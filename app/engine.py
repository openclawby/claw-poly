"""15s tick: manage the rolling horizon of 5-minute rounds, MULTI-STRATEGY.

Markets (rounds table) hold shared facts; each enabled strategy keeps its own
position per round (positions table), with its own stake and daily stop.

Per-position state machine:
  (no row)  -> strategy fires inside its window -> ordered
  ordered   -> entry limit filled               -> tp_set
  ordered   -> round ends unfilled, cancel      -> skipped
  tp_set    -> round result known               -> settled (pnl booked)
Risk gates: global daily halt, per-strategy daily stop, overpay cap,
total open exposure cap.
"""
import asyncio
import json
import logging
import time
from pathlib import Path

from . import btc, clawby, config, db, executor, markets, redeem, strategy

_LOG_FILE = Path(__file__).resolve().parent.parent / "run.log"
_LOG_MAX = 20 * 1024 * 1024            # 20MB -> keep last 2MB


def _rotate_log():
    try:
        if _LOG_FILE.exists() and _LOG_FILE.stat().st_size > _LOG_MAX:
            tail = _LOG_FILE.read_bytes()[-2 * 1024 * 1024:]
            _LOG_FILE.write_bytes(b"[log rotated]\n" + tail)
            log.info("run.log rotated (kept last 2MB)")
    except OSError as exc:
        log.warning("log rotate failed: %s", exc)

log = logging.getLogger("engine")

TICK = 15


async def _px(token, cache):
    if token not in cache:
        cache[token] = await clawby.best_prices(token)
    return cache[token]


async def _try_open(st, r, settings, now, halted, px_cache):
    if not st.wants(r):
        return                                     # 与本策略无关的盘口,零开销
    if now < st.entry_ts(r):
        return
    m = executor.mode(settings)
    if getattr(st, "preopen_only", False) and now >= r["start_ts"]:
        db.insert_position(r["slug"], st.key, state="skipped",
                           reason="开盘前未触发,本盘不参与", mode=m)
        return
    if now > r["end_ts"] - 30:
        db.insert_position(r["slug"], st.key, state="skipped",
                           reason="窗口错过/未触发", mode=m)
        return
    if halted:
        db.insert_position(r["slug"], st.key, state="skipped",
                           reason="止损熔断中", mode=m)
        return
    if not r.get("token_up"):
        return
    if db.open_usd() + st.usd > settings["max_open_usd"]:
        return                                     # wait; may free up next tick
    px = await _px(r["token_up"], px_cache)
    up_price = px["mid"] if px and px["mid"] is not None else None
    sig = st.decide(r, now, up_price)
    if not sig:
        return
    if sig.limit_price > settings["overpay_cap"]:
        db.insert_position(r["slug"], st.key, state="skipped",
                           reason=f"限价{sig.limit_price:.2f}超overpay上限", mode=m)
        return
    try:
        oid, price, shares = await executor.place_limit(
            r, sig.side, st.usd, sig.limit_price, settings, strategy=st.key)
    except Exception as exc:  # noqa: BLE001
        log.warning("place %s/%s failed: %s", r["slug"], st.key, exc)
        db.insert_position(r["slug"], st.key, state="skipped",
                           reason=f"下单失败:{str(exc)[:80]}", mode=m)
        return
    db.insert_position(r["slug"], st.key, state="ordered", side=sig.side,
                       entry_price=price, usd=st.usd, shares=shares,
                       order_id=oid, reason=sig.reason, mode=m)
    log.info("ordered %s [%s] %s @%.2f (%s)", r["slug"], st.key, sig.side,
             price, sig.reason)
    # paper 即时成交:吃单(限价 >= 当前卖价)现实中立即撮合,无需等下个周期
    ask = None
    if px:
        if sig.side == "up":
            ask = px.get("ask")
        elif px.get("bid") is not None:
            ask = round(1 - px["bid"], 4)          # Down 的卖价 = 1 - Up 买价
    if m == "paper" and ask is not None and price >= ask - 1e-9:
        merged = {**r, "side": sig.side, "entry_price": price,
                  "shares": shares, "usd": st.usd}
        tp = st.tp_price(price, settings)
        if tp is None:                            # 自动结算模式:持仓到期,不挂止盈
            db.update_position(r["slug"], st.key, state="holding")
            log.info("filled %s [%s] instantly -> hold to settle", r["slug"], st.key)
        else:
            oid2, tpp = await executor.place_tp(merged, settings, strategy=st.key,
                                                tp_price=tp)
            db.update_position(r["slug"], st.key, state="tp_set",
                               tp_order_id=oid2, tp_price=tpp)
            log.info("filled %s [%s] instantly -> tp @%.2f", r["slug"], st.key, tpp)


