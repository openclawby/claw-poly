"""Prediction strategies for 5-minute BTC up/down rounds.

decide(round_row, now, market_up_price) -> Signal | None
Signal.side is "up"/"down"; limit_price is the probability we are willing to
pay for that side's token. All tunables come from settings["params"].
"""
import json
import logging
import math
from dataclasses import dataclass

from . import btc, db

log = logging.getLogger("strategy")


@dataclass
class Signal:
    side: str
    limit_price: float
    reason: str


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


class Base:
    key = "base"
    # entry timing: seconds AFTER round start when decide() becomes active
    def __init__(self, settings, cfg=None):
        self.s = settings
        self.p = settings.get("params", {})
        c = cfg or {}
        # 交易所按股数管控,最小 5 股/单;金额 = 股数 × 成交价(下单时算)
        self.shares = max(5, int(c.get("shares", c.get("usd", 5) or 5)))
        self.daily_loss = float(c.get("daily_loss",
                                      settings.get("daily_loss_halt_usd", 30)))
        self.entry_delay = int(c.get("entry_delay",
                                     settings.get("entry_delay_sec", 20)))

    def entry_ts(self, round_row):
        return round_row["start_ts"] + self.entry_delay

    def wants(self, round_row):
        """Cheap pre-screen BEFORE any orderbook fetch (override to skip)."""
        return True

    def tp_price(self, entry_price, settings):
        """Take-profit price after a fill. float -> place a book sell at that
        price; None -> hold to settlement (no TP order)."""
        return (entry_price or 0) * (1 + settings.get("take_profit_pct", 20) / 100)

    def decide(self, round_row, now, up_price):
        raise NotImplementedError


class FairValue(Base):
    """Theoretical P(Up) from drift-so-far + realized vol vs market price.
    Buys whichever side the market underprices by >= edge_min."""
    key = "fair_value"

    def decide(self, round_row, now, up_price):
        open_p = round_row.get("open_price")
        cur = btc.price()
        if not open_p or not cur or up_price is None:
            return None
        t_rem = round_row["end_ts"] - now
        if t_rem < 20:                       # too late, spreads blow out
            return None
        drift = (cur - open_p) / open_p
        sigma = btc.realized_vol(600)
        if not sigma:
            return None
        denom = sigma * math.sqrt(t_rem)
        if denom <= 0:
            return None
        p_up = _phi(drift / denom)
        edge_min = float(self.p.get("edge_min", 0.06))
        margin = float(self.p.get("price_margin", 0.02))
        if p_up - up_price >= edge_min:
            return Signal("up", round(min(p_up - margin, 0.99), 2),
                          f"P(Up)={p_up:.2f} vs mkt {up_price:.2f}")
        down_price = 1 - up_price
        if (1 - p_up) - down_price >= edge_min:
            return Signal("down", round(min(1 - p_up - margin, 0.99), 2),
                          f"P(Down)={1-p_up:.2f} vs mkt {down_price:.2f}")
        return None


class TickMomo(Base):
    """Sign of the last momo_window seconds' slope, decided right at entry."""
    key = "tick_momo"

    def decide(self, round_row, now, up_price):
        win = int(self.p.get("momo_window", 60))
        move = btc.change(win)
        if move is None or up_price is None:
            return None
        if abs(move) < float(self.p.get("momo_min", 0.02)):
            return None
        side = "up" if move > 0 else "down"
        price = up_price if side == "up" else 1 - up_price
        return Signal(side, round(min(price + 0.01, 0.99), 2),
                      f"{win}s move {move:+.3f}%")


class OpenBurst(Base):
    """If the round has already moved >= burst_min since open, follow it."""
    key = "open_burst"

    def decide(self, round_row, now, up_price):
        open_p = round_row.get("open_price")
        cur = btc.price()
        if not open_p or not cur or up_price is None:
            return None
        move = (cur - open_p) / open_p * 100
        if abs(move) < float(self.p.get("burst_min", 0.05)):
            return None
        side = "up" if move > 0 else "down"
        price = up_price if side == "up" else 1 - up_price
        return Signal(side, round(min(price + 0.01, 0.99), 2),
                      f"burst {move:+.3f}% since open")


