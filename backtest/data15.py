"""Fetch 15 days of BTC 1s closes into data/btc_1s_15d.json.gz (idempotent).
Run: python -m backtest.data15"""
import gzip
import json
import logging
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("bt.data15")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATA = Path(__file__).resolve().parent / "data"
DAYS = 15
END_TS = int(time.time()) // 300 * 300 - 600
START_TS = END_TS - DAYS * 86400


def main():
    out = DATA / "btc_1s_15d.json.gz"
    if out.exists():
        log.info("cached, skip")
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
        if n % 100 == 0:
            log.info("%d rows (%.0f%%)", len(rows),
                     (cur / 1000 - START_TS) / (END_TS - START_TS) * 100)
        time.sleep(0.12)
    with gzip.open(out, "wt") as f:
        json.dump(rows, f)
    log.info("done: %d rows -> %s", len(rows), out)


if __name__ == "__main__":
    main()
