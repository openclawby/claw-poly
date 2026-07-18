"""Backtest data: 7 days of BTC 1s closes (Binance spot) + ~150 sampled
finished btc-updown-5m rounds' Up-token price history (Clawby relay).

Idempotent: cached files are skipped. Run: python -m backtest.data
"""
import gzip
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("bt.data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

DAYS = 7
NOW = int(time.time())
END_TS = NOW // 300 * 300 - 600          # last fully settled boundary, margin
START_TS = END_TS - DAYS * 86400
SAMPLE_N = 150

CLAWBY_KEY = os.environ.get("CLAWBY_API_KEY", "")


def relay(name, params, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(
                "https://api.openclawby.com/api/relay",
                data=json.dumps({"name": name, "params": params}).encode(),
                headers={"X-API-Key": CLAWBY_KEY, "Content-Type": "application/json"})
            body = json.loads(urllib.request.urlopen(req, timeout=30).read())
            d = body.get("data")
            if isinstance(d, dict) and "code" in d:
                d = d.get("data")
            time.sleep(0.35)              # free-plan friendly throttle
            return d
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i < retries - 1:
                time.sleep(5 * (i + 1))
                continue
            raise
    return None


def fetch_btc_1s():
    out = DATA / "btc_1s.json.gz"
    if out.exists():
        log.info("btc_1s cached, skip")
        return
    rows = []
    cur = START_TS * 1000
    end_ms = END_TS * 1000
    n = 0
    while cur < end_ms:
        url = ("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1s"
               f"&startTime={cur}&endTime={end_ms - 1}&limit=1000")
        with urllib.request.urlopen(url, timeout=20) as r:
            ks = json.load(r)
        if not ks:
            cur += 1000 * 1000
            continue
        rows.extend([[int(k[0] // 1000), float(k[4])] for k in ks])
        cur = ks[-1][0] + 1000
        n += 1
        if n % 50 == 0:
            log.info("btc_1s: %d rows (%.0f%%)", len(rows),
                     (cur / 1000 - START_TS) / (END_TS - START_TS) * 100)
        time.sleep(0.15)
    with gzip.open(out, "wt") as f:
        json.dump(rows, f)
    log.info("btc_1s done: %d rows -> %s", len(rows), out)


def fetch_samples():
    out = DATA / "samples.json"
    done = []
    if out.exists():
        done = json.loads(out.read_text())
        if len(done) >= SAMPLE_N:
            log.info("samples cached (%d), skip", len(done))
            return
    have = {s["slug"] for s in done}
    step = (END_TS - START_TS - 3600) // SAMPLE_N // 300 * 300
    targets = [START_TS + 1800 + i * step for i in range(SAMPLE_N)]
    for i, ts in enumerate(targets):
        boundary = ts // 300 * 300
        slug = f"btc-updown-5m-{boundary}"
        if slug in have:
            continue
        try:
            ev = relay("polymarket_events", {"slug": slug, "closed": True})
            rows = ev if isinstance(ev, list) else (ev or {}).get("data") or []
            if not rows:
                ev = relay("polymarket_events", {"slug": slug})
                rows = ev if isinstance(ev, list) else (ev or {}).get("data") or []
            if not rows:
                continue
            m = (rows[0].get("markets") or [{}])[0]
            tokens = m.get("clobTokenIds")
            if isinstance(tokens, str):
                tokens = json.loads(tokens)
            if not tokens:
                continue
            hist = relay("polymarket_price_history",
                         {"market": tokens[0], "startTs": boundary - 300,
                          "endTs": boundary + 300, "fidelity": 1})
            series = (hist or {}).get("history") if isinstance(hist, dict) else hist
            if not series:
                continue
            pts = [[int(p.get("t")), float(p.get("p"))] for p in series
                   if isinstance(p, dict) and p.get("t") is not None]
            outcome_prices = m.get("outcomePrices")
            if isinstance(outcome_prices, str):
                outcome_prices = json.loads(outcome_prices)
            done.append({"slug": slug, "start_ts": boundary,
                         "series": pts, "final": outcome_prices})
            if len(done) % 10 == 0:
                out.write_text(json.dumps(done))
                log.info("samples: %d/%d", len(done), SAMPLE_N)
        except Exception as exc:  # noqa: BLE001
            log.warning("sample %s failed: %s", slug, exc)
    out.write_text(json.dumps(done))
    log.info("samples done: %d -> %s", len(done), out)


if __name__ == "__main__":
    log.info("window: %s -> %s (%d days)", START_TS, END_TS, DAYS)
    fetch_btc_1s()
    fetch_samples()
    log.info("all done")