async def _handle_ordered(pos, r, settings, now, px_cache, strat_map):
    merged = {**r, **pos}
    if now >= r["end_ts"]:
        await executor.cancel_order(pos["order_id"] or "")
        db.update_position(r["slug"], pos["strategy"], state="skipped",
                           reason="到期未成交,已撤单")
        return
    if executor.mode(settings) == "paper":
        # 远期(>30min 后开盘)的未成交挂单,盘前订单簿几乎不动 -> 每分钟查一次即可
        if r["start_ts"] - now > 1800 and int(now) % 60 >= TICK:
            return
        token = r["token_up"] if pos["side"] == "up" else r["token_down"]
        px = await _px(token, px_cache)
        filled = bool(px and px.get("ask") is not None
                      and px["ask"] <= (pos["entry_price"] or 0) + 1e-9)
    else:
        filled = await executor.order_filled(merged, settings)
    if filled:
        st = strat_map.get(pos["strategy"])
        tp = (st.tp_price(pos["entry_price"], settings) if st is not None
              else (pos["entry_price"] or 0) * (1 + settings["take_profit_pct"] / 100))
        if tp is None:                            # 自动结算模式
            db.update_position(r["slug"], pos["strategy"], state="holding")
            log.info("filled %s [%s] -> hold to settle", r["slug"], pos["strategy"])
            return
        oid, tpp = await executor.place_tp(merged, settings,
                                           strategy=pos["strategy"], tp_price=tp)
        db.update_position(r["slug"], pos["strategy"], state="tp_set",
                           tp_order_id=oid, tp_price=tpp)
        log.info("filled %s [%s] -> tp @%.2f", r["slug"], pos["strategy"], tpp)


async def _handle_settle(pos, r, settings, now, px_cache):
    if now < r["end_ts"] + 15:
        return
    result = r.get("result")
    if not result:
        return                                     # market not resolved yet
    tick = r.get("tick") or 0.01
    tp_hit = False
    tp_price = None
    if pos.get("tp_order_id"):                    # 挂过止盈单才判定是否触发
        tp_price = pos.get("tp_price")
        if tp_price is None:                      # 旧数据:按全局百分比回算
            tp_price = (pos["entry_price"] or 0) * (1 + settings["take_profit_pct"] / 100)
            tp_price = min(round(round(tp_price / tick) * tick, 4), 1 - tick)
        token = r["token_up"] if pos["side"] == "up" else r["token_down"]
        px = await _px(token, px_cache)
        if px and px["bid"] is not None and px["bid"] >= tp_price - 1e-9:
            tp_hit = True
    shares = pos.get("shares") or 0
    usd = pos.get("usd") or 0
    if tp_hit:
        pnl = shares * tp_price - usd
        note = "止盈"
    elif result == pos["side"]:
        pnl = shares * 1.0 - usd
        note = "结算获胜"
    elif result == "unknown":
        pnl = 0.0
        note = "价格覆盖不足,未记账"
    else:
        pnl = -usd
        note = "结算失败"
    db.update_position(r["slug"], pos["strategy"], state="settled",
                       pnl=round(pnl, 4),
                       reason=f"{pos.get('reason', '')} | {note}")
    log.info("settled %s [%s]: %s -> %s pnl=%.2f", r["slug"], pos["strategy"],
             pos["side"], result, pnl)


def _settle_market(r, now):
    """Record open/close/result on the market row once its window ends."""
    if r.get("result") or now < r["end_ts"] + 15:
        return r
    result, open_p, close_p = markets.settle_result(r)
    if result is None and now < r["end_ts"] + 120:
        return r
    db.upsert_round(r["slug"], result=result or "unknown",
                    open_price=r.get("open_price") or open_p, close_price=close_p)
    return db.get_round(r["slug"])