class PrevReverse(Base):
    """After a large one-way previous round, bet the other way."""
    key = "prev_reverse"

    def decide(self, round_row, now, up_price):
        start = round_row["start_ts"]
        p0 = btc.price_at(start - 300)
        p1 = btc.price_at(start)
        if not p0 or not p1 or up_price is None:
            return None
        prev_move = (p1 - p0) / p0 * 100
        if abs(prev_move) < float(self.p.get("rev_min", 0.15)):
            return None
        side = "down" if prev_move > 0 else "up"
        price = up_price if side == "up" else 1 - up_price
        return Signal(side, round(min(price + 0.01, 0.99), 2),
                      f"prev round {prev_move:+.3f}%, fade")


class PreTrend(Base):
    """Pre-open bet: pick the direction BEFORE the round starts, from the
    lookback move, and leave a resting limit order (books quote ~0.50/0.51
    up to 25+ minutes ahead). preopen_only: after open it never enters."""
    key = "pre_trend"
    preopen_only = True

    def entry_ts(self, round_row):
        return round_row["start_ts"] - int(self.p.get("lead_sec", 600))

    def decide(self, round_row, now, up_price):
        if now >= round_row["start_ts"]:
            return None                          # pre-open window closed
        lb = int(self.p.get("lookback_sec", 600))
        thr = float(self.p.get("min_move_pct", 0.2))
        sig_mode = str(self.p.get("signal", "revert"))
        move = btc.change(lb)
        if move is None:
            return None
        side = "up" if move > 0 else "down"
        if sig_mode == "revert":
            side = "down" if side == "up" else "up"
        cap = float(self.p.get("max_price", 0.51))
        limit = cap
        if up_price is not None:
            book = up_price if side == "up" else 1 - up_price
            limit = min(cap, round(book + 0.01, 2))
        label = "fade" if sig_mode == "revert" else "follow"
        if abs(move) >= thr:                     # edge tier (strong move)
            return Signal(side, round(limit, 2),
                          f"pre-open {lb}s {move:+.3f}% {label}")
        if int(float(self.p.get("cover", 1))):   # coverage tier: buy every round
            return Signal(side, round(limit, 2),
                          f"cover {lb}s {move:+.3f}% {label}")
        return None


class MysticEast(Base):
    """神秘的东方力量:按预生成命盘对 50 个盘口下注,盘口一上架即买入,
    命盘走完自动收工不循环。纯娱乐,无任何科学依据。"""
    key = "mystic_east"

    def __init__(self, settings, cfg=None):
        super().__init__(settings, cfg)
        try:
            self.plan = json.loads(db.get_meta("mystic_plan") or "{}")
        except ValueError:
            self.plan = {}
        self.plan_map = {e["slug"]: e for e in self.plan.get("entries", [])}

    def entry_ts(self, round_row):
        return round_row["start_ts"] - 32400     # 盘口挂牌即下单(实测≥8h)

    def wants(self, round_row):
        return round_row["slug"] in self.plan_map   # 命盘之外的盘口零开销跳过

    def tp_price(self, entry_price, settings):
        if self.plan.get("tp_mode", "settle") == "book":
            return float(self.plan.get("tp_price", 0.8))
        return None                                  # 自动结算:不挂止盈单

    def decide(self, round_row, now, up_price):
        e = self.plan_map.get(round_row["slug"])
        if not e:
            return None
        cap = float(self.plan.get("max_price", 0.55))
        side = e["side"]
        limit = cap
        if up_price is not None:
            book = up_price if side == "up" else 1 - up_price
            limit = min(cap, round(book + 0.01, 2))
        return Signal(side, round(max(0.05, limit), 2), e["reason"])


STRATEGIES = {c.key: c for c in (FairValue, PreTrend, TickMomo, OpenBurst,
                                 PrevReverse, MysticEast)}

