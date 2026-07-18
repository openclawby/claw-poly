"""Pre-open betting backtest: decide each round's direction BEFORE it opens.

The live probe shows pre-open books quote ~0.50/0.51 with a 1-cent spread up
to 25+ minutes ahead, so entry cost is modeled at three fills:
  maker 0.50 (rest at bid) · taker 0.51 (cross) · pessimist 0.52.
Verdicts are judged on the TAKER 0.51 fill (honest default).

Signals (all computed at t0 = round_start - lead, no lookahead):
  momo   — follow the sign of the last `lookback` seconds' return
  revert — fade it
  streak — last k completed 5-min rounds all same direction -> follow / fade

Run: python -m backtest.prebet  ->  backtest/PREBET.md (+ merge into picks.json)
"""
import json
from pathlib import Path

from .sim import Feed, ROUND

HERE = Path(__file__).resolve().parent
FILLS = [0.50, 0.51, 0.52]
LEADS = [300, 600, 900, 1200, 1500, 1800]
LOOKBACKS = [300, 600, 900, 1800, 3600]
THRESHOLDS = [0.0, 0.05, 0.10, 0.20]     # min |ret| % to bet
USD = 5.0


def result_of(feed, s):
    o, c = feed.at(s), feed.at(s + ROUND - 1)
    if not o or not c:
        return None
    return "up" if c >= o else "down"


def momo_side(feed, t0, lb, thr, flip):
    a, b = feed.at(t0 - lb), feed.at(t0)
    if not a or not b:
        return None
    ret = (b - a) / a * 100
    if abs(ret) < thr:
        return None
    side = "up" if ret > 0 else "down"
    if flip:
        side = "down" if side == "up" else "up"
    return side


