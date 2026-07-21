"""多信号集成回测:各类因子单独 + 组合("N个一致才下注"),看能否突破51%天花板。
15天秒级->1分钟bar,盘口开盘时刻用历史算因子,预测该盘close vs open。无前视。
Run: python -m backtest.ensemble  ->  backtest/ENSEMBLE.md
"""
import bisect
import itertools
from pathlib import Path
from .sim import Feed, ROUND
from .indicators import build_minute_bars, rsi, ema, macd

HERE = Path(__file__).resolve().parent


def _ret(cl, n):
    return (cl[-1] / cl[-1 - n] - 1) if len(cl) > n else 0.0


# 因子库:每个返回 +1(看涨) / -1(看跌) / 0(弃权)。全部按"反转"倾向(实盘验证 revert 占优)
FACTORS = {
    "rsi_rev": lambda cl: (-1 if (rsi(cl) or 50) > 55 else (1 if (rsi(cl) or 50) < 45 else 0)),
    "macd_rev": lambda cl: (0 if macd(cl) is None else (-1 if macd(cl) > 0 else 1)),
    "ema_rev": lambda cl: (0 if ema(cl, 21) is None else (-1 if ema(cl, 9) > ema(cl, 21) else 1)),
    "mom5_rev": lambda cl: (-1 if _ret(cl, 5) > 0 else 1),        # 5分钟动量反转
    "mom15_rev": lambda cl: (-1 if _ret(cl, 15) > 0 else 1),      # 15分钟动量反转
    "mom1_rev": lambda cl: (-1 if _ret(cl, 1) > 0 else 1),        # 1分钟动量反转
    "accel_rev": lambda cl: (-1 if _ret(cl, 3) > _ret(cl, 10) else 1),  # 加速度
}


def precompute(bars, feed):
    """对每个盘口:算所有因子值 + 实际结果。返回 list of (results_dict, actual_up)。"""
    ts = [b[0] for b in bars]
    cl = [b[1] for b in bars]
    lo, hi = feed.span()
    out = []
    start = (int(lo + 3000) // ROUND + 1) * ROUND
    while start + ROUND <= hi:
        idx = bisect.bisect_right(ts, start)
        if idx >= 40:
            o, c = feed.at(start), feed.at(start + ROUND - 1)
            if o and c:
                sub = cl[:idx]
                fv = {k: fn(sub) for k, fn in FACTORS.items()}
                out.append((fv, c >= o))
        start += ROUND
    return out


def eval_combo(data, keys, need_agree=None):
    """组合:keys 里的因子投票,net vote 决定方向;need_agree=要求至少几个非零一致。"""
    hits = n = 0
    for fv, up in data:
        votes = [fv[k] for k in keys]
        nz = [v for v in votes if v != 0]
        if not nz:
            continue
        s = sum(nz)
        if need_agree is not None:
            # 要求净票数绝对值 >= need_agree(强共识)
            if abs(s) < need_agree:
                continue
        if s == 0:
            continue
        side_up = s > 0
        n += 1
        hits += (side_up == up)
    return n, (hits / n * 100 if n else 0)


def main():
    feed = Feed("btc_1s_15d.json.gz")
    bars = build_minute_bars(feed)
    data = precompute(bars, feed)
    print(f"评估盘口: {len(data)} / 15天")

    L = ["# 多信号集成回测(15天,全反转倾向,无前视)", "",
         f"- {len(data)} 盘;方向命中率;盈亏线约 51%;实盘再扣提前量+点差",
         "- 因子均按 revert(反转)构造:+1看涨/-1看跌/0弃权", ""]

    # 1) 单因子
    L += ["## 单因子命中率", "", "| 因子 | 样本 | 命中率 |", "|---|---|---|"]
    singles = []
    for k in FACTORS:
        n, wr = eval_combo(data, [k])
        singles.append((k, n, wr))
    for k, n, wr in sorted(singles, key=lambda x: -x[2]):
        L.append(f"| {k} | {n} | {wr:.2f}% |")

    # 2) 全因子投票(多数决)+ 强共识(要求净票≥阈值)
    allk = list(FACTORS)
    L += ["", "## 全因子投票(净票数越高=共识越强,单量越少)", "",
          "| 要求净票≥ | 样本 | 命中率 |", "|---|---|---|"]
    combo_best = []
    for agree in (1, 2, 3, 4, 5):
        n, wr = eval_combo(data, allk, need_agree=agree)
        L.append(f"| {agree} | {n} | {wr:.2f}% |")
        combo_best.append((f"全因子净票≥{agree}", n, wr))

    # 3) 两两/三因子最优组合(要求全部一致)
    L += ["", "## 因子子集全一致(所有选中因子方向相同才下注)Top 15", "",
          "| 因子组合 | 样本 | 命中率 |", "|---|---|---|"]
    subset_results = []
    for r in (2, 3, 4):
        for combo in itertools.combinations(allk, r):
            # 全一致:每个因子非零且方向相同
            hits = n = 0
            for fv, up in data:
                votes = [fv[k] for k in combo]
                if 0 in votes:
                    continue
                if all(v > 0 for v in votes):
                    side_up = True
                elif all(v < 0 for v in votes):
                    side_up = False
                else:
                    continue
                n += 1
                hits += (side_up == up)
            if n >= 150:                     # 样本门槛
                subset_results.append((combo, n, hits / n * 100))
    subset_results.sort(key=lambda x: -x[2])
    for combo, n, wr in subset_results[:15]:
        L.append(f"| {'+'.join(combo)} | {n} | {wr:.2f}% |")

    # 结论
    best = max(subset_results, key=lambda x: x[2]) if subset_results else None
    L += ["", "## 结论", ""]
    if best and best[2] > 53:
        L.append(f"最优集成 **{'+'.join(best[0])}** 命中 {best[2]:.2f}%({best[1]}盘)"
                 f",相比单因子天花板有提升 —— 但需 OOS 验证是否过拟合。")
    else:
        b = best[2] if best else 0
        L.append(f"最优集成仅 {b:.2f}%,**未能明显突破 51-52% 天花板**。"
                 "多因子只是同一均值回归信号的不同包装,高度相关,集成收益有限。"
                 "共识越强样本越少,命中率提升多为小样本噪音。")
    L.append("\n> 单一市况15天;实盘扣提前量+点差后更低。集成的高分需独立OOS复核。")

    (HERE / "ENSEMBLE.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
