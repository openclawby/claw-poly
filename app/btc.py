"""BTC real-time price: Binance spot bookTicker WS + second-level ring buffer
(coverage ≥ 43 min so a full 6-round horizon plus history fits)."""
import asyncio
import json
import logging
import time
from bisect import bisect_right
from collections import deque

import httpx
import websockets

log = logging.getLogger("btc")

_BUF_MAX = 7500                    # 1/s -> ~2 hours (pre-bet lookbacks need depth)
_buf = deque(maxlen=_BUF_MAX)      # (ts_float, mid)
_last_price = 0.0
_last_ts = 0.0


def price(max_age=15):
    if _last_price and time.time() - _last_ts <= max_age:
        return _last_price
    return 0.0


def price_at(ts):
    """Last recorded price at-or-before ts (None if buffer doesn't cover)."""
    if not _buf:
        return None
    arr_ts = [p[0] for p in _buf]
    i = bisect_right(arr_ts, ts)
    if i == 0:
        return None
    return _buf[i - 1][1]


def change(sec):
    """Percent move over the last `sec` seconds (None if not covered)."""
    now = time.time()
    old = price_at(now - sec)
    cur = price()
    if old and cur:
        return (cur - old) / old * 100
    return None


def realized_vol(window_sec=600, step=5):
    """Per-second stdev of log-ish returns over the window (fraction/sec^0.5).
    Used by the fair-value strategy; None until the buffer covers the window."""
    now = time.time()
    pts = []
    t = now - window_sec
    while t <= now:
        p = price_at(t)
        if p:
            pts.append(p)
        t += step
    if len(pts) < 20:
        return None
    rets = [(pts[i] / pts[i - 1] - 1) for i in range(1, len(pts))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return (var ** 0.5) / (step ** 0.5)


def buffer_span():
    if not _buf:
        return 0.0
    return time.time() - _buf[0][0]


async def _backfill():
    """Seed the ring buffer from Binance 1s klines so a restart never leaves
    the strategy signal-blind (no more cold-start skipped rounds)."""
    global _last_price, _last_ts
    try:
        end = int(time.time() * 1000)
        rows = []
        async with httpx.AsyncClient(timeout=15) as client:
            for _ in range(8):
                r = await client.get(
                    "https://api.binance.com/api/v3/klines",
                    params={"symbol": "BTCUSDT", "interval": "1s",
                            "limit": 1000, "endTime": end})
                r.raise_for_status()
                batch = r.json()
                if not batch:
                    break
                rows = batch + rows
                end = batch[0][0] - 1
                if len(rows) >= _BUF_MAX - 300:
                    break
        for k in rows[-(_BUF_MAX - 60):]:
            _buf.append((k[0] / 1000.0, float(k[4])))
        if rows:
            _last_price = float(rows[-1][4])
            _last_ts = rows[-1][0] / 1000.0
            log.info("btc buffer backfilled: %d pts (%.1f min)",
                     len(_buf), buffer_span() / 60)
    except Exception as exc:  # noqa: BLE001
        log.warning("btc backfill failed (will warm up from the public stream): %s", exc)


async def ws_loop():
    global _last_price, _last_ts
    backoff = 1
    url = "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"
    last_store = 0.0
    if not _buf:
        await _backfill()
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, close_timeout=5) as conn:
                log.info("btc bookTicker connected")
                backoff = 1
                async for raw in conn:
                    d = json.loads(raw)
                    bid, ask = float(d.get("b") or 0), float(d.get("a") or 0)
                    if not (bid and ask):
                        continue
                    now = time.time()
                    _last_price = (bid + ask) / 2
                    _last_ts = now
                    if now - last_store >= 1.0:    # 1/s into the ring buffer
                        _buf.append((now, _last_price))
                        last_store = now
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("btc ws dropped: %s — retry in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
