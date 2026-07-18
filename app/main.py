"""FastAPI app: React admin + API + background loops (btc ws, engine)."""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                                   RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles

from . import btc, clawby, config, db, engine, executor, mystic, strategy

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("main")

ADMIN_HTML = (Path(__file__).parent / "admin.html").read_text(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
UI_DIST = ROOT / "frontend" / "dist"
BT_DIR = ROOT / "backtest"


def _load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    tasks = [asyncio.create_task(btc.ws_loop()),
             asyncio.create_task(engine.loop())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="claw-poly", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True, "last_tick": db.get_meta("last_tick"),
            "btc": btc.price(), "mode": db.get_meta("mode", "paper")}


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/admin")


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    if (UI_DIST / "index.html").exists():
        return FileResponse(UI_DIST / "index.html")
    return HTMLResponse(ADMIN_HTML)


@app.get("/admin-lite", response_class=HTMLResponse)
async def admin_lite():
    return HTMLResponse(ADMIN_HTML)


@app.get("/api/rounds")
async def api_rounds(limit: int = 300, state: str = "", mode: str = "",
                     side: str = "", result: str = "", strategy: str = ""):
    return {"rounds": db.position_rows(limit, state, mode, side, result, strategy)}


@app.get("/api/orders")
async def api_orders(limit: int = 300, kind: str = "", mode: str = "",
                     slug: str = "", strategy: str = ""):
    return {"orders": db.orders_full(limit, kind, mode, slug, strategy)}


def _csv(rows, cols):
    esc = lambda v: ('"' + str(v).replace('"', '""') + '"'
                     if v is not None and any(c in str(v) for c in ',"\n')
                     else ("" if v is None else str(v)))
    lines = [",".join(cols)]
    lines += [",".join(esc(r.get(c)) for c in cols) for r in rows]
    return "﻿" + "\n".join(lines)          # BOM so Excel opens UTF-8


@app.get("/api/export")
async def api_export(what: str = "trades", mode: str = "", strategy: str = ""):
    if what == "orders":
        rows = db.orders_full(3000, mode=mode, strategy=strategy)
        cols = ["id", "ts", "slug", "strategy", "kind", "side", "price", "usd",
                "order_id", "mode", "note"]
    else:
        rows = [r for r in db.position_rows(3000, mode=mode, strategy=strategy)
                if r.get("strategy")]
        cols = ["slug", "start_ts", "end_ts", "strategy", "state", "side",
                "entry_price", "usd", "shares", "open_price", "close_price",
                "result", "pnl", "mode", "reason", "order_id", "tp_order_id"]
    name = f"claw-poly_{what}_{time.strftime('%Y%m%d_%H%M')}.csv"
    return Response(_csv(rows, cols), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/equity")
async def api_equity(mode: str = "", points: int = 1440):
    m = mode or db.get_meta("mode", "paper")
    return {"mode": m, "equity": db.equity_series(m, points)}


@app.get("/api/stats")
async def api_stats(mode: str = "", strategy: str = ""):
    m = mode or db.get_meta("mode", "paper")
    out = db.stats(m, strategy)
    out["mode"] = m
    return out


def _persist_env(key, value):
    """Set KEY=value in the project .env (replaces existing/commented line)."""
    p = ROOT / ".env"
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    out, done = [], False
    for ln in lines:
        s = ln.strip()
        if (s.startswith(f"{key}=") or s.startswith(f"# {key}=")
                or s.startswith(f"#{key}=")):
            if not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(ln)
    if not done:
        out.append(f"{key}={value}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


@app.get("/api/private-key")
async def api_private_key_status():
    addr = ""
    if config.PM_PRIVATE_KEY:
        try:
            from eth_account import Account
            addr = Account.from_key(config.PM_PRIVATE_KEY).address
        except Exception:  # noqa: BLE001
            addr = "(无法解析)"
    return {"configured": bool(config.PM_PRIVATE_KEY), "address": addr,
            "funder": config.PM_FUNDER, "signature_type": config.PM_SIGNATURE_TYPE,
            "match": bool(addr and config.PM_FUNDER
                          and addr.lower() == config.PM_FUNDER.lower())}


@app.post("/api/private-key")
async def api_private_key_set(payload: dict):
    key = str(payload.get("key") or "").strip()
    if key.lower() in ("", "clear"):
        _persist_env("PM_PRIVATE_KEY", "")
        import os
        os.environ["PM_PRIVATE_KEY"] = ""
        config.PM_PRIVATE_KEY = ""
        executor._client = None
        db.save_settings({"live_enabled": "0"})
        return {"ok": True, "configured": False, "message": "私钥已清除,实盘已关闭"}
    if not key.startswith("0x"):
        key = "0x" + key
    body = key[2:]
    if len(body) != 64 or any(c not in "0123456789abcdefABCDEF" for c in body):
        return JSONResponse({"ok": False, "error": "格式错误:应为 0x + 64 位十六进制"},
                            status_code=400)
    try:
        from eth_account import Account
        addr = Account.from_key(key).address
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"私钥无效:{str(exc)[:80]}"},
                            status_code=400)
    warning = ""
    if config.PM_FUNDER and addr.lower() != config.PM_FUNDER.lower() \
            and config.PM_SIGNATURE_TYPE == 0:
        warning = (f"注意:推导地址 {addr} 与资金地址 {config.PM_FUNDER} 不一致;"
                   "EOA 直签模式下将使用推导地址的资金")
    _persist_env("PM_PRIVATE_KEY", key)
    import os
    os.environ["PM_PRIVATE_KEY"] = key
    config.PM_PRIVATE_KEY = key
    executor._client = None                    # rebuild live client with new key
    db.set_meta("clob_creds", "")              # re-derive L2 creds for the new key
    log.info("private key configured via admin (address %s)", addr)
    return {"ok": True, "configured": True, "address": addr, "warning": warning}


@app.post("/api/private-key/context")
async def api_private_key_context(payload: dict):
    """Set funder address + signature type from the admin (persisted to .env)."""
    import os
    funder = str(payload.get("funder") or "").strip()
    if funder and not (funder.startswith("0x") and len(funder) == 42):
        return JSONResponse({"ok": False, "error": "资金地址格式错误(0x + 40 位十六进制)"},
                            status_code=400)
    try:
        sig = int(payload.get("signature_type", 0))
        assert sig in (0, 1, 2)
    except (TypeError, ValueError, AssertionError):
        return JSONResponse({"ok": False, "error": "签名类型须为 0 / 1 / 2"},
                            status_code=400)
    _persist_env("PM_FUNDER", funder)
    _persist_env("PM_SIGNATURE_TYPE", str(sig))
    os.environ["PM_FUNDER"] = funder
    os.environ["PM_SIGNATURE_TYPE"] = str(sig)
    config.PM_FUNDER = funder
    config.PM_SIGNATURE_TYPE = sig
    executor._client = None
    db.set_meta("clob_creds", "")
    log.info("funder/signature_type updated via admin: %s / %s", funder, sig)
    return {"ok": True, "funder": funder, "signature_type": sig}


@app.get("/api/strategies")
async def api_strategies():
    s = db.get_settings()
    m = db.get_meta("mode", "paper")
    today = {k: db.realized_today(m, k) for k in strategy.STRATEGIES}
    return {"enabled": s["enabled_strategies"], "strat_cfg": s["strat_cfg"],
            "params": s["params"], "meta": strategy.META,
            "today_pnl": today, "mode": m,
            "picks": _load_json(BT_DIR / "picks.json") or [],
            "accuracy": _load_json(BT_DIR / "accuracy.json")}


@app.get("/api/positions/open")
async def api_positions_open(quotes: int = 1):
    """Open positions. quotes=0 -> instant (no market data); quotes=1 -> live
    bids for the nearest 16 positions fetched with concurrency 10."""
    rows = [r for r in db.position_rows(200)
            if r.get("strategy") and r["state"] in ("ordered", "holding", "tp_set")]
    rows.sort(key=lambda x: x["start_ts"])
    out = [{**r, "cur_bid": None, "unrealized": None} for r in rows]
    quoted = 0
    if quotes:
        sem = asyncio.Semaphore(10)

        async def _quote(i, r):
            token = r["token_up"] if r["side"] == "up" else r["token_down"]
            if not token:
                return
            async with sem:
                px = await clawby.best_prices(token)
            if px and px.get("bid") is not None:
                out[i]["cur_bid"] = px["bid"]
                if r["state"] in ("holding", "tp_set"):
                    out[i]["unrealized"] = round(
                        (r["shares"] or 0) * px["bid"] - (r["usd"] or 0), 2)

        targets = list(enumerate(rows))[:16]
        await asyncio.gather(*(_quote(i, r) for i, r in targets))
        quoted = len(targets)
    return {"positions": out, "ts": int(time.time()), "quoted": quoted}


@app.get("/api/mystic")
async def api_mystic():
    try:
        plan = json.loads(db.get_meta("mystic_plan") or "{}")
    except ValueError:
        plan = {}
    s = db.get_settings()
    out = {"almanac": mystic.almanac(),
           "active": "mystic_east" in s["enabled_strategies"], "plan": None}
    if plan.get("entries"):
        slugs = [e["slug"] for e in plan["entries"]]
        rows = db.position_rows(300, strategy="mystic_east")
        by = {r["slug"]: r for r in rows if r.get("strategy") == "mystic_east"}
        now = time.time()
        entries = []
        filled = 0
        for e in plan["entries"]:
            p = by.get(e["slug"]) or {}
            st = p.get("state")
            if st in ("tp_set", "holding", "settled"):
                filled += 1
            entries.append({**e, "pos_state": st,
                            "entry_price": p.get("entry_price"),
                            "pnl": p.get("pnl"),
                            "pos_reason": p.get("reason"),
                            "missed": st is None and e["start_ts"] + 270 < now})
        out["plan"] = {
            "created": plan["created"], "seed": plan["seed"],
            "fate": plan["fate"], "day": plan["almanac"],
            "profile": plan["profile"], "total": len(slugs),
            "max_price": plan.get("max_price", 0.55),
            "tp_mode": plan.get("tp_mode", "settle"),
            "tp_price": plan.get("tp_price"),
            "usd": (s["strat_cfg"].get("mystic_east") or {}).get("usd", 1),
            "placed": sum(1 for x in slugs if x in by),
            "filled": filled,
            "done": sum(1 for x in slugs
                        if by.get(x, {}).get("state") == "settled"),
            "pnl": round(sum(by.get(x, {}).get("pnl") or 0 for x in slugs), 2),
            "entries": entries,
        }
    return out


@app.post("/api/mystic/start")
async def api_mystic_start(payload: dict):
    name = str(payload.get("name") or "").strip()
    birth = str(payload.get("birth") or "").strip()
    gender = str(payload.get("gender") or "男").strip()
    place = str(payload.get("birthplace") or "").strip()
    try:
        usd = max(0.5, min(100.0, float(payload.get("usd") or 1)))
        cap = max(0.51, min(0.85, float(payload.get("max_price") or 0.55)))
        count = max(1, min(100, int(payload.get("count") or 50)))
        tp_mode = str(payload.get("tp_mode") or "settle")
        tp_mode = tp_mode if tp_mode in ("settle", "book") else "settle"
        tp_px = max(0.55, min(0.99, float(payload.get("tp_price") or 0.8)))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "金额/买价/盘数格式错误"}, status_code=400)
    if not name or not place:
        return JSONResponse({"ok": False, "error": "姓名和出生地必填"}, status_code=400)
    try:
        y = int(birth.split("-")[0])
        assert 1900 <= y <= 2100
        first = (int(time.time()) // 300 + 2) * 300      # 下下盘开始,留足挂单时间
        plan = mystic.build_plan(name, birth, gender, place, first, n=count)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"生辰解析失败:{str(exc)[:60]}"},
                            status_code=400)
    plan["max_price"] = cap
    plan["tp_mode"] = tp_mode
    plan["tp_price"] = tp_px
    db.set_meta("mystic_plan", json.dumps(plan, ensure_ascii=False))
    s = db.get_settings()
    cfg = s["strat_cfg"]
    cfg["mystic_east"] = {"usd": usd, "daily_loss": round(usd * count + 1, 2),
                          "entry_delay": 0}
    en = s["enabled_strategies"]
    if "mystic_east" not in en:
        en = en + ["mystic_east"]
    db.save_settings({"strat_cfg": json.dumps(cfg),
                      "enabled_strategies": json.dumps(en)})
    log.info("mystic_east 命盘生成:%s 50盘 seed=%s", plan["profile"]["name"],
             plan["seed"])
    return {"ok": True, "seed": plan["seed"], "fate": plan["fate"],
            "almanac": plan["almanac"], "total_cost": round(usd * count, 2),
            "count": count, "first_ts": first, "preview": plan["entries"][:10]}


