"""FastAPI app: React admin + API + background loops (btc ws, engine)."""
import asyncio
import json
import logging
import math
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                                   RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles

from . import btc, clawby, config, db, engine, mystic, strategy

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
    config.enforce_paper_only_environment()
    db.init()
    log.warning("PAPER_ONLY research build | localhost only | no wallet | no live trading")
    tasks = [asyncio.create_task(btc.ws_loop()),
             asyncio.create_task(engine.loop())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="claw-poly", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost"],
)

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@app.middleware("http")
async def local_write_guard(request: Request, call_next):
    """【PAPER_ONLY】Reject cross-origin/non-local state-changing requests."""
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        client_host = request.client.host if request.client else ""
        if client_host not in _LOCAL_HOSTS:
            return JSONResponse({"ok": False, "error": "local client required"},
                                status_code=403)
        if origin:
            try:
                origin_host = (urlparse(origin).hostname or "").lower()
            except ValueError:
                origin_host = ""
            if origin_host not in _LOCAL_HOSTS:
                return JSONResponse({"ok": False, "error": "local origin required"},
                                    status_code=403)
    return await call_next(request)


@app.get("/health")
async def health():
    return {"ok": True, "last_tick": db.get_meta("last_tick"),
            "btc": btc.price(), "mode": "paper", "paper_only": True}


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
    if mode not in ("", "paper"):
        return JSONResponse({"ok": False, "error": "paper mode only"}, status_code=400)
    return {"rounds": db.position_rows(limit, state, "paper", side, result, strategy)}


@app.get("/api/orders")
async def api_orders(limit: int = 300, kind: str = "", mode: str = "",
                     slug: str = "", strategy: str = ""):
    if mode not in ("", "paper"):
        return JSONResponse({"ok": False, "error": "paper mode only"}, status_code=400)
    return {"orders": db.orders_full(limit, kind, "paper", slug, strategy)}


def _csv(rows, cols):
    esc = lambda v: ('"' + str(v).replace('"', '""') + '"'
                     if v is not None and any(c in str(v) for c in ',"\n')
                     else ("" if v is None else str(v)))
    lines = [",".join(cols)]
    lines += [",".join(esc(r.get(c)) for c in cols) for r in rows]
    return "﻿" + "\n".join(lines)          # BOM so Excel opens UTF-8


