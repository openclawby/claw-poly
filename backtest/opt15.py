"""15-day parameter optimization for the CURRENT pre_trend strategy
(two tiers, cover=1: every round is bought pre-open at ~0.51 taker).

With cover on, the economics depend on (lead_sec, lookback_sec, signal);
min_move_pct only labels trigger vs cover trades, so it is analyzed
separately as a labeling recommendation, not an economic knob.

IS = first 10 days, OOS = last 5. Fills at 0.50 / 0.51 / 0.52.
Run: python -m backtest.opt15  ->  backtest/OPT15.md (+ picks.json pre_trend)
"""
import json
from pathlib import Path

from .sim import Feed, ROUND

HERE = Path(__file__).resolve().parent
LEADS = [120, 300, 450, 600, 900, 1200, 1800]
LOOKBACKS = [180, 300, 600, 900, 1200, 1800, 3600]
FILLS = [0.50, 0.51, 0.52]
THRESHOLDS = [0.1, 0.15, 0.2, 0.3]
USD = 5.0


def build(feed):
    """rounds: [(start, result_up:bool, {(lead,lb): move_pct})]"""
    lo, hi = feed.span()
    warm = lo + max(LEADS) + max(LOOKBACKS) + 60
    out = []
    start = (int(warm) // ROUND + 1) * ROUND
    while start + ROUND <= hi:
        o, c = feed.at(start), feed.at(start + ROUND - 1)
        if o and c:
            moves = {}
            for lead in LEADS:
                t0 = start - lead
                b = feed.at(t0)
                for lb in LOOKBACKS:
                    a = feed.at(t0 - lb)
                    moves[(lead, lb)] = (b - a) / a * 100 if (a and b) else None
            out.append((start, c >= o, moves))
        start += ROUND
    return out


def metrics(trades, fill):
    """trades: list of (hit: bool). Returns acc/net/ev at given fill price."""
    n = len(trades)
    hits = sum(trades)
    if not n:
        return {"trades": 0, "acc": 0, "net": 0, "ev": 0}
    win_gain = USD / fill - USD
    net = hits * win_gain - (n - hits) * USD
    return {"trades": n, "acc": round(hits / n * 100, 2),
            "net": round(net, 2), "ev": round(net / n, 4)}


def run(rounds, lead, lb, sig, t0, t1, thr=None, tier=None):
    """tier=None: all rounds; 'trigger'/'cover': subset by |move| vs thr."""
    trades = []
    for start, up, moves in rounds:
        if not (t0 <= start < t1):
            continue
        mv = moves.get((lead, lb))
        if mv is None:
            continue
        if tier == "trigger" and abs(mv) < thr:
            continue
        if tier == "cover" and abs(mv) >= thr:
            continue
        side_up = (mv > 0) if sig == "momo" else (mv <= 0)
        trades.append(side_up == up)
    return trades


def main():
    feed = Feed("btc_1s_15d.json.gz")
    rounds = build(feed)
    lo = rounds[0][0]
    hi = rounds[-1][0]
    is_end = lo + 10 * 86400

    results = []
    for sig in ("revert", "momo"):
        for lead in LEADS:
            for lb in LOOKBACKS:
                tr = run(rounds, lead, lb, sig, lo, is_end)
                m = metrics(tr, 0.51)
                if m["trades"] >= 1000:
                    results.append((sig, lead, lb, m))
    results.sort(key=lambda x: x[3]["ev"], reverse=True)

    L = [f"# pre_trend 15 天调参(全覆盖口径:每盘必买 @0.51;{len(rounds)} 盘,"
         f"IS 前 10 天 / OOS 后 5 天)", "",
         "cover=1 时每盘都下注,方向由 (lead, lookback, signal) 决定;",
         "min_move_pct 仅划分触发/补仓标签,单独分析。", "",
         "## IS 段 Top 12(按 0.51 成交单盘期望)", "",
         "| 信号 | 提前 | 回看 | IS 盘数 | IS 准确率 | IS 净$ | OOS 盘数 | OOS 准确率 | OOS 净$ |",
         "|---|---|---|---|---|---|---|---|---|"]

    top = results[:12]
    oos_cache = {}
    for sig, lead, lb, is_m in top:
        oos_m = metrics(run(rounds, lead, lb, sig, is_end, hi + 1), 0.51)
        oos_cache[(sig, lead, lb)] = oos_m
        L.append(f"| {sig} | {lead//60}min | {lb//60:.0f}min | {is_m['trades']} "
                 f"| {is_m['acc']}% | {is_m['net']} | {oos_m['trades']} "
                 f"| {oos_m['acc']}% | {oos_m['net']} |")

    # pick: best IS whose OOS net@0.51 > 0; fallback best IS
    pick = None
    for sig, lead, lb, is_m in top:
        if oos_cache[(sig, lead, lb)]["net"] > 0:
            pick = (sig, lead, lb, is_m, oos_cache[(sig, lead, lb)])
            break
    fallback = pick is None
    if fallback:
        sig, lead, lb, is_m = results[0]
        pick = (sig, lead, lb, is_m, oos_cache.get((sig, lead, lb))
                or metrics(run(rounds, lead, lb, sig, is_end, hi + 1), 0.51))
    sig, lead, lb, is_m, oos_m = pick

    # neighborhood plateau (lead±1, lb±1, same signal) on IS
    li, bi = LEADS.index(lead), LOOKBACKS.index(lb)
    nb = []
    for dl in (-1, 0, 1):
        for db_ in (-1, 0, 1):
            if 0 <= li + dl < len(LEADS) and 0 <= bi + db_ < len(LOOKBACKS):
                nb.append(metrics(run(rounds, LEADS[li + dl], LOOKBACKS[bi + db_],
                                      sig, lo, is_end), 0.51)["ev"])
    nb.sort()
    nb_med = nb[len(nb) // 2]

    # fills sensitivity on OOS
    oos_tr = run(rounds, lead, lb, sig, is_end, hi + 1)
    sens = {f: metrics(oos_tr, f) for f in FILLS}

    # threshold labeling: trigger vs cover subsets (full window, at pick)
    L += ["", f"## 入选配置的阈值分层(min_move_pct 标签分析,{sig} lead={lead}s lb={lb}s,全 15 天)",
          "", "| 阈值 | 触发单数 | 触发准确率 | 触发净$@0.51 | 补仓单数 | 补仓准确率 | 补仓净$@0.51 |",
          "|---|---|---|---|---|---|---|"]
    for thr in THRESHOLDS:
        tg = metrics(run(rounds, lead, lb, sig, lo, hi + 1, thr, "trigger"), 0.51)
        cv = metrics(run(rounds, lead, lb, sig, lo, hi + 1, thr, "cover"), 0.51)
        L.append(f"| {thr}% | {tg['trades']} | {tg['acc']}% | {tg['net']} "
                 f"| {cv['trades']} | {cv['acc']}% | {cv['net']} |")

    # daily stability of the pick
    daily = {}
    for start, up, moves in rounds:
        mv = moves.get((lead, lb))
        if mv is None:
            continue
        side_up = (mv > 0) if sig == "momo" else (mv <= 0)
        d = int((start - lo) // 86400)
        e = daily.setdefault(d, [0, 0])
        e[0] += 1
        e[1] += side_up == up
    L += ["", "## 入选配置逐日准确率(51% 为 0.51 成交的盈亏线)", "",
          "| 日 | 盘数 | 准确率 | 日净$@0.51 |", "|---|---|---|---|"]
    for d in sorted(daily):
        n, h = daily[d]
        win_gain = USD / 0.51 - USD
        L.append(f"| D{d+1} | {n} | {h/n*100:.1f}% | {h*win_gain-(n-h)*USD:+.2f} |")

    seg = "" if not fallback else "(⚠️ 无 OOS 为正的配置,以下为 IS 最优,仅作参考)"
    L += ["", f"## 结论{seg}", "",
          f"**入选:signal={sig} · lead_sec={lead} · lookback_sec={lb}**",
          f"- IS:{is_m['trades']} 盘 / {is_m['acc']}% / 净 ${is_m['net']}",
          f"- OOS:{oos_m['trades']} 盘 / {oos_m['acc']}% / 净 ${oos_m['net']}",
          f"- 邻域中位 IS 期望:${nb_med}" + ("(平原)" if nb_med > 0 else "(⚠️ 孤峰嫌疑)"),
          f"- OOS 随成交价:0.50→${sens[0.50]['net']} · 0.51→${sens[0.51]['net']} · 0.52→${sens[0.52]['net']}",
          "", "> 全覆盖模式的收益天花板天然薄(每盘 ~51% vs 51% 盈亏线),",
          "> 真正的利润集中在高阈值触发单;若 OOS 为负,建议 cover=0 只做触发单。"]

    (HERE / "OPT15.md").write_text("\n".join(L), encoding="utf-8")

    # update picks.json pre_trend entry (cover-on economics, $5 canonical)
    ok = (not fallback) and oos_m["net"] >= 20 and oos_m["acc"] > 51
    entry = {
        "strategy": "pre_trend",
        "params": {"signal": sig, "lookback_sec": lb, "min_move_pct": 0.2,
                   "lead_sec": lead, "max_price": 0.51, "cover": 1},
        "entry_delay": 0,
        "is": {"trades": is_m["trades"], "win_rate": is_m["acc"],
               "ev_usd": is_m["ev"], "net_usd": is_m["net"], "max_dd": None},
        "oos": {"trades": oos_m["trades"], "win_rate": oos_m["acc"],
                "ev_usd": oos_m["ev"], "net_usd": oos_m["net"], "max_dd": None},
        "verdict": "✅ 上架" if ok else ("⚠️ 观察(OOS 净利过薄)" if oos_m["net"] > 0
                                        else "⚠️ 观察(全覆盖 OOS 为负)"),
    }
    picks_p = HERE / "picks.json"
    picks = [p for p in json.loads(picks_p.read_text()) if p["strategy"] != "pre_trend"]
    picks_p.write_text(json.dumps(picks + [entry], indent=1, ensure_ascii=False))
    print("\n".join(L))


if __name__ == "__main__":
    main()
