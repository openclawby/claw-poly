"""Coverage-bet economics: buy EVERY round pre-open (user requirement).

Two evidence layers:
  A. Full 7-day 1s feed — "taker 0.51 on every round" exact accuracy/EV for the
     weak revert/momo side signal at several leads (fills are certain).
  B. 150 real Up-token price paths — resting maker bids at q: fill rate and
     conditional accuracy (adverse selection), 60s granularity (lower bound
     on fills; wicks between prints are missed).

Run: python -m backtest.cover  ->  backtest/COVER.md
"""
import json
from pathlib import Path

from .sim import Feed, ROUND

HERE = Path(__file__).resolve().parent
USD = 5.0
LB = 600


def weak_side(feed, t0, mode="revert"):
    a, b = feed.at(t0 - LB), feed.at(t0)
    if not a or not b:
        return None
    side = "up" if b >= a else "down"
    if mode == "revert":
        side = "down" if side == "up" else "up"
    return side


def taker_every_round(feed, lead, mode, price):
    lo, hi = feed.span()
    trades = hits = 0
    start = (int(lo) // ROUND + 1) * ROUND + ROUND * 4
    while start + ROUND <= hi:
        side = weak_side(feed, start - lead, mode)
        o, c = feed.at(start), feed.at(start + ROUND - 1)
        if side and o and c:
            trades += 1
            hits += (("up" if c >= o else "down") == side)
        start += ROUND
    acc = hits / trades * 100 if trades else 0
    win_gain = USD / price - USD
    net = hits * win_gain - (trades - hits) * USD
    return {"trades": trades, "acc": round(acc, 2), "net": round(net, 2),
            "ev": round(net / trades, 4) if trades else 0,
            "day": round(net / 7, 2)}


def maker_paths(feed, q, mode):
    """Resting bid at q from 5 min pre-open until round end, real paths."""
    samples = json.loads((HERE / "data" / "samples.json").read_text())
    placed = filled = hits = 0
    for s in samples:
        st = s["start_ts"]
        side = weak_side(feed, st - 300, mode)
        o, c = feed.at(st), feed.at(st + ROUND - 1)
        if not side or not o or not c:
            continue
        placed += 1
        pts = [(t, p) for t, p in s["series"] if st - 300 <= t < st + ROUND]
        hit_px = [p for t, p in pts if (p <= q if side == "up" else p >= 1 - q)]
        if not hit_px:
            continue
        filled += 1
        hits += (("up" if c >= o else "down") == side)
    fill_rate = filled / placed * 100 if placed else 0
    acc = hits / filled * 100 if filled else 0
    win_gain = USD / q - USD
    net = hits * win_gain - (filled - hits) * USD
    return {"placed": placed, "filled": filled, "fill%": round(fill_rate, 1),
            "acc": round(acc, 1), "net": round(net, 2),
            "ev_per_fill": round(net / filled, 4) if filled else 0}


def main():
    feed = Feed()
    L = ["# 全覆盖补仓经济学(每盘必买)", "",
         "## A. 吃单 0.51 每盘必买(7 天全量,成交确定)", "",
         "| 弱信号 | 提前量 | 盘数 | 方向准确率 | 总净$($5/盘) | 折算每天 |",
         "|---|---|---|---|---|---|"]
    for mode in ("revert", "momo"):
        for lead in (300, 600, 1800):
            r = taker_every_round(feed, lead, mode, 0.51)
            L.append(f"| {mode} | {lead//60}min | {r['trades']} | {r['acc']}% "
                     f"| {r['net']} | {r['day']}/天 |")

    L += ["", "## B. 低价挂单(150 个真实价格路径,60s 粒度→成交率是下限)", "",
          "| 挂单价 | 信号 | 挂出 | 成交 | 成交率 | 成交后胜率 | 保本胜率 | 净$ | 每成交期望 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for q in (0.44, 0.46, 0.48, 0.50):
        for mode in ("revert", "momo"):
            r = maker_paths(feed, q, mode)
            be = q * 100
            L.append(f"| {q} | {mode} | {r['placed']} | {r['filled']} | {r['fill%']}% "
                     f"| {r['acc']}% | {be:.0f}% | {r['net']} | {r['ev_per_fill']} |")

    L += ["", "> A 层:准确率≈50% 时,0.51 成本意味着约 -2%/盘 的确定磨损。",
          "> B 层:成交后胜率 vs 保本胜率(=挂单价)的差值就是逆向选择的代价;",
          "> 60 秒粒度会漏掉部分成交机会,真实成交率略高于表中值。"]
    (HERE / "COVER.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
