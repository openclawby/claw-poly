"""Order execution: paper simulation or live py-clob-client.

live requires PM_PRIVATE_KEY in env AND the admin master switch
(settings.live_enabled). Without either, everything runs in paper mode with
identical bookkeeping. The private key signs orders locally (EIP-712) and
never leaves this machine.
"""
import asyncio
import logging
import math
import time

from . import clawby, config, db

log = logging.getLogger("executor")

_client = None          # lazy py-clob-client instance (live only)
_client_lock = asyncio.Lock()


def mode(settings=None):
    s = settings or db.get_settings()
    if s["live_enabled"] and config.PM_PRIVATE_KEY:
        return "live"
    return "paper"


async def _get_client():
    """Build (once) the L2-authed ClobClient in a worker thread."""
    global _client
    async with _client_lock:
        if _client is not None:
            return _client

        def build():
            from py_clob_client_v2 import ApiCreds, ClobClient
            creds_cached = db.get_meta("clob_creds", "")
            base = dict(host=config.CLOB_HOST, key=config.PM_PRIVATE_KEY,
                        chain_id=config.CHAIN_ID)
            if config.PM_SIGNATURE_TYPE:
                base.update(signature_type=config.PM_SIGNATURE_TYPE,
                            funder=config.PM_FUNDER)
            c = ClobClient(**base)
            if creds_cached:
                import json as _j
                d = _j.loads(creds_cached)
                c.set_api_creds(ApiCreds(d["k"], d["s"], d["p"]))
            else:
                creds = c.create_or_derive_api_key()
                c.set_api_creds(creds)
                import json as _j
                db.set_meta("clob_creds", _j.dumps(
                    {"k": creds.api_key, "s": creds.api_secret,
                     "p": creds.api_passphrase}))
            return c

        _client = await asyncio.to_thread(build)
        log.info("live CLOB client ready")
        return _client


def _is_transient(exc):
    """服务器/网络类错误(5xx / 超时 / 连接)才值得重试;4xx 参数错误不重试。"""
    s = str(exc).lower()
    if "status_code=5" in s or "status=5" in s:            # 500/502/503/504
        return True
    if any(k in s for k in ("timeout", "timed out", "connection",
                            "request exception", "temporarily")):
        return True
    if "status_code=4" in s or "status=4" in s:            # 明确的 4xx 不重试
        return False
    return False


async def _post_with_retry(fn, slug, attempts=3):
    """下单提交,遇 5xx/网络类错误退避重试;4xx 立即抛出。"""
    last = None
    for i in range(attempts):
        try:
            return await asyncio.to_thread(fn)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < attempts - 1 and _is_transient(exc):
                wait = 2 * (i + 1)
                log.warning("下单 %s 第%d次遇服务器错误,%ds 后重试:%s",
                            slug, i + 1, wait, str(exc)[:100])
                await asyncio.sleep(wait)
                continue
            raise
    raise last


async def place_limit(round_row, side, shares, limit_price, settings, strategy=""):
    """GTC limit BUY of `shares` shares. Returns order_id (paper: 'paper:...')."""
    m = mode(settings)
    token = round_row["token_up"] if side == "up" else round_row["token_down"]
    tick = round_row.get("tick") or 0.01
    price = max(tick, min(round(round(limit_price / tick) * tick, 4), 1 - tick))
    shares = max(5, int(round(shares)))             # 交易所强制最小 5 股/单
    usd = round(price * shares, 2)

    if m == "paper":
        oid = f"paper:{round_row['slug']}:{side}"
        db.log_order(round_row["slug"], "buy_limit", side, price, usd, oid, m,
                     strategy=strategy)
        return oid, price, shares

    client = await _get_client()

    def _do():
        from py_clob_client_v2 import (OrderArgs, OrderType,
                                       PartialCreateOrderOptions, Side)
        ts = f"{tick:g}"
        opts = (PartialCreateOrderOptions(tick_size=ts)
                if ts in ("0.1", "0.01", "0.005", "0.0025", "0.001", "0.0001")
                else None)                      # 非标准 tick 交给 SDK 自查
        return client.create_and_post_order(
            order_args=OrderArgs(token_id=token, price=price,
                                 size=shares, side=Side.BUY),
            options=opts, order_type=OrderType.GTC)

    resp = await _post_with_retry(_do, round_row["slug"])
    oid = (resp or {}).get("orderID") or (resp or {}).get("orderId") or ""
    ok = bool((resp or {}).get("success", oid))
    db.log_order(round_row["slug"], "buy_limit", side, price, usd, oid, m,
                 note="" if ok else str(resp)[:150], strategy=strategy)
    if not ok:
        raise RuntimeError(f"order rejected: {str(resp)[:200]}")
    return oid, price, shares


