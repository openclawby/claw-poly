"""二次 OOS 验证:用完全独立的 30 天数据(不同市况)验证多因子集成信号。
原 15 天数据用于"发现"信号,这 30 天数据从未参与,是真正的样本外考验。
Run: python -m backtest.verify2
"""
import bisect
import itertools
from .sim import Feed, ROUND
from .indicators import build_minute_bars
from .ensemble import precompute, FACTORS


def evalset(data, combo):
    hits = n = 0
    for fv, up in data:
        v = [fv[k] for k in combo]
        if 0 in v:
            continue
        if all(x > 0 for x in v):
            su = True
        elif all(x < 0 for x in v):
            su = False
        else:
            continue
        n += 1
        hits += (su == up)
    return n, (hits / n * 100 if n else 0)


def main():
    print("加载原 15 天数据(发现集)...")
    f1 = Feed("btc_1s_15d.json.gz")
    d1 = precompute(build_minute_bars(f1), f1)
    print(f"  {len(d1)} 盘")

    print("加载独立 30 天数据(二次验证集,不同市况)...")
    f2 = Feed("btc_1s_oos.json.gz")
    d2 = precompute(build_minute_bars(f2), f2)
    print(f"  {len(d2)} 盘\n")

    # 在原 15 天上选出的最优组合(来自 ensemble 的 OOS 结果),到 30 天独立验证
    candidates = [
        ("macd_rev", "mom5_rev", "mom1_rev", "accel_rev"),
        ("rsi_rev", "mom5_rev", "mom1_rev", "accel_rev"),
        ("ema_rev", "mom5_rev", "mom1_rev", "accel_rev"),
        ("mom5_rev", "mom15_rev", "mom1_rev", "accel_rev"),
        ("macd_rev", "mom5_rev", "accel_rev"),
        ("rsi_rev", "macd_rev", "mom15_rev"),          # 纯"有效因子"对照组
    ]

    print("=== 组合在两段数据的命中率对比 ===")
    print(f"  {'组合':44s} {'15天(发现)':>16} {'30天(独立验证)':>18}")
    print("  " + "-" * 82)
    for combo in candidates:
        n1, wr1 = evalset(d1, combo)
        n2, wr2 = evalset(d2, combo)
        verdict = "✅稳健" if wr2 > 53 else ("⚠️衰减但过线" if wr2 > 51 else "❌失效")
        print(f"  {'+'.join(combo):44s} {n1:>5}盘 {wr1:>5.1f}%   {n2:>5}盘 {wr2:>5.1f}%  {verdict}")

    # 全因子净票强共识,两段对比
    print("\n=== 全因子投票(净票≥N)两段对比 ===")
    allk = list(FACTORS)

    def vote(data, agree):
        hits = n = 0
        for fv, up in data:
            nz = [v for v in (fv[k] for k in allk) if v != 0]
            s = sum(nz)
            if abs(s) < agree or s == 0:
                continue
            n += 1
            hits += ((s > 0) == up)
        return n, (hits / n * 100 if n else 0)

    print(f"  {'净票≥':>6} {'15天':>14} {'30天(独立)':>16}")
    for a in (2, 3, 4, 5):
        n1, w1 = vote(d1, a)
        n2, w2 = vote(d2, a)
        print(f"  {a:>6} {n1:>5}盘 {w1:>5.1f}%   {n2:>5}盘 {w2:>5.1f}%")

    print("\n> 30 天段(06-07~07-06)日均振幅 3.55%、涨 5.2%,比 15 天段波动更大、趋势更强。")
    print("> 若组合在 30 天独立数据上仍 >53%,则 alpha 大概率真实;若跌回 51%,则是过拟合。")


if __name__ == "__main__":
    main()
