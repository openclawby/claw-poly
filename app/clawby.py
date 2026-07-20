"""Clawby relay client (data only). Global throttle + retry on upstream 5xx.

NOTE: never use order=start_date on polymarket_events — that sort is a stable
502 upstream; round discovery is slug-constructed locally instead.
"""
import asyncio
import json
import logging
import time

import httpx

from . import config

log = logging.getLogger("clawby")

_MIN_GAP = 0.25
CALLS = 0
CALLS_BY = {}
_last = 0.0
_gap = asyncio.Lock()


async def validate_key(key):
    """-> (ok, message). Live check against the relay; 401 => bad key."""
    if not (key or "").strip():
        return False, "API Key 为空"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{config.CLAWBY_BASE}/api/relay",
                headers={"X-API-Key": key.strip(), "Content-Type": "application/json"},
                json={"name": "polymarket_orderbook",
                      "params": {"token_id": "1"}})
        if resp.status_code == 401:
            return False, "API Key 无效(401),请到 openclawby.com 核对"
        if resp.status_code in (200, 400, 404, 422, 500, 502):
            return True, "校验通过"          # 鉴权已过,业务错误与 key 无关
        return False, f"未知响应 HTTP {resp.status_code}"
    except httpx.TransportError as exc:
        return False, f"无法连接 Clawby:{str(exc)[:80]}"


async def relay(name, params=None, timeout=30, retries=3):
    global _last, CALLS
    if not config.CLAWBY_API_KEY:
        raise RuntimeError("未配置 CLAWBY_API_KEY")
    CALLS += 1
    CALLS_BY[name] = CALLS_BY.get(name, 0) + 1
    for attempt in range(retries):
        async with _gap:
            wait = _MIN_GAP - (time.monotonic() - _last)
            if wait > 0:
                await asyncio.sleep(wait)
            _last = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{config.CLAWBY_BASE}/api/relay",
                    headers={"X-API-Key": config.CLAWBY_API_KEY,
                             "Content-Type": "application/json"},
                    json={"name": name, "params": params or {}})
                if resp.status_code in (429, 500, 502, 503) and attempt < retries - 1:
                    log.warning("relay %s -> %s, backoff %ds", name,
                                resp.status_code, 2 * (attempt + 1))
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                resp.raise_for_status()
                body = resp.json()
            data = body.get("data")
            if isinstance(data, dict) and "code" in data:
                if str(data.get("code")) != "0":
                    raise RuntimeError(f"{name}: code={data.get('code')} msg={data.get('msg')}")
                data = data.get("data")
            return data
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if attempt == retries - 1:
                raise
            log.warning("relay %s retry %d: %s", name, attempt + 1, exc)
            await asyncio.sleep(2 * (attempt + 1))
    return None


async def relay_safe(name, params=None, timeout=30):
    try:
        return await relay(name, params, timeout)
    except Exception as exc:  # noqa: BLE001
        log.warning("relay %s failed: %s", name, exc)
        return None


async def market_by_slug(slug):
    """-> {token_up, token_down, tick, accepting, neg_risk} or None."""
    ev = await relay_safe("polymarket_events", {"slug": slug})
    rows = ev if isinstance(ev, list) else (ev or {}).get("data") or []
    if not rows:
        return None
    m = (rows[0].get("markets") or [{}])[0]
    tokens = m.get("clobTokenIds")
    if isinstance(tokens, str):
        try:
            tokens = json.loads(tokens)
        except ValueError:
            tokens = None
    if not tokens or len(tokens) < 2:
        return None
    try:
        tick = float(m.get("orderPriceMinTickSize") or 0.01)
    except (TypeError, ValueError):
        tick = 0.01
    return {"token_up": str(tokens[0]), "token_down": str(tokens[1]),
            "tick": tick, "accepting": bool(m.get("acceptingOrders")),
            "neg_risk": bool(m.get("negRisk")),
            "condition_id": m.get("conditionId") or ""}


_PX_CACHE = {}                     # token -> (monotonic_ts, result); shared by
_PX_TTL = 8                        # engine + admin pages to halve relay load


async def best_prices(token_id):
    """-> {bid, ask, mid} implied probabilities (None on failure). 8s TTL cache."""
    hit = _PX_CACHE.get(token_id)
    if hit and time.monotonic() - hit[0] < _PX_TTL:
        return hit[1]
    ob = await relay_safe("polymarket_orderbook", {"token_id": token_id})
    if not isinstance(ob, dict):
        return None
    try:
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        bid = max(float(b["price"]) for b in bids) if bids else None
        ask = min(float(a["price"]) for a in asks) if asks else None
        mid = (bid + ask) / 2 if bid is not None and ask is not None else None
        out = {"bid": bid, "ask": ask, "mid": mid}
        _PX_CACHE[token_id] = (time.monotonic(), out)
        if len(_PX_CACHE) > 600:
            _PX_CACHE.clear()
        return out
    except (TypeError, ValueError, KeyError):
        return None
