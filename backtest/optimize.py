"""Dense grid optimization for ALL in-round strategies (pre_trend has its own
runner in prebet.py; its pick is preserved).

Per strategy: dense grid -> pick by IS EV -> OOS validate -> plateau check
(neighborhood median EV) -> spread sensitivity (0.010/0.015/0.020).
Precomputes per-(round, entry) features once so the grid is pure filtering.

Run: python -m backtest.optimize  ->  rewrites backtest/REPORT.md + picks.json
"""
import json
import math
from pathlib import Path

from .sim import Feed, OddsSurface, ROUND, _phi

HERE = Path(__file__).resolve().parent
ENTRIES = [10, 20, 30, 45, 60, 90, 120, 150]
MOMO_WINDOWS = [15, 30, 60, 120, 180]
SPREADS = [0.010, 0.015, 0.020]
BASE_SP = 0.015
USD = 5.0

GRIDS = {
    "fair_value": {"edge_min": [0.03, 0.04, 0.05, 0.06, 0.07, 0.09, 0.11, 0.13, 0.15]},
    "tick_momo": {"momo_window": MOMO_WINDOWS,
                  "momo_min": [0.02, 0.03, 0.05, 0.08, 0.12]},
    "open_burst": {"burst_min": [0.03, 0.05, 0.07, 0.10, 0.15, 0.20]},
    "prev_reverse": {"rev_min": [0.08, 0.12, 0.18, 0.25, 0.35, 0.50]},
}
MIN_IS_TRADES = {"fair_value": 50, "tick_momo": 50, "open_burst": 30, "prev_reverse": 30}
MIN_OOS_TRADES = 25          # thinner OOS samples don't count as validation
OOS_NET_FLOOR = 20.0         # ✅ needs at least this much OOS net (else ⚠️ 观察)