@app.get("/api/export")
async def api_export(what: str = "trades", mode: str = "", strategy: str = ""):
    if mode not in ("", "paper"):
        return JSONResponse({"ok": False, "error": "paper mode only"}, status_code=400)
    if what == "orders":
        rows = db.orders_full(3000, mode="paper", strategy=strategy)
        cols = ["id", "ts", "slug", "strategy", "kind", "side", "price", "usd",
                "order_id", "mode", "note"]
    else:
        rows = [r for r in db.position_rows(3000, mode="paper", strategy=strategy)
                if r.get("strategy")]
        cols = ["slug", "start_ts", "end_ts", "strategy", "state", "side",
                "entry_price", "usd", "shares", "open_price", "close_price",
                "result", "pnl", "mode", "reason", "order_id", "tp_order_id"]
    name = f"claw-poly_{what}_{time.strftime('%Y%m%d_%H%M')}.csv"
    return Response(_csv(rows, cols), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/equity")
async def api_equity(mode: str = "", points: int = 1440):
    if mode not in ("", "paper"):
        return JSONResponse({"ok": False, "error": "paper mode only"}, status_code=400)
    return {"mode": "paper", "equity": db.equity_series("paper", points)}


@app.get("/api/stats")
async def api_stats(mode: str = "", strategy: str = ""):
    if mode not in ("", "paper"):
        return JSONResponse({"ok": False, "error": "paper mode only"}, status_code=400)
    out = db.stats("paper", strategy)
    out["mode"] = "paper"
    return out


@app.get("/api/strategies")
async def api_strategies():
    s = db.get_settings()
    m = "paper"
    today = {k: db.realized_today(m, k) for k in strategy.STRATEGIES}
    return {"enabled": s["enabled_strategies"], "strat_cfg": s["strat_cfg"],
            "params": s["params"], "meta": strategy.META,
            "today_pnl": today, "mode": m,
            "picks": _load_json(BT_DIR / "picks.json") or [],
            "accuracy": _load_json(BT_DIR / "accuracy.json")}


@app.get("/api/positions/open")
async def api_positions_open(quotes: int = 1):
    """Open positions. quotes=0 -> instant (no market data); quotes=1 -> current
    bids for the nearest 16 positions fetched with concurrency 10."""
    rows = [r for r in db.position_rows(200, mode="paper")
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
    """Current paper-signal preview (display only)."""
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
    m = "paper"
    return {
        "settings": s["_raw"],
        "status": {
            "now": int(time.time()),
            "mode": m,
            "paper_only": config.PAPER_ONLY,
            "btc": btc.price(),
            "btc_buffer_min": round(btc.buffer_span() / 60, 1),
            "last_tick": int(db.get_meta("last_tick", "0") or 0),
            "halted": db.get_meta("halted", "") == "1",
            "realized_today": db.realized_today(m),
            "preview": _signal_preview(s),
        },
        "rounds": db.recent_rounds(24),
        "positions": db.position_rows(48, mode="paper"),
        "equity": db.equity_series(m, 720),
        "orders": db.orders_full(30, mode="paper"),
    }


_SETTING_RANGES = {
    "usd_per_market": (0.5, 1000.0),
    "take_profit_pct": (0.0, 500.0),
    "horizon": (1.0, 100.0),
    "entry_delay_sec": (0.0, 86400.0),
    "daily_loss_halt_usd": (0.0, 100000.0),
    "max_open_usd": (0.0, 100000.0),
    "overpay_cap": (0.01, 0.99),
}
_PARAM_RANGES = {
    "edge_min": (0.0, 1.0), "price_margin": (0.0, 1.0),
    "burst_min": (0.0, 100.0), "rev_min": (0.0, 100.0),
    "momo_window": (1.0, 3600.0), "momo_min": (0.0, 100.0),
    "lead_sec": (0.0, 32400.0), "lookback_sec": (1.0, 86400.0),
    "min_move_pct": (0.0, 100.0), "max_price": (0.01, 0.99),
}
_INTEGER_PARAMS = {"momo_window", "lead_sec", "lookback_sec"}
_ALLOWED_SETTINGS = set(_SETTING_RANGES) | {
    "strategy", "enabled_strategies", "strat_cfg", "params",
}


def _parse_json_object(value):
    parsed = value if isinstance(value, dict) else json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError
    return parsed


def _parse_finite_number(value):
    if isinstance(value, bool):
        raise ValueError
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError from exc
    if not math.isfinite(number):
        raise ValueError
    return number


@app.post("/api/settings")
async def api_settings(payload: dict):
    """Whitelisted paper-strategy settings; trading controls do not exist."""
    if not isinstance(payload, dict) or any(k not in _ALLOWED_SETTINGS for k in payload):
        return JSONResponse({"ok": False, "error": "unsupported settings field"},
                            status_code=400)
    updates = {}
    for key, value in payload.items():
        if key in _SETTING_RANGES:
            try:
                number = _parse_finite_number(value)
                low, high = _SETTING_RANGES[key]
                if not low <= number <= high:
                    raise ValueError
                if key in {"horizon", "entry_delay_sec"} and not number.is_integer():
                    raise ValueError
            except (TypeError, ValueError):
                return JSONResponse({"ok": False, "error": f"invalid {key}"},
                                    status_code=400)
            updates[key] = f"{number:g}"
        elif key == "strategy":
            if not isinstance(value, str) or value not in strategy.STRATEGIES:
                return JSONResponse({"ok": False, "error": "invalid strategy"},
                                    status_code=400)
            updates[key] = value
        elif key == "enabled_strategies":
            try:
                values = value if isinstance(value, list) else json.loads(value)
                if (not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                        or any(v not in strategy.STRATEGIES for v in values)):
                    raise ValueError
                updates[key] = json.dumps(list(dict.fromkeys(values)))
            except (TypeError, ValueError, json.JSONDecodeError):
                return JSONResponse({"ok": False, "error": "invalid enabled_strategies"},
                                    status_code=400)
        elif key == "strat_cfg":
            try:
                values = _parse_json_object(value)
                clean = {}
                for name, fields in values.items():
                    if name not in strategy.STRATEGIES or not isinstance(fields, dict):
                        raise ValueError
                    if any(field not in {"usd", "daily_loss", "entry_delay"}
                           for field in fields):
                        raise ValueError
                    item = {}
                    for field, raw in fields.items():
                        number = _parse_finite_number(raw)
                        limits = {"usd": (0.5, 1000.0), "daily_loss": (0.0, 100000.0),
                                  "entry_delay": (0.0, 86400.0)}[field]
                        if not limits[0] <= number <= limits[1]:
                            raise ValueError
                        if field == "entry_delay" and not number.is_integer():
                            raise ValueError
                        item[field] = int(number) if field == "entry_delay" else number
                    clean[name] = item
                updates[key] = json.dumps(clean)
            except (TypeError, ValueError, json.JSONDecodeError):
                return JSONResponse({"ok": False, "error": "invalid strat_cfg"},
                                    status_code=400)
        elif key == "params":
            try:
                values = _parse_json_object(value)
                if any(name not in set(_PARAM_RANGES) | {"signal", "cover"}
                       for name in values):
                    raise ValueError
                clean = {}
                for name, raw in values.items():
                    if name == "signal":
                        if raw not in {"revert", "momo"}:
                            raise ValueError
                        clean[name] = raw
                    elif name == "cover":
                        number = _parse_finite_number(raw)
                        if not number.is_integer() or int(number) not in (0, 1):
                            raise ValueError
                        clean[name] = int(number)
                    else:
                        number = _parse_finite_number(raw)
                        low, high = _PARAM_RANGES[name]
                        if not low <= number <= high:
                            raise ValueError
                        if name in _INTEGER_PARAMS and not number.is_integer():
                            raise ValueError
                        clean[name] = int(number) if name in _INTEGER_PARAMS else number
                updates[key] = json.dumps(clean)
            except (TypeError, ValueError, json.JSONDecodeError):
                return JSONResponse({"ok": False, "error": "invalid params"},
                                    status_code=400)
    db.save_settings(updates)
    return {"ok": True, "saved": list(updates)}


if UI_DIST.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIST, html=True), name="ui")