# UI metadata: names, full logic description, per-parameter docs (React admin)
META = {
    "pre_trend": {
        "name": "提前下注·动量反转",
        "tagline": "开盘前就把单挂好,不等盘中信号",
        "logic": "两层提前下注,保证每个盘口开盘前仓位已就位:开盘前 lead_sec 秒决策,"
                 "读取最近 lookback_sec 秒 BTC 涨跌幅 —— ①幅度 ≥ min_move_pct 时为「触发单」"
                 "(回测 56% 家族);②未达阈值时若 cover=1,仍按同方向下「补仓单」全覆盖"
                 "(回测 51.2%,约盈亏线)。signal=revert 反向下注(均值回归占优)。"
                 "限价以 max_price 为上限吃单成交(未开盘订单簿 0.50/0.51)。"
                 "注意:决策点 10 分钟(600s)是实测最优;提前 30 分钟全批量买入准确率掉到 "
                 "49.5%(≈-$41/天@$5),低价挂单(0.44-0.48)因逆向选择每单亏 20-50%,都别用。",
        "params": [
            {"key": "lead_sec", "label": "提前决策秒数 lead_sec",
             "hint": "开盘前多少秒决策并买入;600=提前10分钟(实测最优);1800=进视野立即买(实测-$41/天)"},
            {"key": "lookback_sec", "label": "回看窗口(秒)lookback_sec",
             "hint": "用最近多少秒的涨跌幅作为信号"},
            {"key": "min_move_pct", "label": "触发幅度(%)min_move_pct",
             "hint": "达到该幅度记为「触发单」(强信号);未达且 cover=1 时以「补仓单」参与"},
            {"key": "cover", "label": "全覆盖补仓 cover", "type": "select",
             "options": [{"value": 1, "label": "1 开启:每盘开盘前必买"},
                         {"value": 0, "label": "0 关闭:只做触发单"}],
             "hint": "开启后每个盘口开盘前都持仓(补仓单≈盈亏线);关闭则静默盘口不参与"},
            {"key": "signal", "label": "信号方向 signal", "type": "select",
             "options": [{"value": "revert", "label": "revert 反转(回测占优)"},
                         {"value": "momo", "label": "momo 顺势"}],
             "hint": "revert=大幅波动后赌回摆;momo=顺着近期趋势"},
            {"key": "max_price", "label": "最高买入价 max_price",
             "hint": "预挂限价的上限;0.51≈吃单立即成交,0.50=挂单等成交(可能不成交)"},
        ],
    },
    "fair_value": {
        "name": "理论定价套利",
        "tagline": "算出理论概率,只买市场定价错了的一边",
        "logic": "用「开盘至今的漂移」和「近 10 分钟已实现波动率」计算本盘理论上涨概率 "
                 "P(Up)=Φ(drift/(σ·√剩余秒)),再对比 Polymarket 实际报价:当某一边被市场"
                 "低估至少 edge_min 时,以「理论概率 − price_margin」为限价买入该边。"
                 "方向本质上跟随漂移,真正的优势在于对『该有多确定』的定价能力(回测中"
                 "置信度阶梯 53%→87% 严格兑现)。",
        "params": [
            {"key": "edge_min", "label": "最小定价偏差 edge_min",
             "hint": "理论概率须高出市场报价至少这么多才下单;越大越挑剔、单越少越准"},
            {"key": "price_margin", "label": "挂单让价 price_margin",
             "hint": "限价 = 理论概率 − 让价,留出安全边际,买得更便宜但可能不成交"},
        ],
    },
    "tick_momo": {
        "name": "秒级动量",
        "tagline": "最近 N 秒在涨就买涨,在跌就买跌",
        "logic": "读取入场时刻前 momo_window 秒的价格斜率,涨跌幅达到 momo_min(%)即顺势"
                 "买入对应方向,按市场现价 +0.01 挂限价。吃的是短时惯性延续。",
        "params": [
            {"key": "momo_window", "label": "动量窗口(秒)momo_window",
             "hint": "回看多少秒计算涨跌斜率"},
            {"key": "momo_min", "label": "触发涨跌幅(%)momo_min",
             "hint": "窗口内涨跌幅绝对值达到该百分比才触发"},
        ],
    },
    "open_burst": {
        "name": "开盘冲量",
        "tagline": "开盘后已经大幅偏离,就顺着冲的方向追",
        "logic": "若本盘开盘价到当前价的偏离达到 burst_min(%),判定单边冲量形成,顺势"
                 "买入该方向。5 分钟内大幅偏离后反转概率低于延续概率。",
        "params": [
            {"key": "burst_min", "label": "触发偏离(%)burst_min",
             "hint": "距开盘价的涨跌幅绝对值达到该百分比才追入"},
        ],
    },
    "mystic_east": {
        "name": "神秘的东方力量",
        "tagline": "🔮 纯娱乐策略:命理推演 50 盘,不构成任何投资建议",
        "logic": "输入姓名、生日(自动推演农历与年命五行)、性别、出生地,结合当日"
                 "内置万年历(日干支、建除十二神、黄道吉日判定)生成种子码,推演未来 "
                 "50 个盘口的涨跌方向与星级。盘口一上架即按命盘买入,50 盘走完自动"
                 "收工,不循环。同一个人同一天启动,命盘完全一致(可复现)。"
                 "郑重声明:方向本质是命理调味的随机数,期望约为 -点差,当娱乐消费。",
        "params": [],
        "fun": True,
    },
    "prev_reverse": {
        "name": "前盘反转",
        "tagline": "上一盘单边走完,这一盘赌回摆",
        "logic": "上一个 5 分钟盘单边波动超过 rev_min(%)时,本盘反向买入,博短线"
                 "均值回归。信号少但独立于盘中价格,入场最早。",
        "params": [
            {"key": "rev_min", "label": "前盘触发幅度(%)rev_min",
             "hint": "上一盘涨跌幅绝对值达到该百分比,本盘才反向入场"},
        ],
    },
}