@app.post("/api/mystic/stop")
async def api_mystic_stop():
    s = db.get_settings()
    en = [k for k in s["enabled_strategies"] if k != "mystic_east"]
    db.save_settings({"enabled_strategies": json.dumps(en)})
    db.set_meta("mystic_plan", "")
    return {"ok": True, "message": "命盘已终止;在途仓位将正常结算"}


@app.get("/api/backtest")
async def api_backtest():
    return {name: (BT_DIR / name).read_text(encoding="utf-8")
            if (BT_DIR / name).exists() else ""
            for name in ("REPORT.md", "ACCURACY.md", "PREBET.md")}


def _signal_preview(s):
    """Live view of what pre_trend would do right now (display only)."""
    if "pre_trend" not in (s.get("enabled_strategies") or []):
        return None
    p = s["params"]
    lb = int(p.get("lookback_sec", 600))
    move = btc.change(lb)
    out = {"ready": move is not None, "move_pct": move, "side": None,
           "tier": None, "lead_sec": int(p.get("lead_sec", 600)),
           "lookback_sec": lb,
           "cover_on": bool(int(float(p.get("cover", 1))))}
    if move is not None:
        side = "up" if move > 0 else "down"
        if str(p.get("signal", "revert")) == "revert":
            side = "down" if side == "up" else "up"
        out["side"] = side
        out["move_pct"] = round(move, 4)
        out["tier"] = ("trigger" if abs(move) >= float(p.get("min_move_pct", 0.2))
                       else "cover")
    return out


