import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")

def test_slug_alignment():
    from app import markets
    slug, b = markets.slug_at(1784397601)
    assert slug == "btc-updown-5m-1784397600" and b % 300 == 0
    ups = markets.upcoming_slugs(6, now=1784397600)
    assert len(ups) == 6 and ups[5][1] - ups[0][1] == 1500

def test_db_settings_seed_and_positions():
    from app import db
    db.init()
    s = db.get_settings()
    assert s["usd_per_market"] == 5.0 and s["horizon"] == 6 and not s["live_enabled"]
    assert s["enabled_strategies"] == ["pre_trend"]
    assert s["strat_cfg"]["pre_trend"]["usd"] == 1
    now = int(time.time())
    db.upsert_round("btc-updown-5m-100", start_ts=now - 300, end_ts=now,
                    token_up="u", token_down="d")
    db.insert_position("btc-updown-5m-100", "pre_trend", state="ordered",
                       side="up", entry_price=0.51, usd=1.0, shares=1.96)
    db.insert_position("btc-updown-5m-100", "fair_value", state="ordered",
                       side="down", entry_price=0.6, usd=5.0, shares=8.3)
    assert db.open_usd() == 6.0                          # two strategies, same round
    db.update_position("btc-updown-5m-100", "pre_trend", state="settled", pnl=1.5)
    db.update_position("btc-updown-5m-100", "fair_value", state="settled", pnl=-5.0)
    assert db.realized_today("paper") == -3.5            # total across strategies
    assert db.realized_today("paper", "pre_trend") == 1.5  # per-strategy stop basis
    rows = db.position_rows(10)
    assert any(r["strategy"] == "fair_value" and r["pnl"] == -5.0 for r in rows)
    st = db.stats("paper")
    assert st["trades"] == 2 and len(st["by_strategy"]) == 2

def test_btc_buffer():
    from app import btc
    now = time.time()
    for i in range(120):
        btc._buf.append((now - 120 + i, 100000 + i))
    btc._last_price, btc._last_ts = 100119.0, now
    assert btc.price() == 100119.0
    assert btc.price_at(now - 60) == 100000 + 59 or abs(btc.price_at(now-60) - 100059) <= 1
    assert btc.change(60) is not None
    assert btc.realized_vol(100, step=5) is not None

def test_fair_value_direction():
    from app import btc, strategy
    now = time.time()
    btc._buf.clear()
    for i in range(700):
        btc._buf.append((now - 700 + i, 100000.0))   # flat vol -> tiny sigma
    btc._buf.append((now, 100200.0))                  # sudden +0.2%
    btc._last_price, btc._last_ts = 100200.0, now
    s = {"params": {"edge_min": 0.05, "price_margin": 0.02}, "entry_delay_sec": 20,
         "take_profit_pct": 20}
    fv = strategy.STRATEGIES["fair_value"](s)
    r = {"slug": "x", "start_ts": now - 60, "end_ts": now + 240,
         "open_price": 100000.0, "token_up": "t1", "token_down": "t2"}
    sig = fv.decide(r, now, up_price=0.55)   # market underprices Up after +0.2%
    assert sig is not None and sig.side == "up" and sig.limit_price <= 0.99

def test_paper_order_arith():
    import asyncio
    from app import db, executor
    r = {"slug": "s", "token_up": "u", "token_down": "d", "tick": 0.01}
    oid, price, shares = asyncio.get_event_loop().run_until_complete(
        executor.place_limit(r, "up", 5.0, 0.634, {"live_enabled": False}))
    assert oid.startswith("paper") and price == 0.63 and abs(shares - 5/0.63) < 0.02