# English variants for the bilingual admin (merged into META)
_META_EN = {
    "pre_trend": {
        "name_en": "Pre-Open Bettor",
        "tagline_en": "Positions are bought BEFORE each round opens — no in-round waiting",
        "logic_en": "Decides lead_sec before open from the last lookback_sec BTC move. "
                    "Two tiers: moves ≥ min_move_pct fire a trigger bet (56% family in "
                    "backtests); otherwise with cover=1 a same-direction cover bet keeps "
                    "every round pre-bought (~51.2%, near breakeven). signal=revert fades "
                    "the move (mean reversion wins on 5-min bars). Limits cross the "
                    "pre-open book (~0.50/0.51) capped at max_price. Tested: 10-min lead "
                    "is optimal; 30-min batch drops to 49.5% (≈-$41/day @$5); low maker "
                    "bids (0.44-0.48) lose 20-50%/fill to adverse selection.",
        "p_en": {"lead_sec": ("Decision lead (sec)", "Seconds before open to decide & buy; 600=10min (tested best)"),
                 "lookback_sec": ("Lookback window (sec)", "BTC move window used as the signal"),
                 "min_move_pct": ("Trigger move (%)", "Moves ≥ this are 'trigger' bets; below = 'cover' bets when cover=1"),
                 "cover": ("Full coverage", "1: buy every round pre-open (cover tier ≈ breakeven); 0: trigger bets only"),
                 "max_price": ("Max buy price", "Cap per share; 0.51≈instant taker fill, 0.50=maker (may not fill)")},
    },
    "fair_value": {
        "name_en": "Fair-Value Arbitrage",
        "tagline_en": "Compute the theoretical probability; buy only what the market misprices",
        "logic_en": "P(Up)=Φ(drift/(σ·√t_remaining)) from the drift since open and realized "
                    "vol (10-min window), compared with the live Polymarket quote. Buys a "
                    "side only when it is underpriced by ≥ edge_min, at limit = theoretical "
                    "prob − price_margin. Direction follows drift; the real edge is pricing "
                    "confidence (calibration ladder 53%→87% verified on backtests).",
        "p_en": {"edge_min": ("Min mispricing edge_min", "Theoretical prob must exceed market quote by at least this"),
                 "price_margin": ("Limit discount price_margin", "Limit = theoretical prob − margin; safer entry, may miss fills")},
    },
    "tick_momo": {
        "name_en": "Tick Momentum",
        "tagline_en": "Buy the direction of the last N seconds",
        "logic_en": "Reads the momo_window-second slope at entry; if |move| ≥ momo_min(%), "
                    "follows it with a limit at market+0.01. Rides short-term persistence.",
        "p_en": {"momo_window": ("Momentum window (sec)", "Lookback seconds for the slope"),
                 "momo_min": ("Trigger move (%)", "Minimum |move| within the window")},
    },
    "open_burst": {
        "name_en": "Opening Burst",
        "tagline_en": "If the round already moved hard since open, chase it",
        "logic_en": "When the move from round open reaches burst_min(%), joins the "
                    "direction — large early bursts continue more often than they revert.",
        "p_en": {"burst_min": ("Trigger burst (%)", "Minimum |move| from the round's open price")},
    },
    "prev_reverse": {
        "name_en": "Previous-Round Reversal",
        "tagline_en": "After a one-way round, bet the swing back",
        "logic_en": "If the previous 5-min round moved more than rev_min(%) one way, bets "
                    "the opposite direction this round (short-horizon mean reversion).",
        "p_en": {"rev_min": ("Previous move (%)", "Minimum |previous round move| to fade")},
    },
    "mystic_east": {
        "name_en": "Mysterious Eastern Power",
        "tagline_en": "🔮 Entertainment only — zero scientific validity",
        "logic_en": "Name, birthday (auto lunar conversion), gender and birthplace are "
                    "hashed with today's Chinese almanac (day pillar, Twelve Officers, "
                    "auspicious-day flag) into a seed that divines direction & stars for "
                    "up to 100 rounds. Buys each round as it lists (≥8h ahead), then "
                    "auto-retires. Same person + same day = identical, reproducible "
                    "destiny chart. Honest note: directions are feng-shui-flavored "
                    "randomness with negative expected value (the spread). Enjoy.",
        "p_en": {},
    },
}
for _k, _v in _META_EN.items():
    if _k in META:
        META[_k]["name_en"] = _v["name_en"]
        META[_k]["tagline_en"] = _v["tagline_en"]
        META[_k]["logic_en"] = _v["logic_en"]
        for _p in META[_k].get("params", []):
            if _p["key"] in _v["p_en"]:
                _p["label_en"], _p["hint_en"] = _v["p_en"][_p["key"]]
            for _o in _p.get("options", []) or []:
                _o.setdefault("label_en", str(_o["value"]))
for _p in META["pre_trend"]["params"]:
    if _p["key"] == "signal":
        for _o in _p["options"]:
            _o["label_en"] = ("revert — fade the move (backtest winner)"
                              if _o["value"] == "revert" else "momo — follow the trend")
    if _p["key"] == "cover":
        for _o in _p["options"]:
            _o["label_en"] = ("1 ON: buy every round pre-open"
                              if _o["value"] == 1 else "0 OFF: trigger bets only")


def enabled(settings):
    """Instances of every enabled strategy, carrying per-strategy cfg."""
    cfgs = settings.get("strat_cfg") or {}
    out = []
    for key in settings.get("enabled_strategies") or []:
        cls = STRATEGIES.get(key)
        if cls:
            out.append(cls(settings, cfgs.get(key)))
    return out


def active(settings):
    """Legacy single-strategy accessor (tests/back-compat)."""
    cls = STRATEGIES.get(settings.get("strategy"), FairValue)
    return cls(settings)
