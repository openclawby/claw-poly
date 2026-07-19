"""Round discovery & settlement for the btc-updown-5m series.

Slugs are pure local math: btc-updown-5m-<unix aligned to 300s>. Tokens/tick
are fetched once per round via the relay and cached in the rounds table.
Settlement rule (from the market description): close >= open  ->  Up.
"""
import logging
import time

from . import btc, clawby, config, db

log = logging.getLogger("markets")


def slug_at(ts):
    b = int(ts) // config.ROUND_SEC * config.ROUND_SEC
    return f"{config.SERIES_PREFIX}-{b}", b


def upcoming_slugs(n, now=None):
    """Current round + next n-1 (the tradeable horizon)."""
    now = now or time.time()
    _, b = slug_at(now)
    out = []
    for i in range(n):
        start = b + i * config.ROUND_SEC
        out.append((f"{config.SERIES_PREFIX}-{start}", start))
    return out


async def ensure_round(slug, start_ts):
    """Round row with tokens cached; returns the row or None (not tradeable)."""
    row = db.get_round(slug)
    if row and row.get("token_up"):
        return row
    info = await clawby.market_by_slug(slug)
    if not info:
        return row
    db.upsert_round(slug, start_ts=start_ts, end_ts=start_ts + config.ROUND_SEC,
                    token_up=info["token_up"], token_down=info["token_down"],
                    tick=info["tick"])
    return db.get_round(slug)


def capture_open(round_row):
    """Record the BTC price at round start (called once start_ts passes)."""
    if round_row.get("open_price"):
        return
    p = btc.price_at(round_row["start_ts"]) or btc.price()
    if p:
        db.upsert_round(round_row["slug"], open_price=p)


def settle_result(round_row):
    """Local result judgment: close >= open -> 'up' else 'down' (display &
    simulated PnL; settlement data comes from public market resolution)."""
    open_p = round_row.get("open_price") or btc.price_at(round_row["start_ts"])
    close_p = btc.price_at(round_row["end_ts"]) or btc.price()
    if not open_p or not close_p:
        return None, open_p, close_p
    return ("up" if close_p >= open_p else "down"), open_p, close_p