def test_pre_trend_preopen_logic(monkeypatch):
    from app import strategy
    s = {"entry_delay_sec": 45, "params": {
        "lead_sec": 600, "lookback_sec": 600, "min_move_pct": 0.2,
        "signal": "revert", "max_price": 0.51, "cover": 0}}
    st = strategy.PreTrend(s)
    r = {"start_ts": 10000, "end_ts": 10300}
    assert st.entry_ts(r) == 10000 - 600          # decides 10 min before open
    assert st.preopen_only is True
    monkeypatch.setattr(strategy.btc, "change", lambda sec: +0.35)
    sig = st.decide(r, 9500, 0.505)               # pre-open, big up move
    assert sig.side == "down"                     # revert fades the move
    assert sig.limit_price <= 0.51
    monkeypatch.setattr(strategy.btc, "change", lambda sec: +0.05)
    assert st.decide(r, 9500, 0.505) is None      # below threshold, cover off
    s["params"]["cover"] = 1
    cov = strategy.PreTrend(s).decide(r, 9500, 0.505)
    assert cov.side == "down" and cov.reason.startswith("cover")  # coverage tier
    s["params"]["cover"] = 0
    monkeypatch.setattr(strategy.btc, "change", lambda sec: +0.35)
    assert st.decide(r, 10001, 0.505) is None     # after open -> never enters
    s["params"]["signal"] = "momo"
    sig = strategy.PreTrend(s).decide(r, 9500, 0.505)
    assert sig.side == "up"                       # momo follows the move


def test_mystic_almanac_and_plan():
    import datetime as _dt
    from app import mystic
    a = mystic.almanac(_dt.date(2000, 1, 1))
    assert a["day_ganzhi"] == "戊午"              # known anchor cross-check
    assert a["jianxing"] in "建除满平定执破危成收开闭"
    p1 = mystic.build_plan("张三", "1990-05-20", "男", "上海", 1784500000, n=50)
    p2 = mystic.build_plan("张三", "1990-05-20", "男", "上海", 1784500000, n=50)
    assert len(p1["entries"]) == 50
    assert [e["side"] for e in p1["entries"]] == [e["side"] for e in p2["entries"]]
    p3 = mystic.build_plan("李四", "1990-05-20", "男", "上海", 1784500000, n=50)
    assert [e["side"] for e in p1["entries"]] != [e["side"] for e in p3["entries"]]
    assert all(e["side"] in ("up", "down") and 1 <= e["stars"] <= 5
               for e in p1["entries"])
    assert p1["fate"]["element"] in "金木水火土"


def test_mystic_tp_modes(monkeypatch):
    import json as _j
    from app import db, strategy
    db.init()
    db.set_meta("mystic_plan", _j.dumps({
        "entries": [{"slug": "btc-updown-5m-1", "start_ts": 1, "side": "up",
                     "stars": 3, "reason": "r", "i": 1}],
        "tp_mode": "settle", "tp_price": 0.8, "max_price": 0.55}))
    st = strategy.MysticEast({"params": {}, "take_profit_pct": 95})
    assert st.tp_price(0.51, {"take_profit_pct": 95}) is None      # 自动结算
    db.set_meta("mystic_plan", _j.dumps({
        "entries": [], "tp_mode": "book", "tp_price": 0.8}))
    st2 = strategy.MysticEast({"params": {}})
    assert st2.tp_price(0.51, {"take_profit_pct": 95}) == 0.8      # 挂单止盈
    base = strategy.PreTrend({"params": {}})
    assert abs(base.tp_price(0.5, {"take_profit_pct": 20}) - 0.6) < 1e-9


def test_redeem_gating_and_query():
    import asyncio
    from app import config, db, redeem
    db.init()
    now = int(time.time())
    db.upsert_round("btc-updown-5m-900", start_ts=now - 900, end_ts=now - 600,
                    token_up="u", token_down="d", condition_id="0x" + "ab" * 32)
    db.insert_position("btc-updown-5m-900", "mystic_east", state="settled",
                       side="up", pnl=0.9, usd=1.0, mode="live")
    db.insert_position("btc-updown-5m-900", "pre_trend", state="settled",
                       side="down", pnl=-1.0, usd=1.0, mode="live")
    rows = db.unredeemed_live()
    assert len(rows) == 1 and rows[0]["won"] == 1          # 同盘有赢面 -> 待赎回
    db.mark_redeemed("btc-updown-5m-900")
    assert db.unredeemed_live() == []                       # 标记后不再扫描
    # 门禁:签名类型非 0 时 run_once 必须是空操作(不触网)
    old = config.PM_SIGNATURE_TYPE
    config.PM_SIGNATURE_TYPE = 2
    asyncio.get_event_loop().run_until_complete(redeem.run_once())
    config.PM_SIGNATURE_TYPE = old
