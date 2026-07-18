"""Prediction-accuracy audit over the 7-day window.

Answers "策略预估的准不准" three ways:
  1. fair_value 概率校准:模型说 P(Up)=x 时,实际 Up 发生的频率是不是 ≈ x
  2. 方向命中率:模型倾向方(P>=0.5)对最终涨跌的命中率,对比市场定价与朴素基准
  3. 信号级命中率:四个策略按冠军参数实际触发的单,买的方向赢了多少

Run: python -m backtest.accuracy   ->  backtest/ACCURACY.md
"""
import json
import math
import time
from pathlib import Path

from .sim import Feed, OddsSurface, ROUND, STRATS, _phi

HERE = Path(__file__).resolve().parent


def day_label(ts):
    return time.strftime("%m-%d", time.gmtime(ts))


def pct(n, d):
    return f"{n / d * 100:.1f}%" if d else "-"


def main():
    feed = Feed()
    surface = OddsSurface(feed)
    lo, hi = feed.span()
    picks = {p["strategy"]: p for p in json.loads((HERE / "picks.json").read_text())}
    fv_entry = picks.get("fair_value", {}).get("entry_delay", 45)
    fv_params = picks.get("fair_value", {}).get("params", {"edge_min": 0.09})

    # per-round records for fair_value model view
    rounds = []            # (start, result, p_up, mkt_up)
    skipped = 0
    start = (int(lo) // ROUND + 1) * ROUND
    while start + ROUND <= hi:
        open_p = feed.at(start)
        close_p = feed.at(start + ROUND - 1)
        entry_t = start + fv_entry
        cur = feed.at(entry_t)
        sigma = feed.vol(entry_t)
        if not (open_p and close_p and cur and sigma):
            skipped += 1
            start += ROUND
            continue
        result = "up" if close_p >= open_p else "down"
        drift = (cur - open_p) / open_p
        t_rem = start + ROUND - entry_t
        p_up = _phi(drift / (sigma * math.sqrt(t_rem)))
        mkt_up = surface.up_price(t_rem, drift * 10000)
        rounds.append((start, result, p_up, mkt_up))
        start += ROUND

    n = len(rounds)
    ups = sum(1 for r in rounds if r[1] == "up")

    # -- 1. calibration: deciles of predicted P(Up) vs realized Up freq --------
    cal = {}
    for _, result, p_up, _ in rounds:
        b = min(int(p_up * 10), 9)
        c = cal.setdefault(b, [0, 0])
        c[0] += 1
        c[1] += result == "up"

    # -- 2. direction hit rates ------------------------------------------------
    def hits(pred):
        h = t = 0
        for start, result, p_up, mkt_up in rounds:
            side = pred(start, p_up, mkt_up)
            if side is None:
                continue
            t += 1
            h += side == result
        return h, t

    model_h, model_t = hits(lambda s, p, m: "up" if p >= 0.5 else "down")
    mkt_h, mkt_t = hits(lambda s, p, m: "up" if m >= 0.5 else "down")
    alw_h, alw_t = ups, n
    drift_h, drift_t = hits(
        lambda s, p, m: "up" if (feed.at(s + fv_entry) or 0) >= (feed.at(s) or 0) else "down")

    # confidence buckets for the model
    conf_rows = []
    for label, f in [("弱(0.50-0.60)", lambda p: 0.5 <= abs(p - 0.5) + 0.5 < 0.6),
                     ("中(0.60-0.75)", lambda p: 0.6 <= abs(p - 0.5) + 0.5 < 0.75),
                     ("强(0.75-0.90)", lambda p: 0.75 <= abs(p - 0.5) + 0.5 < 0.9),
                     ("极强(≥0.90)", lambda p: abs(p - 0.5) + 0.5 >= 0.9)]:
        h = t = 0
        for _, result, p_up, _ in rounds:
            if not f(p_up):
                continue
            t += 1
            h += ("up" if p_up >= 0.5 else "down") == result
        conf_rows.append((label, h, t))

    # -- 3. signal-level hit rate per strategy (champion params) ---------------
    sig_rows = []
    daily = {}
    for key, fn in STRATS.items():
        p = picks.get(key)
        if not p:
            continue
        params, entry = p["params"], p["entry_delay"]
        h = t = 0
        net = 0.0
        for start, result, _, _ in rounds:
            sig = fn(feed, surface, start, start + entry, params)
            if not sig:
                continue
            side, price = sig
            if not (0.03 <= price <= 0.85):
                continue
            t += 1
            win = side == result
            h += win
            net += (5.0 / price - 5.0) if win else -5.0
            if key == "fair_value":
                d = daily.setdefault(day_label(start), [0, 0, 0.0])
                d[0] += 1
                d[1] += win
                d[2] += (5.0 / price - 5.0) if win else -5.0
        sig_rows.append((key, t, h, net))

    # -- report -----------------------------------------------------------------
    L = [f"# 预测准确率审计({day_label(lo)} ~ {day_label(hi)},{n} 个有效盘口,跳过 {skipped})",
         "",
         f"整周实际:Up {pct(ups, n)} / Down {pct(n - ups, n)}(涨跌基本对半,方向没有免费午餐)",
         "",
         "## 1. fair_value 概率校准(模型说 x% 涨,实际涨了多少)",
         "",
         "| 模型预测 P(Up) | 盘数 | 实际 Up 频率 | 偏差 |",
         "|---|---|---|---|"]
    for b in sorted(cal):
        cnt, up_cnt = cal[b]
        mid = b / 10 + 0.05
        real = up_cnt / cnt
        L.append(f"| {b/10:.1f}–{b/10+0.1:.1f} | {cnt} | {real*100:.1f}% | {(real-mid)*100:+.1f}pp |")

    L += ["", "## 2. 方向命中率(每盘一判,谁更会猜涨跌)", "",
          "| 预测者 | 判定盘数 | 命中率 |", "|---|---|---|",
          f"| fair_value 模型倾向方 | {model_t} | {pct(model_h, model_t)} |",
          f"| 市场定价倾向方(赔率曲面) | {mkt_t} | {pct(mkt_h, mkt_t)} |",
          f"| 朴素:跟随开盘后 {fv_entry}s 漂移 | {drift_t} | {pct(drift_h, drift_t)} |",
          f"| 朴素:永远买涨 | {alw_t} | {pct(alw_h, alw_t)} |",
          "", "### 模型置信度 vs 命中率(越自信是否越准)", "",
          "| 置信区间 | 盘数 | 命中率 |", "|---|---|---|"]
    for label, h, t in conf_rows:
        L.append(f"| {label} | {t} | {pct(h, t)} |")

    L += ["", "## 3. 信号级命中(冠军参数实际会下的单)", "",
          "| 策略 | 触发单数 | 方向命中 | 命中率 | 结算制净利($5/单) |",
          "|---|---|---|---|---|"]
    for key, t, h, net in sig_rows:
        L.append(f"| {key} | {t} | {h} | {pct(h, t)} | ${net:+.2f} |")

    L += ["", "## 4. fair_value 按日分解(稳定性)", "",
          "| 日期 | 单数 | 命中率 | 净利 |", "|---|---|---|---|"]
    for d in sorted(daily):
        t, h, net = daily[d]
        L.append(f"| {d} | {t} | {pct(h, t)} | ${net:+.2f} |")

    L += ["", "> 口径:结算制(不含止盈提前退出);入场价=赔率曲面中位数+半点差 0.015,",
          "> 与 REPORT.md 相同,系统性偏乐观 —— 以 paper 实测为最终对照。"]

    out = HERE / "ACCURACY.md"
    out.write_text("\n".join(L), encoding="utf-8")
    (HERE / "accuracy.json").write_text(json.dumps({
        "window": [day_label(lo), day_label(hi)], "n": n, "ups": ups,
        "calibration": [
            {"bucket": f"{b/10:.1f}-{b/10+0.1:.1f}", "mid": round(b / 10 + 0.05, 2),
             "count": cal[b][0], "realized": round(cal[b][1] / cal[b][0], 3)}
            for b in sorted(cal)],
        "direction": [
            {"who": "fair_value 模型", "hits": model_h, "total": model_t},
            {"who": "市场定价(赔率曲面)", "hits": mkt_h, "total": mkt_t},
            {"who": "跟随开盘后漂移", "hits": drift_h, "total": drift_t},
            {"who": "永远买涨", "hits": alw_h, "total": alw_t}],
        "confidence": [{"label": l, "hits": h, "total": t} for l, h, t in conf_rows],
        "signals": [{"strategy": k, "trades": t, "hits": h, "net": round(net, 2)}
                    for k, t, h, net in sig_rows],
        "daily": [{"date": d, "trades": daily[d][0], "hits": daily[d][1],
                   "net": round(daily[d][2], 2)} for d in sorted(daily)],
    }, ensure_ascii=False), encoding="utf-8")
    print("\n".join(L))
    print(f"\n-> {out} + accuracy.json")


if __name__ == "__main__":
    main()
