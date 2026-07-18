"""Backtest: replay every 5-min round in the 7-day window against BTC 1s data.

Odds model: sampled real rounds' Up-token price history is bucketed into a
(remaining-seconds, drift-bp) grid of median market prices; the simulator
looks prices up from that surface, so estimated entry prices reflect how the
market actually quotes these rounds. Spread cost SPREAD_C is charged on entry.

Strategies mirror app/strategy.py logic (shared math, standalone data feed).
IS = first 5 days, OOS = last 2 days.
"""
import gzip
import json
import math
import statistics
from bisect import bisect_right
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
ROUND = 300
SPREAD_C = 0.015          # half-spread cost charged on entry price
TP_NONE = 0               # take-profit disabled in the core sim (settle-only)


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


class Feed:
    """1s BTC closes with O(log n) time lookup."""

    def __init__(self, fname="btc_1s.json.gz"):
        with gzip.open(DATA / fname, "rt") as f:
            rows = json.load(f)
        self.ts = [r[0] for r in rows]
        self.px = [r[1] for r in rows]

    def at(self, t):
        i = bisect_right(self.ts, t)
        return self.px[i - 1] if i else None

    def vol(self, t, window=600, step=5):
        pts = [self.at(x) for x in range(int(t - window), int(t) + 1, step)]
        pts = [p for p in pts if p]
        if len(pts) < 20:
            return None
        rets = [pts[i] / pts[i - 1] - 1 for i in range(1, len(pts))]
        m = sum(rets) / len(rets)
        var = sum((r - m) ** 2 for r in rets) / len(rets)
        return (var ** 0.5) / (step ** 0.5)

    def span(self):
        return self.ts[0], self.ts[-1]


class OddsSurface:
    """(remaining_sec, drift_bp) -> median market Up price, from samples."""

    REM_EDGES = [0, 30, 60, 120, 180, 240, 300]
    BP_EDGES = [-999, -15, -8, -4, -1.5, 1.5, 4, 8, 15, 999]

    def __init__(self, feed):
        cells = {}
        samples = json.loads((DATA / "samples.json").read_text())
        for s in samples:
            start = s["start_ts"]
            open_p = feed.at(start)
            if not open_p:
                continue
            for t, up_price in s["series"]:
                if not (start <= t < start + ROUND):
                    continue
                cur = feed.at(t)
                if not cur:
                    continue
                drift_bp = (cur - open_p) / open_p * 10000
                rem = start + ROUND - t
                key = (self._bucket(self.REM_EDGES, rem),
                       self._bucket(self.BP_EDGES, drift_bp))
                cells.setdefault(key, []).append(up_price)
        self.grid = {k: statistics.median(v) for k, v in cells.items() if len(v) >= 3}
        self.n_samples = len(samples)

    @staticmethod
    def _bucket(edges, v):
        for i in range(len(edges) - 1):
            if edges[i] <= v < edges[i + 1]:
                return i
        return len(edges) - 2

    def up_price(self, remaining_sec, drift_bp):
        key = (self._bucket(self.REM_EDGES, remaining_sec),
               self._bucket(self.BP_EDGES, drift_bp))
        if key in self.grid:
            return self.grid[key]
        # fallback: nearest drift bucket at same remaining bucket
        r, b = key
        for db_ in (1, 2, 3, 4):
            for cand in ((r, b - db_), (r, b + db_)):
                if cand in self.grid:
                    return self.grid[cand]
        return 0.5


# -- strategies (mirror app/strategy.py math) ---------------------------------

def fair_value(feed, surface, start, entry_t, p):
    open_p = feed.at(start)
    cur = feed.at(entry_t)
    if not open_p or not cur:
        return None
    t_rem = start + ROUND - entry_t
    if t_rem < 20:
        return None
    sigma = feed.vol(entry_t)
    if not sigma:
        return None
    drift = (cur - open_p) / open_p
    p_up_theo = _phi(drift / (sigma * math.sqrt(t_rem)))
    mkt_up = surface.up_price(t_rem, drift * 10000)
    edge_min = p.get("edge_min", 0.06)
    if p_up_theo - mkt_up >= edge_min:
        return "up", min(mkt_up + SPREAD_C, 0.99)
    if (1 - p_up_theo) - (1 - mkt_up) >= edge_min:
        return "down", min((1 - mkt_up) + SPREAD_C, 0.99)
    return None


def tick_momo(feed, surface, start, entry_t, p):
    win = int(p.get("momo_window", 60))
    a, b = feed.at(entry_t - win), feed.at(entry_t)
    if not a or not b:
        return None
    move = (b - a) / a * 100
    if abs(move) < p.get("momo_min", 0.02):
        return None
    open_p = feed.at(start)
    drift_bp = (b - open_p) / open_p * 10000 if open_p else 0
    mkt_up = surface.up_price(start + ROUND - entry_t, drift_bp)
    side = "up" if move > 0 else "down"
    price = mkt_up if side == "up" else 1 - mkt_up
    return side, min(price + SPREAD_C, 0.99)


def open_burst(feed, surface, start, entry_t, p):
    open_p, cur = feed.at(start), feed.at(entry_t)
    if not open_p or not cur:
        return None
    move = (cur - open_p) / open_p * 100
    if abs(move) < p.get("burst_min", 0.05):
        return None
    mkt_up = surface.up_price(start + ROUND - entry_t, move * 100)
    side = "up" if move > 0 else "down"
    price = mkt_up if side == "up" else 1 - mkt_up
    return side, min(price + SPREAD_C, 0.99)


def prev_reverse(feed, surface, start, entry_t, p):
    p0, p1 = feed.at(start - ROUND), feed.at(start)
    if not p0 or not p1:
        return None
    prev_move = (p1 - p0) / p0 * 100
    if abs(prev_move) < p.get("rev_min", 0.15):
        return None
    cur = feed.at(entry_t)
    drift_bp = (cur - p1) / p1 * 10000 if cur and p1 else 0
    mkt_up = surface.up_price(start + ROUND - entry_t, drift_bp)
    side = "down" if prev_move > 0 else "up"
    price = mkt_up if side == "up" else 1 - mkt_up
    return side, min(price + SPREAD_C, 0.99)


STRATS = {"fair_value": fair_value, "tick_momo": tick_momo,
          "open_burst": open_burst, "prev_reverse": prev_reverse}


def run(strategy_key, params, feed, surface, t0, t1, entry_delay=20,
        overpay_cap=0.85, usd=5.0):
    """Simulate all rounds in [t0, t1). Returns metrics dict."""
    fn = STRATS[strategy_key]
    trades = []
    start = (int(t0) // ROUND + 1) * ROUND
    while start + ROUND <= t1:
        entry_t = start + entry_delay
        sig = fn(feed, surface, start, entry_t, params)
        if sig:
            side, price = sig
            if price <= overpay_cap and price >= 0.03:
                open_p = feed.at(start)
                close_p = feed.at(start + ROUND - 1)
                if open_p and close_p:
                    result = "up" if close_p >= open_p else "down"
                    shares = usd / price
                    pnl = shares * 1.0 - usd if result == side else -usd
                    trades.append(pnl)
        start += ROUND
    n = len(trades)
    if not n:
        return {"trades": 0, "win_rate": 0, "ev_usd": 0, "net_usd": 0, "max_dd": 0}
    wins = sum(1 for x in trades if x > 0)
    cum = peak = dd = 0.0
    for x in trades:
        cum += x
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return {"trades": n, "win_rate": round(wins / n * 100, 1),
            "ev_usd": round(sum(trades) / n, 4),
            "net_usd": round(sum(trades), 2), "max_dd": round(dd, 2)}
