"""Grid-search each strategy on IS (first 5 days), validate picks on OOS
(last 2 days), write backtest/REPORT.md. Run: python -m backtest.report"""
import itertools
import json
from pathlib import Path

from .sim import Feed, OddsSurface, run

GRIDS = {
    "fair_value": {"edge_min": [0.04, 0.06, 0.09], "_entry": [20, 45, 90]},
    "tick_momo": {"momo_window": [30, 60, 120], "momo_min": [0.02, 0.05],
                  "_entry": [10, 20]},
    "open_burst": {"burst_min": [0.04, 0.07, 0.12], "_entry": [30, 60, 120]},
    "prev_reverse": {"rev_min": [0.1, 0.18, 0.3], "_entry": [10, 30]},
}


def expand(grid):
    keys = list(grid)
    for vals in itertools.product(*grid.values()):
        d = dict(zip(keys, vals))
        entry = d.pop("_entry")
        yield d, entry


def main():
    feed = Feed()
    surface = OddsSurface(feed)
    lo, hi = feed.span()
    is_end = lo + 5 * 86400
    print(f"data span {hi - lo:.0f}s · odds surface {len(surface.grid)} cells "
          f"from {surface.n_samples} sampled rounds")

    lines = ["# polymarketbot 回测报告(7 天:IS 前 5 天 / OOS 后 2 天)", "",
             f"- 赔率曲面:{surface.n_samples} 个真实盘口样本 → {len(surface.grid)} 格",
             f"- 成本:入场价含半点差 {0.015};每盘 $5;结算制(不含止盈提前退出)", "",
             "| 策略 | 参数 | 入场延迟 | IS 盘数 | IS 胜率 | IS 期望$ | IS 净$ | OOS 盘数 | OOS 胜率 | OOS 净$ | 判定 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]

    picks = []
    for key, grid in GRIDS.items():
        best = None
        for params, entry in expand(grid):
            r = run(key, params, feed, surface, lo, is_end, entry_delay=entry)
            if r["trades"] < 25:
                continue
            score = r["ev_usd"]
            if best is None or score > best[0]:
                best = (score, params, entry, r)
        if best is None:
            lines.append(f"| {key} | - | - | 样本不足 | | | | | | | ❌ |")
            continue
        _, params, entry, is_r = best
        oos_r = run(key, params, feed, surface, is_end, hi, entry_delay=entry)
        ok = is_r["ev_usd"] > 0 and oos_r["net_usd"] > 0 and oos_r["trades"] >= 10
        verdict = "✅ 上架" if ok else ("⚠️ 观察" if is_r["ev_usd"] > 0 else "❌")
        lines.append(
            f"| {key} | {json.dumps(params)} | {entry}s | {is_r['trades']} "
            f"| {is_r['win_rate']}% | {is_r['ev_usd']} | {is_r['net_usd']} "
            f"| {oos_r['trades']} | {oos_r['win_rate']}% | {oos_r['net_usd']} | {verdict} |")
        picks.append({"strategy": key, "params": params, "entry_delay": entry,
                      "is": is_r, "oos": oos_r, "verdict": verdict})

    lines += ["", "## 结论", ""]
    good = [p for p in picks if p["verdict"] == "✅ 上架"]
    watch = [p for p in picks if p["verdict"] == "⚠️ 观察"]
    if good:
        lines.append("IS/OOS 双正的策略:" + ", ".join(p["strategy"] for p in good)
                     + " —— 建议 paper 观察后启用。")
    if watch:
        lines.append("仅 IS 为正(OOS 不达标):" + ", ".join(p["strategy"] for p in watch))
    if not good and not watch:
        lines.append("**没有策略在成本后取得正期望** —— 5 分钟二元盘接近有效定价,"
                     "如实报告;建议不启用实盘。")
    lines.append("")
    lines.append("> 提醒:7 天单一市况样本;赔率曲面为中位数近似,实盘点差与"
                 "深度会进一步压缩收益。回测未含止盈提前退出(保守口径)。")

    out = Path(__file__).resolve().parent / "REPORT.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    (Path(__file__).resolve().parent / "picks.json").write_text(json.dumps(picks, indent=1))
    print("\n".join(lines))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
