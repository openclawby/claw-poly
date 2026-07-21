"""技术指标预测力回测:RSI / MACD / 均线交叉 能否预测下个 5 分钟盘口涨跌?
用 15 天 BTC 秒级数据聚合成 1 分钟 bar,在每个盘口开盘时刻用历史数据算指标,
预测该盘口 close vs open。无前视偏差。对比基线 50% 和盈亏线 51%。
Run: python -m backtest.indicators
"""
from .sim import Feed, ROUND


def build_minute_bars(feed):
    """秒级 -> 1分钟收盘价序列 (ts, close)。"""
    lo, hi = feed.span()
    bars = []
    t = (int(lo) // 60 + 1) * 60
    while t <= hi:
        c = feed.at(t)
        if c:
            bars.append((t, c))
        t += 60
    return bars


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0)
        losses += max(-ch, 0)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - 100 / (1 + rs)


def ema(closes, period):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    e = closes[-period]
    for c in closes[-period + 1:]:
        e = c * k + e * (1 - k)
    return e


def macd(closes):
    if len(closes) < 35:
        return None
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    if e12 is None or e26 is None:
        return None
    return e12 - e26          # MACD 线;>0 多头动量


def test_signal(bars, feed, name, signal_fn):
    """signal_fn(closes_up_to_now) -> 'up'/'down'/None。对齐盘口边界评估。"""
    ts = [b[0] for b in bars]
    cl = [b[1] for b in bars]
    import bisect
    hits = n = 0
    lo, hi = feed.span()
    start = (int(lo + 3000) // ROUND + 1) * ROUND
    while start + ROUND <= hi:
        # 用截止到开盘时刻的分钟收盘算指标
        idx = bisect.bisect_right(ts, start)
        if idx < 40:
            start += ROUND
            continue
        sig = signal_fn(cl[:idx])
        if sig:
            o, c = feed.at(start), feed.at(start + ROUND - 1)
            if o and c:
                n += 1
                hits += (sig == ("up" if c >= o else "down"))
        start += ROUND
    return name, n, (hits / n * 100 if n else 0)


def main():
    feed = Feed("btc_1s_15d.json.gz")
    bars = build_minute_bars(feed)
    print(f"1分钟 bar: {len(bars)} 根 / 15 天")

    # 各指标的两种解读:动量(trend)和反转(revert)
    sigs = {
        "RSI>50 动量(顺势)": lambda c: "up" if (rsi(c) or 50) > 50 else "down",
        "RSI 超买超卖反转": lambda c: ("down" if (rsi(c) or 50) > 70 else
                                    ("up" if (rsi(c) or 50) < 30 else None)),
        "MACD>0 动量": lambda c: (None if macd(c) is None else
                                 ("up" if macd(c) > 0 else "down")),
        "MACD<0 反转": lambda c: (None if macd(c) is None else
                                 ("down" if macd(c) > 0 else "up")),
        "EMA9>EMA21 动量": lambda c: (None if ema(c, 21) is None else
                                     ("up" if ema(c, 9) > ema(c, 21) else "down")),
        "EMA9<EMA21 反转": lambda c: (None if ema(c, 21) is None else
                                     ("down" if ema(c, 9) > ema(c, 21) else "up")),
    }

    print("\n=== 技术指标预测下个5分钟盘口涨跌(15天,无前视)===")
    print(f"  {'信号':22s} {'样本':>6} {'方向命中率':>10}  {'vs 51%盈亏线':>12}")
    print("  " + "-" * 60)
    results = []
    for name, fn in sigs.items():
        _, n, wr = test_signal(bars, feed, name, fn)
        results.append((name, n, wr))
        edge = wr - 51
        tag = "✓ 有优势" if wr > 51.5 else ("≈盈亏线" if wr > 50 else "✗ 无效")
        print(f"  {name:22s} {n:>6} {wr:>9.2f}%  {edge:>+8.2f}pp  {tag}")

    # 基线
    up = sum(1 for i in range(1, len(bars)))
    print("\n  基线参考: 永远买涨≈50%,你现有策略实盘51.8%")
    print("\n> 口径:5分钟收盘vs开盘;单一市况15天;实盘还要扣提前量+点差,只会更差。")


if __name__ == "__main__":
    main()
