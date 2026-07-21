"""触发单 vs 补仓单分层回测:验证实盘发现的三个假设
  1. 触发单(强信号)该顺势(momo)还是反转(revert)?
  2. 补仓单(弱信号)该顺势还是反转?
  3. 提前量 lead_sec 对两者的影响是否不同?

口径与实盘一致:@0.51 吃单,每股赢结算 $1,最小 5 股(此处按 $5.1/单归一)。
15 天数据,不分 IS/OOS(这是机制验证,不是选参过拟合)。
Run: python -m backtest.layer_analysis
"""
from .sim import Feed, ROUND

LEADS = [60, 120, 180, 300, 450, 600]      # 提前决策秒数
LB = 900                                    # 回看窗口固定 15min(实盘同款)
THR = 0.20                                  # 触发/补仓分界(实盘同款)
FILL = 0.51
USD = 5.1


def move(feed, t0, lb):
    a, b = feed.at(t0 - lb), feed.at(t0)
    return None if not a or not b else (b - a) / a * 100


def result(feed, start):
    o, c = feed.at(start), feed.at(start + ROUND - 1)
    return None if not o or not c else ("up" if c >= o else "down")


def metrics(hits, n):
    if not n:
        return "  0盘", 0, 0
    win_gain = USD / FILL - USD
    net = hits * win_gain - (n - hits) * USD
    return f"{n:4d}盘 胜率{hits/n*100:5.1f}% 净${net:+8.2f} 单均${net/n:+.3f}", net, hits / n


def evaluate(feed, lead, tier, sig, lo, hi):
    """tier: 'trigger'|'cover'; sig: 'momo'|'revert'. 返回 (hits, n)."""
    hits = n = 0
    start = (int(lo) // ROUND + 1) * ROUND
    while start + ROUND <= hi:
        t0 = start - lead
        mv = move(feed, t0, LB)
        res = result(feed, start)
        if mv is not None and res is not None:
            big = abs(mv) >= THR
            if (tier == "trigger" and big) or (tier == "cover" and not big):
                side_up = (mv > 0) if sig == "momo" else (mv <= 0)
                n += 1
                hits += (("up" if side_up else "down") == res)
        start += ROUND
    return hits, n


def main():
    feed = Feed("btc_1s_15d.json.gz")
    lo, hi = feed.span()
    lo += LB + max(LEADS) + 60

    print("=" * 92)
    print(f"分层回测(15天,回看{LB}s,触发线{THR}%,@{FILL}成交,$5.1/单)")
    print("=" * 92)

    for tier, label in [("trigger", "① 触发单(强信号 ≥0.2%)"), ("cover", "② 补仓单(弱信号 <0.2%)")]:
        print(f"\n{label}")
        print(f"  {'提前量':>8} | {'revert 反转':^38} | {'momo 顺势':^38}")
        print("  " + "-" * 88)
        for lead in LEADS:
            rev = metrics(*evaluate(feed, lead, tier, "revert", lo, hi))
            mom = metrics(*evaluate(feed, lead, tier, "momo", lo, hi))
            mark = "  ← momo胜" if mom[1] > rev[1] else "  ← revert胜"
            print(f"  {lead:>6}s  | {rev[0]:38s} | {mom[0]:38s}{mark}")

    # 组合建议:每个 tier 取各自最优方向,合成整体
    print("\n" + "=" * 92)
    print("最优组合(每层各取最优方向,按实盘 lead=300 及更优 lead 对比)")
    print("=" * 92)
    for lead in (300, 180, 120, 60):
        best_net = 0
        parts = []
        for tier in ("trigger", "cover"):
            rev_h, rev_n = evaluate(feed, lead, tier, "revert", lo, hi)
            mom_h, mom_n = evaluate(feed, lead, tier, "momo", lo, hi)
            _, rev_net, _ = metrics(rev_h, rev_n)
            _, mom_net, _ = metrics(mom_h, mom_n)
            if mom_net >= rev_net:
                parts.append(f"{tier}=momo(${mom_net:+.0f})")
                best_net += mom_net
            else:
                parts.append(f"{tier}=revert(${rev_net:+.0f})")
                best_net += rev_net
        print(f"  lead={lead}s: {' + '.join(parts)} = 合计 ${best_net:+.2f}")


if __name__ == "__main__":
    main()