def streak_side(feed, t0, s, k, flip):
    """Last k rounds fully completed before t0 all same direction -> follow."""
    last_done = (int(t0) // ROUND) * ROUND          # bar ending at/before t0
    dirs = []
    for i in range(1, k + 1):
        st = last_done - i * ROUND
        r = result_of(feed, st)
        if r is None:
            return None
        dirs.append(r)
    if len(set(dirs)) != 1:
        return None
    side = dirs[0]
    if flip:
        side = "down" if side == "up" else "up"
    return side


def run_cfg(feed, cfg, t_lo, t_hi):
    """-> per-fill {trades, hits, acc, net} for one config on [t_lo, t_hi)."""
    trades = hits = 0
    start = (int(t_lo) // ROUND + 1) * ROUND
    while start + ROUND <= t_hi:
        t0 = start - cfg["lead"]
        if t0 < t_lo:
            start += ROUND
            continue
        if cfg["kind"] == "momo":
            side = momo_side(feed, t0, cfg["lb"], cfg["thr"], cfg["flip"])
        else:
            side = streak_side(feed, t0, start, cfg["k"], cfg["flip"])
        if side:
            res = result_of(feed, start)
            if res:
                trades += 1
                hits += side == res
        start += ROUND
    out = {"trades": trades, "hits": hits,
           "acc": round(hits / trades * 100, 2) if trades else 0}
    for f in FILLS:
        win_gain = USD / f - USD
        net = hits * win_gain - (trades - hits) * USD
        out[f"net@{f:.2f}"] = round(net, 2)
        out[f"ev@{f:.2f}"] = round(net / trades, 4) if trades else 0
    return out


def all_configs():
    for lead in LEADS:
        for lb in LOOKBACKS:
            for thr in THRESHOLDS:
                for flip in (False, True):
                    yield {"kind": "momo", "lead": lead, "lb": lb, "thr": thr,
                           "flip": flip,
                           "name": f"{'revert' if flip else 'momo'} lb={lb}s thr={thr}% lead={lead}s"}
        for k in (2, 3):
            for flip in (False, True):
                yield {"kind": "streak", "lead": lead, "k": k, "flip": flip,
                       "name": f"{'streak_fade' if flip else 'streak_follow'} k={k} lead={lead}s"}


def fmt_cfg_row(cfg, is_r, oos_r=None):
    base = (f"| {cfg['name']} | {is_r['trades']} | {is_r['acc']}% "
            f"| {is_r['ev@0.51']} | {is_r['net@0.51']} |")
    if oos_r:
        base += f" {oos_r['trades']} | {oos_r['acc']}% | {oos_r['net@0.51']} |"
    return base


def main():
    feed = Feed()
    lo, hi = feed.span()
    warm = lo + 4000                       # warm-up so 3600s lookbacks exist
    is_end = lo + 5 * 86400

    results = []
    for cfg in all_configs():
        r = run_cfg(feed, cfg, warm, is_end)
        if r["trades"] >= 100:
            results.append((cfg, r))
    results.sort(key=lambda x: x[1]["ev@0.51"], reverse=True)

    # accuracy vs lead for the always-bet momo baseline (best lb by IS acc)
    lead_curves = {}
    for lb in LOOKBACKS:
        row = []
        for lead in LEADS:
            cfg = {"kind": "momo", "lead": lead, "lb": lb, "thr": 0.0, "flip": False}
            row.append(run_cfg(feed, cfg, warm, is_end)["acc"])
        lead_curves[lb] = row

    L = ["# 提前下注回测(决策在开盘前,7 天:IS 前 5 天 / OOS 后 2 天)", "",
         "实测前置条件:未开盘盘口订单簿 ~0.50/0.51,点差 1 分,提前 25 分钟可交易。",
         "判定口径按 **吃单 0.51 成交**;同时给出 0.50(挂单)与 0.52(悲观)。", "",
         "## 方向准确率 vs 提前量(momo 全下注基线,IS 段)", "",
         "| 回看窗口 | " + " | ".join(f"提前{x//60}min" for x in LEADS) + " |",
         "|---|" + "---|" * len(LEADS)]
    for lb, row in lead_curves.items():
        L.append(f"| {lb}s | " + " | ".join(f"{a}%" for a in row) + " |")

    L += ["", "## IS 段 Top 15(按 0.51 成交的单盘期望排序,≥100 单)", "",
          "| 配置 | IS 单数 | IS 准确率 | IS 期望$@0.51 | IS 净$@0.51 | OOS 单数 | OOS 准确率 | OOS 净$@0.51 |",
          "|---|---|---|---|---|---|---|---|"]
    top = results[:15]
    oos_map = {}
    for cfg, is_r in top:
        oos_r = run_cfg(feed, cfg, is_end, hi)
        oos_map[cfg["name"]] = oos_r
        L.append(fmt_cfg_row(cfg, is_r, oos_r))

    # pick: best IS whose OOS also holds up at 0.51
    pick = None
    for cfg, is_r in top:
        oos_r = oos_map[cfg["name"]]
        if oos_r["net@0.51"] > 0 and oos_r["trades"] >= 50 and oos_r["acc"] > 51:
            pick = (cfg, is_r, oos_r)
            break

    L += ["", "## 结论", ""]
    if pick:
        cfg, is_r, oos_r = pick
        # neighborhood sanity for momo picks: +-1 step in lb & thr
        nb_note = ""
        if cfg["kind"] == "momo":
            li = LOOKBACKS.index(cfg["lb"])
            ti = THRESHOLDS.index(cfg["thr"])
            nb = []
            for dl in (-1, 0, 1):
                for dt in (-1, 0, 1):
                    if 0 <= li + dl < len(LOOKBACKS) and 0 <= ti + dt < len(THRESHOLDS):
                        c2 = dict(cfg, lb=LOOKBACKS[li + dl], thr=THRESHOLDS[ti + dt])
                        nb.append(run_cfg(feed, c2, warm, is_end)["ev@0.51"])
            nb_med = sorted(nb)[len(nb) // 2]
            nb_note = f"参数邻域中位期望 ${nb_med}(非孤峰)" if nb_med > 0 else \
                      f"⚠️ 参数邻域中位期望 ${nb_med} —— 该点可能是孤峰,谨慎"
        L += [f"**入选:{cfg['name']}**",
              f"- IS:{is_r['trades']} 单 / 准确率 {is_r['acc']}% / 净 ${is_r['net@0.51']}@0.51",
              f"- OOS:{oos_r['trades']} 单 / 准确率 {oos_r['acc']}% / 净 ${oos_r['net@0.51']}@0.51",
              f"- 三档成交价 OOS 净:0.50→${oos_r['net@0.50']} · 0.51→${oos_r['net@0.51']} · 0.52→${oos_r['net@0.52']}",
              f"- {nb_note}" if nb_note else ""]
    else:
        L += ["**没有配置在 0.51 成交价下通过 IS/OOS 双正验证** —— 提前 5-30 分钟预测"
              "未来 5 分钟 K 线方向,准确率不足以覆盖点差。如实报告:该模式在当前市况"
              "下没有可靠优势;若仍要提前挂单,建议用 0.50 挂单价 + 最强的动量配置,"
              "并以模拟盘验证为准。"]
        # still surface the least-bad momo config for the live default
        if results:
            cfg, is_r = results[0]
            oos_r = oos_map.get(cfg["name"]) or run_cfg(feed, cfg, is_end, hi)
            pick = (cfg, is_r, oos_r)
            L += ["", f"回测最优(未达标,仅作默认参数):{cfg['name']} — "
                      f"IS {is_r['acc']}% / OOS {oos_r['acc']}%,OOS 净@0.50 ${oos_r['net@0.50']}"]

    L += ["", "> 口径:结算制;假设每盘固定 $5;成交价为固定档位(真实挂单可能不成交,",
          "> 吃单价可能劣于 0.51)。IS 选参存在多重比较,以 OOS 与模拟盘为准。"]

    (HERE / "PREBET.md").write_text("\n".join(L), encoding="utf-8")

    # merge the pick into picks.json so the strategy center shows pre_trend
    if pick:
        cfg, is_r, oos_r = pick
        params = ({"signal": "revert" if cfg["flip"] else "momo",
                   "lookback_sec": cfg["lb"], "min_move_pct": cfg["thr"]}
                  if cfg["kind"] == "momo" else
                  {"signal": "streak_fade" if cfg["flip"] else "streak_follow",
                   "streak_k": cfg["k"]})
        params["lead_sec"] = cfg["lead"]
        params["max_price"] = 0.51
        ok = oos_r["net@0.51"] >= 20 and oos_r["acc"] > 51 and oos_r["trades"] >= 50
        entry = {
            "strategy": "pre_trend", "params": params, "entry_delay": 0,
            "is": {"trades": is_r["trades"], "win_rate": is_r["acc"],
                   "ev_usd": is_r["ev@0.51"], "net_usd": is_r["net@0.51"], "max_dd": None},
            "oos": {"trades": oos_r["trades"], "win_rate": oos_r["acc"],
                    "ev_usd": oos_r["ev@0.51"], "net_usd": oos_r["net@0.51"], "max_dd": None},
            "verdict": "✅ 上架" if ok else "⚠️ 观察",
        }
        picks_p = HERE / "picks.json"
        picks = json.loads(picks_p.read_text()) if picks_p.exists() else []
        picks = [p for p in picks if p["strategy"] != "pre_trend"] + [entry]
        picks_p.write_text(json.dumps(picks, indent=1, ensure_ascii=False))
        (HERE / "prebet_pick.json").write_text(json.dumps(entry, ensure_ascii=False))

    print("\n".join(L))


if __name__ == "__main__":
    main()