@app.get("/api/state")
async def api_state():
    s = db.get_settings()
    m = db.get_meta("mode", "paper")
    return {
        "settings": s["_raw"],
        "status": {
            "now": int(time.time()),
            "mode": m,
            "live_ready": bool(config.PM_PRIVATE_KEY),
            "btc": btc.price(),
            "btc_buffer_min": round(btc.buffer_span() / 60, 1),
            "last_tick": int(db.get_meta("last_tick", "0") or 0),
            "halted": db.get_meta("halted", "") == "1",
            "realized_today": db.realized_today(m),
            "preview": _signal_preview(s),
        },
        "rounds": db.recent_rounds(24),
        "positions": db.recent_positions(48),
        "equity": db.equity_series(m, 720),
        "orders": db.recent_orders(30),
    }


@app.post("/api/settings")
async def api_settings(payload: dict):
    numeric = {"usd_per_market", "take_profit_pct", "horizon", "entry_delay_sec",
               "daily_loss_halt_usd", "max_open_usd", "overpay_cap"}
    updates = {}
    for key in config.DEFAULT_SETTINGS:
        if key not in payload:
            continue
        value = payload[key]
        if key in numeric:
            try:
                value = float(value)
                if value < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return JSONResponse({"ok": False, "error": f"invalid {key}"},
                                    status_code=400)
            value = f"{value:g}"
        elif key == "enabled_strategies":
            try:
                v = value if isinstance(value, list) else json.loads(value)
                assert isinstance(v, list)
                v = [k for k in v if k in strategy.STRATEGIES]
                value = json.dumps(v)
            except (ValueError, AssertionError):
                return JSONResponse({"ok": False, "error": "invalid enabled_strategies"},
                                    status_code=400)
        elif key == "strat_cfg":
            try:
                v = value if isinstance(value, dict) else json.loads(value)
                assert isinstance(v, dict)
                for k, c in v.items():
                    assert k in strategy.STRATEGIES and isinstance(c, dict)
                    for f in ("usd", "daily_loss", "entry_delay"):
                        if f in c:
                            c[f] = max(0.0, float(c[f]))
                value = json.dumps(v)
            except (ValueError, AssertionError, TypeError):
                return JSONResponse({"ok": False, "error": "invalid strat_cfg"},
                                    status_code=400)
        elif key == "auto_redeem":
            value = "1" if value in (True, "1", "true", "on") else "0"
        elif key == "live_enabled":
            on = value in (True, "1", "true", "on")
            if on and not config.PM_PRIVATE_KEY:
                return JSONResponse(
                    {"ok": False, "error": "PM_PRIVATE_KEY 未配置,无法开启实盘"},
                    status_code=400)
            value = "1" if on else "0"
        updates[key] = value
    db.save_settings(updates)
    return {"ok": True, "saved": list(updates)}


if UI_DIST.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIST, html=True), name="ui")