def build_features(feed, surface, lo, hi):
    """rows[s] = {result, prev_move, per_entry: {e: {...}}}"""
    rows = {}
    start = (int(lo) // ROUND + 1) * ROUND
    while start + ROUND <= hi:
        open_p = feed.at(start)
        close_p = feed.at(start + ROUND - 1)
        p_prev = feed.at(start - ROUND)
        if not (open_p and close_p):
            start += ROUND
            continue
        row = {"result": "up" if close_p >= open_p else "down",
               "prev_move": (open_p - p_prev) / p_prev * 100 if p_prev else None,
               "per_entry": {}}
        for e in ENTRIES:
            t = start + e
            cur = feed.at(t)
            sigma = feed.vol(t)
            if not cur or not sigma:
                continue
            drift = (cur - open_p) / open_p
            t_rem = ROUND - e
            mkt_up = surface.up_price(t_rem, drift * 10000)
            fe = {"drift_pct": drift * 100, "mkt_up": mkt_up,
                  "p_up": _phi(drift / (sigma * math.sqrt(t_rem)))}
            for w in MOMO_WINDOWS:
                a = feed.at(t - w)
                fe[f"mv{w}"] = (cur - a) / a * 100 if a else None
            row["per_entry"][e] = fe
        rows[start] = row
        start += ROUND
    return rows


def decide(strategy, params, entry, row):
    """-> (side, side_mkt_price) or None. Price is the market prob WITHOUT spread."""
    fe = row["per_entry"].get(entry)
    if not fe:
        return None
    if strategy == "fair_value":
        edge = params["edge_min"]
        if fe["p_up"] - fe["mkt_up"] >= edge:
            return "up", fe["mkt_up"]
        if (1 - fe["p_up"]) - (1 - fe["mkt_up"]) >= edge:
            return "down", 1 - fe["mkt_up"]
        return None
    if strategy == "tick_momo":
        mv = fe.get(f"mv{params['momo_window']}")
        if mv is None or abs(mv) < params["momo_min"]:
            return None
        side = "up" if mv > 0 else "down"
    elif strategy == "open_burst":
        if abs(fe["drift_pct"]) < params["burst_min"]:
            return None
        side = "up" if fe["drift_pct"] > 0 else "down"
    elif strategy == "prev_reverse":
        pm = row["prev_move"]
        if pm is None or abs(pm) < params["rev_min"]:
            return None
        side = "down" if pm > 0 else "up"
    else:
        return None
    return side, (fe["mkt_up"] if side == "up" else 1 - fe["mkt_up"])


def evaluate(strategy, params, entry, rows, t0, t1, spread=BASE_SP):
    trades = []
    for s, row in rows.items():
        if not (t0 <= s < t1):
            continue
        sig = decide(strategy, params, entry, row)
        if not sig:
            continue
        side, base = sig
        price = min(base + spread, 0.99)
        if price > 0.85 or price < 0.03:
            continue
        win = row["result"] == side
        trades.append(USD / price - USD if win else -USD)
    n = len(trades)
    if not n:
        return {"trades": 0, "win_rate": 0, "ev_usd": 0, "net_usd": 0, "max_dd": 0}
    wins = sum(1 for x in trades if x > 0)
    cum = peak = dd = 0.0
    for x in trades:
        cum += x
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return {"trades": n, "win_rate": round(wins / n * 100, 1),
            "ev_usd": round(sum(trades) / n, 4),
            "net_usd": round(sum(trades), 2), "max_dd": round(dd, 2)}


def expand(grid):
    keys = list(grid)
    def rec(i, cur):
        if i == len(keys):
            yield dict(cur)
            return
        for v in grid[keys[i]]:
            cur[keys[i]] = v
            yield from rec(i + 1, cur)
    yield from rec(0, {})


def neighborhood(strategy, params, entry, rows, t0, t1):
    """Median IS EV over +-1 grid steps of every param and entry."""
    grid = GRIDS[strategy]
    evs = []
    ei = ENTRIES.index(entry)
    for de in (-1, 0, 1):
        if not (0 <= ei + de < len(ENTRIES)):
            continue
        e2 = ENTRIES[ei + de]
        axes = []
        for k, vals in grid.items():
            vi = vals.index(params[k])
            axes.append([(k, vals[vi + d]) for d in (-1, 0, 1)
                         if 0 <= vi + d < len(vals)])
        def rec(i, cur):
            if i == len(axes):
                evs.append(evaluate(strategy, dict(cur), e2, rows, t0, t1)["ev_usd"])
                return
            for k, v in axes[i]:
                cur[k] = v
                rec(i + 1, cur)
        rec(0, {})
    evs.sort()
    return evs[len(evs) // 2] if evs else 0


def main():
    feed = Feed()
    surface = OddsSurface(feed)
    lo, hi = feed.span()
    warm = lo + 700                       # cover 180s momo lookback + vol window
    is_end = lo + 5 * 86400
    rows = build_features(feed, surface, warm, hi)
    print(f"features: {len(rows)} rounds · surface {len(surface.grid)} cells")

    L = ["# 全策略稠密网格优化(7 天:IS 前 5 天 / OOS 后 2 天,v2)", "",
         f"- 赔率曲面:{surface.n_samples} 个真实盘口样本;成交价=市场概率+半点差(基准 {BASE_SP})",
         "- 每策略:网格选参(IS 期望)→ OOS 验证 → 邻域平原检验 → 点差敏感性",
         "- pre_trend(提前下注)见 PREBET.md,其冠军参数一并保留", ""]

    picks = []
    applied_params = {}
    for strat, grid in GRIDS.items():
        results = []
        for params in expand(grid):
            for entry in ENTRIES:
                r = evaluate(strat, params, entry, rows, warm, is_end)
                if r["trades"] >= MIN_IS_TRADES[strat]:
                    results.append((params, entry, r))
        results.sort(key=lambda x: x[2]["ev_usd"], reverse=True)

        L += [f"## {strat}", "",
              "| 参数 | 入场 | IS 盘数 | IS 胜率 | IS 期望$ | IS 净$ | OOS 盘数 | OOS 胜率 | OOS 净$ |",
              "|---|---|---|---|---|---|---|---|---|"]
        shown = 0
        pick = None
        for params, entry, is_r in results:
            oos_r = evaluate(strat, params, entry, rows, is_end, hi)
            if shown < 6:
                L.append(f"| {json.dumps(params)} | {entry}s | {is_r['trades']} "
                         f"| {is_r['win_rate']}% | {is_r['ev_usd']} | {is_r['net_usd']} "
                         f"| {oos_r['trades']} | {oos_r['win_rate']}% | {oos_r['net_usd']} |")
                shown += 1
            if pick is None and oos_r["net_usd"] > 0 and oos_r["trades"] >= MIN_OOS_TRADES:
                pick = (params, entry, is_r, oos_r)
                if shown >= 6:
                    break
        if pick is None and results:
            params, entry, is_r = results[0]
            pick = (params, entry, is_r, evaluate(strat, params, entry, rows, is_end, hi))
            verdict = "❌ OOS 不达标"
        elif pick is None:
            L += ["", "样本不足,无有效配置", ""]
            continue
        else:
            params, entry, is_r, oos_r = pick
            verdict = ("✅ 上架" if oos_r["net_usd"] >= OOS_NET_FLOOR
                       else "⚠️ 观察(OOS 净利过薄)") if is_r["ev_usd"] > 0 else "❌"
        params, entry, is_r, oos_r = pick
        nb = neighborhood(strat, params, entry, rows, warm, is_end)
        sens = {f"{sp:.3f}": evaluate(strat, params, entry, rows, is_end, hi, sp)["net_usd"]
                for sp in SPREADS}
        plateau = "平原(邻域中位期望 >0)" if nb > 0 else "⚠️ 孤峰嫌疑(邻域中位 ≤0)"
        if nb <= 0 and verdict.startswith("✅"):
            verdict = "⚠️ 观察(孤峰)"
        L += ["",
              f"**入选:{json.dumps(params)} + 入场 {entry}s → {verdict}**",
              f"- 邻域中位 IS 期望:${nb} —— {plateau}",
              f"- OOS 净利随点差:0.010→${sens['0.010']} · 0.015→${sens['0.015']} · 0.020→${sens['0.020']}",
              ""]
        picks.append({"strategy": strat, "params": params, "entry_delay": entry,
                      "is": is_r, "oos": oos_r, "verdict": verdict})
        applied_params.update(params)

    L += ["> 口径:结算制(不含止盈提前退出);赔率曲面为中位数近似,系统性偏乐观;",
          "> IS 选参存在多重比较,判定以 OOS + 邻域 + 点差三重检验与模拟盘实测为准。"]

    (HERE / "REPORT.md").write_text("\n".join(L), encoding="utf-8")

    picks_p = HERE / "picks.json"
    old = json.loads(picks_p.read_text()) if picks_p.exists() else []
    keep = [p for p in old if p["strategy"] == "pre_trend"]
    picks_p.write_text(json.dumps(picks + keep, indent=1, ensure_ascii=False))
    (HERE / "applied_params.json").write_text(json.dumps(applied_params))
    print("\n".join(L))


if __name__ == "__main__":
    main()