async def place_tp(round_row, settings, strategy="", tp_price=None):
    """GTC SELL of held shares. tp_price=None -> entry*(1+global tp%)."""
    m = mode(settings)
    side = round_row["side"]
    token = round_row["token_up"] if side == "up" else round_row["token_down"]
    tick = round_row.get("tick") or 0.01
    if tp_price is None:
        tp_price = round_row["entry_price"] * (1 + settings["take_profit_pct"] / 100)
    tp_price = max(tick, min(round(round(tp_price / tick) * tick, 4), 1 - tick))
    shares = round_row.get("shares") or 0

    if m == "paper":
        oid = f"paper-tp:{round_row['slug']}"
        db.log_order(round_row["slug"], "sell_tp", side, tp_price, None, oid, m,
                     strategy=strategy)
        return oid, tp_price

    client = await _get_client()

    def _do():
        from py_clob_client_v2 import (OrderArgs, OrderType,
                                       PartialCreateOrderOptions, Side)
        ts = f"{tick:g}"
        opts = (PartialCreateOrderOptions(tick_size=ts)
                if ts in ("0.1", "0.01", "0.005", "0.0025", "0.001", "0.0001")
                else None)
        return client.create_and_post_order(
            order_args=OrderArgs(token_id=token, price=tp_price,
                                 size=shares, side=Side.SELL),
            options=opts, order_type=OrderType.GTC)

    resp = await asyncio.to_thread(_do)
    oid = (resp or {}).get("orderID") or ""
    db.log_order(round_row["slug"], "sell_tp", side, tp_price, None, oid, m,
                 strategy=strategy)
    return oid, tp_price


async def order_filled(round_row, settings):
    """Has the entry order filled? paper: filled once market ask <= our limit.
    live: query the order's status."""
    m = mode(settings)
    if m == "paper":
        token = round_row["token_up"] if round_row["side"] == "up" else round_row["token_down"]
        px = await clawby.best_prices(token)
        return bool(px and px["ask"] is not None
                    and px["ask"] <= round_row["entry_price"] + 1e-9)
    client = await _get_client()

    def _do():
        return client.get_order(round_row["order_id"])

    try:
        o = await asyncio.to_thread(_do)
        return str((o or {}).get("status", "")).lower() == "matched" or \
            float((o or {}).get("size_matched") or 0) > 0
    except Exception as exc:  # noqa: BLE001
        log.warning("order status %s: %s", round_row["order_id"], exc)
        return False


async def cancel_all():
    if not config.PM_PRIVATE_KEY:
        return
    try:
        client = await _get_client()
        await asyncio.to_thread(client.cancel_all)
        log.info("cancel_all done")
    except Exception as exc:  # noqa: BLE001
        log.warning("cancel_all failed: %s", exc)


async def cancel_order(order_id):
    if order_id.startswith("paper"):
        return True
    try:
        client = await _get_client()
        from py_clob_client_v2.clob_types import OrderPayload

        def _cancel():
            return client.cancel_order(OrderPayload(orderID=order_id))
        await asyncio.to_thread(_cancel)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("cancel %s failed: %s", order_id, exc)
        return False
