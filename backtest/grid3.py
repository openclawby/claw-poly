"""三参数全网格回测:lead_sec × lookback_sec × min_move_pct
分层统计触发单/补仓单/整体(signal=revert,与实盘一致),15 天数据。
口径:@0.51 吃单,$5.1/单,赢结算 $1。
Run: python -m backtest.grid3  ->  backtest/GRID3.md
"""
from pathlib import Path
from .sim import Feed, ROUND

HERE = Path(__file__).resolve().parent
LEADS = [60, 120, 180, 300, 450, 600]
LOOKBACKS = [300, 600, 900, 1200, 1800]
THRESHOLDS = [0.10, 0.15, 0.20, 0.30, 0.50]
FILL = 0.51
USD = 5.1
WIN_GAIN = USD / FILL - USD


def build(feed):
    """预算每盘在各 (lead, lb) 下的 move,和结果,一次算好。"""
    lo, hi = feed.span()
    warm = lo + max(LOOKBACKS) + max(LEADS) + 60
    rounds = []
    start = (int(warm) // ROUND + 1) * ROUND
    while start + ROUND <= hi:
        o, c = feed.at(start), feed.at(start + ROUND - 1)
        if o and c:
            res = "up" if c >= o else "down"
            moves = {}
            for lead in LEADS:
                t0 = start - lead
                b = feed.at(t0)
                for lb in LOOKBACKS:
                    a = feed.at(t0 - lb)
                    moves[(lead, lb)] = (b - a) / a * 100 if (a and b) else None
            rounds.append((res, moves))
        start += ROUND
    return rounds


def eval_cfg(rounds, lead, lb, thr, sig="revert"):
    """返回 {tier: (hits, n, net)} for trigger / cover / all."""
    out = {"trigger": [0, 0], "cover": [0, 0]}
    for res, moves in rounds:
        mv = moves.get((lead, lb))
        if mv is None:
            continue
        tier = "trigger" if abs(mv) >= thr else "cover"
        side_up = (mv > 0) if sig == "momo" else (mv <= 0)
        out[tier][1] += 1
        out[tier][0] += (("up" if side_up else "down") == res)
    r = {}
    for tier, (h, n) in out.items():
        net = h * WIN_GAIN - (n - h) * USD
        r[tier] = (h, n, round(net, 2))
    ah = out["trigger"][0] + out["cover"][0]
    an = out["trigger"][1] + out["cover"][1]
    r["all"] = (ah, an, round(ah * WIN_GAIN - (an - ah) * USD, 2))
    return r


def main():
    feed = Feed("btc_1s_15d.json.gz")
    rounds = build(feed)
    print(f"数据:{len(rounds)} 盘 / 15 天")

    L = ["# 三参数全网格回测(lead × lookback × min_move,signal=revert,15 天)", "",
         f"- {len(rounds)} 盘;@{FILL} 吃单;$5.1/单;赢结算 $1;胜率含点差盈亏线约 51%",
         "- **触发单**=|move|≥阈值;**补仓单**=|move|<阈值;整体=两者合计", ""]

    # 全网格结果收集
    results = []
    for lead in LEADS:
        for lb in LOOKBACKS:
            for thr in THRESHOLDS:
                r = eval_cfg(rounds, lead, lb, thr)
                results.append((lead, lb, thr, r))

    # 表 1:整体净利总览(lead × lb,固定几个 thr)
    for thr in THRESHOLDS:
        L += [f"## 整体净利:min_move={thr}%(行=lead 提前秒,列=lookback 回看秒)", "",
              "| lead\\lookback | " + " | ".join(f"{lb}s" for lb in LOOKBACKS) + " |",
              "|---|" + "---|" * len(LOOKBACKS)]
        for lead in LEADS:
            cells = []
            for lb in LOOKBACKS:
                net = next(x[3]["all"][2] for x in results
                           if x[0] == lead and x[1] == lb and x[2] == thr)
                cells.append(f"${net:+.0f}")
            L.append(f"| **{lead}s** | " + " | ".join(cells) + " |")
        L.append("")

    # 表 2:分层 Top 结果(整体净利排序)
    results.sort(key=lambda x: x[3]["all"][2], reverse=True)
    L += ["## 整体净利 Top 20(全网格排序)", "",
          "| lead | lookback | min_move | 触发单(盘/胜率/净) | 补仓单(盘/胜率/净) | 整体净$ |",
          "|---|---|---|---|---|---|"]
    for lead, lb, thr, r in results[:20]:
        th, tn, tnet = r["trigger"]
        ch, cn, cnet = r["cover"]
        _, an, anet = r["all"]
        tw = f"{tn}/{th/tn*100:.0f}%/${tnet:+.0f}" if tn else "0"
        cw = f"{cn}/{ch/cn*100:.0f}%/${cnet:+.0f}" if cn else "0"
        L.append(f"| {lead}s | {lb}s | {thr}% | {tw} | {cw} | **${anet:+.0f}** |")

    # 表 3:触发单最优(只看触发单净利)
    trig_sorted = sorted(results, key=lambda x: x[3]["trigger"][2], reverse=True)
    L += ["", "## 只看触发单净利 Top 10", "",
          "| lead | lookback | min_move | 触发盘数 | 触发胜率 | 触发净$ |",
          "|---|---|---|---|---|---|"]
    for lead, lb, thr, r in trig_sorted[:10]:
        h, n, net = r["trigger"]
        L.append(f"| {lead}s | {lb}s | {thr}% | {n} | {h/n*100:.1f}% | ${net:+.0f} |" if n else "")

    # 表 4:补仓单最优
    cov_sorted = sorted(results, key=lambda x: x[3]["cover"][2], reverse=True)
    L += ["", "## 只看补仓单净利 Top 10", "",
          "| lead | lookback | min_move | 补仓盘数 | 补仓胜率 | 补仓净$ |",
          "|---|---|---|---|---|---|"]
    for lead, lb, thr, r in cov_sorted[:10]:
        h, n, net = r["cover"]
        L.append(f"| {lead}s | {lb}s | {thr}% | {n} | {h/n*100:.1f}% | ${net:+.0f} |" if n else "")

    L += ["", "> 口径:15 天单一市况;全覆盖(cover=1)每盘必下;",
          "> 实盘点差/滑点/服务器延迟会压缩收益,提前量太短有挂单来不及的执行风险。"]

    out = HERE / "GRID3.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:80]))
    print(f"\n… 完整报告 -> {out}")


if __name__ == "__main__":
    main()