async def loop():
    log.info("engine started (tick %ss, multi-strategy)", TICK)
    await executor.cancel_all()
    while True:
        started = time.monotonic()
        try:
            settings = db.get_settings()
            now = time.time()
            db.set_meta("last_tick", int(now))     # 周期开始即心跳,长周期不误报
            m = executor.mode(settings)

            # 神秘的东方力量:命盘走完自动收工;命盘内的远期盘口主动挂牌发现
            # (Polymarket 提前 ≥8h 挂牌,100 盘可基本一次性买入)
            if "mystic_east" in settings["enabled_strategies"]:
                try:
                    _plan = json.loads(db.get_meta("mystic_plan") or "{}")
                except ValueError:
                    _plan = {}
                _ent = _plan.get("entries") or []
                if not _ent or _ent[-1]["start_ts"] + 300 < now:
                    keys = [k for k in settings["enabled_strategies"]
                            if k != "mystic_east"]
                    db.save_settings({"enabled_strategies": json.dumps(keys)})
                    log.info("mystic_east 命盘已走完,自动收工")
                    settings = db.get_settings()
                else:
                    ensured = 0                    # 每 tick 最多补发现 12 个,防 relay 洪峰
                    for e in _ent:
                        if e["start_ts"] + 300 < now:
                            continue
                        r0 = db.get_round(e["slug"])
                        if r0 and r0.get("token_up"):
                            continue
                        if ensured >= 12:
                            break
                        await markets.ensure_round(e["slug"], e["start_ts"])
                        ensured += 1

            strats = strategy.enabled(settings)
            strat_map = {st.key: st for st in strats}
            total_today = db.realized_today(m)
            global_halt = total_today <= -settings["daily_loss_halt_usd"]
            db.set_meta("halted", "1" if global_halt else "")
            db.set_meta("mode", m)

            for slug, start in markets.upcoming_slugs(settings["horizon"], now):
                r = await markets.ensure_round(slug, start)
                if r and not r.get("open_price") and now >= start:
                    markets.capture_open(r)

            px_cache = {}
            _t_mid = time.monotonic()
            _c0 = clawby.CALLS
            _stats = {"open": 0, "ordered": 0, "settle": 0, "rounds": 0}
            for r in db.rounds_window(now):
                r = _settle_market(r, now)
                _stats["rounds"] += 1
                for st in strats:
                    pos = db.get_position(r["slug"], st.key)
                    _b = clawby.CALLS
                    if pos is None:
                        halted = (global_halt or
                                  db.realized_today(m, st.key) <= -st.daily_loss)
                        await _try_open(st, r, settings, now, halted, px_cache)
                        _stats["open"] += clawby.CALLS - _b
                    elif pos["state"] == "ordered":
                        await _handle_ordered(pos, r, settings, now, px_cache,
                                              strat_map)
                        _stats["ordered"] += clawby.CALLS - _b
                    elif pos["state"] in ("holding", "tp_set"):
                        await _handle_settle(pos, r, settings, now, px_cache)
                        _stats["settle"] += clawby.CALLS - _b

            if (m == "live" and settings.get("auto_redeem", True)
                    and int(now) % 240 < TICK):
                await redeem.run_once()

            db.record_equity(db.realized_today(m), m)
            db.set_meta("last_tick", int(now))
            if int(now) % 3600 < TICK:
                db.prune()
                _rotate_log()
        except Exception:  # noqa: BLE001
            log.exception("engine tick failed")
        _dur = time.monotonic() - started
        if _dur > 20:
            try:
                _pre = _t_mid - started
            except NameError:
                _pre = -1
            try:
                _loop_calls = clawby.CALLS - _c0
                _st = dict(_stats)
            except NameError:
                _loop_calls, _st = -1, {}
            log.warning("slow tick %.1fs (pre-loop %.1fs, loop-calls=%d, %s) relay_by=%s",
                        _dur, _pre, _loop_calls, _st, dict(clawby.CALLS_BY))
        await asyncio.sleep(max(TICK - _dur, 2))
