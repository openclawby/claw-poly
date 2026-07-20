"""SQLite: settings / rounds(markets) / positions(per strategy) / orders /
equity / meta.

v2 schema: `rounds` holds market-level facts only (tokens, open/close/result);
`positions` holds one row per (round, strategy) bet. A legacy v1 `rounds`
table (with state/side columns) is migrated automatically on startup.
"""
import json
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()
_conn = None


def _migrate_v1(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(rounds)")]
    if "state" not in cols:
        return
    strat = "pre_trend"
    row = conn.execute("SELECT value FROM settings WHERE key='strategy'").fetchone()
    if row and row[0]:
        strat = row[0]
    conn.executescript("""
    CREATE TABLE rounds_v2 (
        slug TEXT PRIMARY KEY,
        start_ts INTEGER NOT NULL, end_ts INTEGER NOT NULL,
        token_up TEXT, token_down TEXT, tick REAL,
        open_price REAL, close_price REAL, result TEXT,
        updated_ts INTEGER
    );
    """)
    conn.execute("""
    INSERT INTO rounds_v2(slug,start_ts,end_ts,token_up,token_down,tick,
                          open_price,close_price,result,updated_ts)
    SELECT slug,start_ts,end_ts,token_up,token_down,tick,
           open_price,close_price,result,updated_ts FROM rounds
    """)
    conn.execute("""
    INSERT INTO positions(slug,strategy,state,side,entry_price,usd,shares,
                          order_id,tp_order_id,reason,pnl,mode,updated_ts)
    SELECT slug,?,state,side,entry_price,usd,shares,order_id,tp_order_id,
           reason,pnl,mode,updated_ts
    FROM rounds WHERE state IN ('ordered','holding','tp_set','settled','skipped')
    """, (strat,))
    conn.execute("DROP TABLE rounds")
    conn.execute("ALTER TABLE rounds_v2 RENAME TO rounds")


def init():
    global _conn
    _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock, _conn:
        _conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rounds (
            slug TEXT PRIMARY KEY,
            start_ts INTEGER NOT NULL, end_ts INTEGER NOT NULL,
            token_up TEXT, token_down TEXT, tick REAL,
            open_price REAL, close_price REAL, result TEXT,
            updated_ts INTEGER
        );
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL, strategy TEXT NOT NULL,
            state TEXT NOT NULL,               -- ordered|tp_set|settled|skipped
            side TEXT, entry_price REAL, usd REAL, shares REAL,
            order_id TEXT, tp_order_id TEXT, reason TEXT,
            pnl REAL, mode TEXT NOT NULL DEFAULT 'paper',
            updated_ts INTEGER,
            UNIQUE(slug, strategy)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL, slug TEXT NOT NULL, kind TEXT NOT NULL,
            side TEXT, price REAL, usd REAL, order_id TEXT, mode TEXT,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS equity (
            ts INTEGER PRIMARY KEY, realized REAL NOT NULL, mode TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        _migrate_v1(_conn)
        ocols = [r[1] for r in _conn.execute("PRAGMA table_info(orders)")]
        if "strategy" not in ocols:
            _conn.execute("ALTER TABLE orders ADD COLUMN strategy TEXT")
        pcols = [r[1] for r in _conn.execute("PRAGMA table_info(positions)")]
        if "tp_price" not in pcols:
            _conn.execute("ALTER TABLE positions ADD COLUMN tp_price REAL")
        if "redeemed" not in pcols:
            _conn.execute("ALTER TABLE positions ADD COLUMN redeemed INTEGER DEFAULT 0")
        rcols = [r[1] for r in _conn.execute("PRAGMA table_info(rounds)")]
        if "condition_id" not in rcols:
            _conn.execute("ALTER TABLE rounds ADD COLUMN condition_id TEXT")
        for k, v in config.DEFAULT_SETTINGS.items():
            _conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))


def get_settings():
    with _lock:
        rows = _conn.execute("SELECT key,value FROM settings").fetchall()
    s = {r["key"]: r["value"] for r in rows}

    def num(key):
        try:
            return float(s.get(key, config.DEFAULT_SETTINGS.get(key, "0")))
        except ValueError:
            return float(config.DEFAULT_SETTINGS.get(key, "0"))

    def jload(key, default):
        try:
            v = json.loads(s.get(key) or "")
            return v if isinstance(v, type(default)) else default
        except ValueError:
            return default

    return {
        "usd_per_market": num("usd_per_market"),
        "take_profit_pct": num("take_profit_pct"),
        "horizon": int(num("horizon")),
        "strategy": s.get("strategy", "pre_trend"),
        "entry_delay_sec": int(num("entry_delay_sec")),
        "live_enabled": s.get("live_enabled", "0") == "1",
        "auto_redeem": s.get("auto_redeem", "1") == "1",
        "daily_loss_halt_usd": num("daily_loss_halt_usd"),
        "max_open_usd": num("max_open_usd"),
        "overpay_cap": num("overpay_cap"),
        "params": jload("params", {}),
        "enabled_strategies": jload("enabled_strategies", []),
        "strat_cfg": jload("strat_cfg", {}),
        "_raw": s,
    }


def save_settings(updates):
    with _lock, _conn:
        for k, v in updates.items():
            if k in config.DEFAULT_SETTINGS:
                _conn.execute("REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(v)))


# -- rounds (market facts) -----------------------------------------------------

def upsert_round(slug, **kw):
    kw.pop("state", None)                     # legacy callers
    kw["updated_ts"] = int(time.time())
    with _lock, _conn:
        row = _conn.execute("SELECT slug FROM rounds WHERE slug=?", (slug,)).fetchone()
        if row is None:
            cols = ["slug"] + list(kw)
            _conn.execute(f"INSERT INTO rounds({','.join(cols)}) "
                          f"VALUES({','.join('?' * len(cols))})",
                          [slug] + list(kw.values()))
        else:
            sets = ",".join(f"{k}=?" for k in kw)
            _conn.execute(f"UPDATE rounds SET {sets} WHERE slug=?",
                          list(kw.values()) + [slug])


def get_round(slug):
    with _lock:
        row = _conn.execute("SELECT * FROM rounds WHERE slug=?", (slug,)).fetchone()
    return dict(row) if row else None


def rounds_window(now, back=420, limit=160):
    """Markets still relevant to the engine: recent + upcoming."""
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM rounds WHERE end_ts > ? ORDER BY start_ts LIMIT ?",
            (int(now) - back, limit)).fetchall()
    return [dict(r) for r in rows]


def recent_rounds(limit=40):
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM rounds ORDER BY start_ts DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# -- positions ------------------------------------------------------------------

def get_position(slug, strategy):
    with _lock:
        row = _conn.execute(
            "SELECT * FROM positions WHERE slug=? AND strategy=?",
            (slug, strategy)).fetchone()
    return dict(row) if row else None


def insert_position(slug, strategy, **kw):
    kw.setdefault("state", "skipped")
    kw["updated_ts"] = int(time.time())
    cols = ["slug", "strategy"] + list(kw)
    with _lock, _conn:
        _conn.execute(
            f"INSERT OR IGNORE INTO positions({','.join(cols)}) "
            f"VALUES({','.join('?' * len(cols))})",
            [slug, strategy] + list(kw.values()))


def update_position(slug, strategy, **kw):
    kw["updated_ts"] = int(time.time())
    sets = ",".join(f"{k}=?" for k in kw)
    with _lock, _conn:
        _conn.execute(f"UPDATE positions SET {sets} WHERE slug=? AND strategy=?",
                      list(kw.values()) + [slug, strategy])


def open_usd():
    with _lock:
        row = _conn.execute(
            "SELECT COALESCE(SUM(usd),0) s FROM positions "
            "WHERE state IN ('ordered','holding','tp_set')").fetchone()
    return float(row["s"])


def realized_today(mode, strategy=None):
    day0 = int(time.time()) // 86400 * 86400
    q = ("SELECT COALESCE(SUM(p.pnl),0) s FROM positions p "
         "JOIN rounds r ON r.slug=p.slug "
         "WHERE p.state='settled' AND p.mode=? AND r.end_ts>=?")
    args = [mode, day0]
    if strategy:
        q += " AND p.strategy=?"
        args.append(strategy)
    with _lock:
        row = _conn.execute(q, args).fetchone()
    return float(row["s"])


def position_rows(limit=300, state="", mode="", side="", result="", strategy=""):
    """Position rows joined with market fields + upcoming pending markets."""
    conds, args = [], []
    for col, val in (("p.state", state), ("p.mode", mode), ("p.side", side),
                     ("r.result", result), ("p.strategy", strategy)):
        if val:
            conds.append(f"{col}=?")
            args.append(val)
    q = ("SELECT r.slug, r.start_ts, r.end_ts, r.token_up, r.token_down, r.tick,"
         " r.open_price, r.close_price, r.result, p.strategy, p.state, p.side,"
         " p.entry_price, p.usd, p.shares, p.order_id, p.tp_order_id, p.tp_price,"
         " p.reason, p.pnl, p.mode, p.updated_ts"
         " FROM positions p JOIN rounds r ON r.slug=p.slug")
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY r.start_ts DESC, p.strategy LIMIT ?"
    with _lock:
        rows = [dict(r) for r in _conn.execute(q, args + [max(1, min(int(limit), 3000))])]
        if not state or state == "pending":
            now = int(time.time())
            pend = _conn.execute(
                "SELECT r.* FROM rounds r WHERE r.end_ts > ? "
                "AND NOT EXISTS (SELECT 1 FROM positions p WHERE p.slug=r.slug) "
                "ORDER BY r.start_ts DESC LIMIT 12", (now,)).fetchall()
            rows = [dict(p) | {"strategy": None, "state": "pending", "side": None,
                               "entry_price": None, "usd": None, "shares": None,
                               "order_id": None, "tp_order_id": None, "tp_price": None,
                               "reason": None, "pnl": None, "mode": None}
                    for p in pend] + rows
    rows.sort(key=lambda x: (-(x["start_ts"] or 0), x.get("strategy") or ""))
    return rows


def positions_of(slug):
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM positions WHERE slug=? ORDER BY strategy", (slug,)).fetchall()
    return [dict(r) for r in rows]


def recent_positions(limit=40):
    with _lock:
        rows = _conn.execute(
            "SELECT p.*, r.start_ts, r.end_ts FROM positions p "
            "JOIN rounds r ON r.slug=p.slug ORDER BY r.start_ts DESC, p.strategy "
            "LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# -- orders / equity / meta ------------------------------------------------------

def log_order(slug, kind, side=None, price=None, usd=None, order_id=None,
              mode="paper", note="", strategy=""):
    with _lock, _conn:
        _conn.execute(
            "INSERT INTO orders(ts,slug,kind,side,price,usd,order_id,mode,note,strategy) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (int(time.time()), slug, kind, side, price, usd, order_id, mode,
             note[:200], strategy))


def orders_full(limit=300, kind="", mode="", slug="", strategy=""):
    conds, args = [], []
    for col, val in (("kind", kind), ("mode", mode), ("slug", slug),
                     ("strategy", strategy)):
        if val:
            conds.append(f"{col}=?")
            args.append(val)
    q = "SELECT * FROM orders"
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY id DESC LIMIT ?"
    with _lock:
        rows = _conn.execute(q, args + [max(1, min(int(limit), 3000))]).fetchall()
    return [dict(r) for r in rows]


def recent_orders(limit=50):
    return orders_full(limit)


def record_equity(realized, mode):
    ts = int(time.time()) // 60 * 60
    with _lock, _conn:
        _conn.execute("REPLACE INTO equity(ts,realized,mode) VALUES(?,?,?)",
                      (ts, realized, mode))


def equity_series(mode, limit=1440):
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM equity WHERE mode=? ORDER BY ts DESC LIMIT ?",
            (mode, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def set_meta(key, value):
    with _lock, _conn:
        _conn.execute("REPLACE INTO meta(key,value) VALUES(?,?)", (key, str(value)))


def get_meta(key, default=""):
    with _lock:
        row = _conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def positions_all_open():
    """All positions still in an open state, regardless of round age."""
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM positions WHERE state IN ('ordered','holding','tp_set')"
        ).fetchall()
    return [dict(r) for r in rows]


def unredeemed_live(limit=20):
    """Settled LIVE positions not yet redeemed, oldest first, round ended >2min.
    won=1 when any position on that slug won (has something to claim)."""
    now = int(time.time())
    with _lock:
        rows = _conn.execute(
            "SELECT p.slug, r.condition_id, r.end_ts, "
            " MAX(CASE WHEN p.pnl > 0 THEN 1 ELSE 0 END) AS won "
            "FROM positions p JOIN rounds r ON r.slug=p.slug "
            "WHERE p.mode='live' AND p.state='settled' AND COALESCE(p.redeemed,0)=0 "
            "AND r.end_ts < ? GROUP BY p.slug ORDER BY r.end_ts LIMIT ?",
            (now - 120, limit)).fetchall()
    return [dict(r) for r in rows]


def mark_redeemed(slug):
    with _lock, _conn:
        _conn.execute("UPDATE positions SET redeemed=1 WHERE slug=? AND mode='live'",
                      (slug,))


def prune():
    cutoff = int(time.time()) - 30 * 86400
    with _lock, _conn:
        _conn.execute("DELETE FROM positions WHERE slug IN "
                      "(SELECT slug FROM rounds WHERE end_ts < ?)", (cutoff,))
        _conn.execute("DELETE FROM rounds WHERE end_ts < ?", (cutoff,))
        _conn.execute("DELETE FROM orders WHERE ts < ?", (cutoff,))


# -- aggregates for the React admin ----------------------------------------------

def stats(mode, strategy=""):
    q = ("SELECT p.*, r.end_ts FROM positions p JOIN rounds r ON r.slug=p.slug "
         "WHERE p.state='settled' AND p.mode=?")
    args = [mode]
    if strategy:
        q += " AND p.strategy=?"
        args.append(strategy)
    q += " ORDER BY r.end_ts"
    with _lock:
        settled = _conn.execute(q, args).fetchall()
        states = _conn.execute(
            "SELECT state, COUNT(*) c FROM positions GROUP BY state").fetchall()
        pending = _conn.execute(
            "SELECT COUNT(*) c FROM rounds WHERE end_ts > ?",
            (int(time.time()),)).fetchone()["c"]
    rows = [dict(r) for r in settled]
    pnls = [r["pnl"] or 0.0 for r in rows]
    wins = sum(1 for p in pnls if p > 0)
    tp_hits = sum(1 for r in rows if "止盈" in (r["reason"] or ""))
    cum, curve = 0.0, []
    daily, by_side, by_hour, by_strat = {}, {}, {}, {}
    for r in rows:
        p = r["pnl"] or 0.0
        cum += p
        curve.append({"ts": r["end_ts"], "cum": round(cum, 2)})
        d = time.strftime("%m-%d", time.gmtime(r["end_ts"]))
        e = daily.setdefault(d, {"date": d, "trades": 0, "wins": 0, "pnl": 0.0})
        e["trades"] += 1
        e["wins"] += p > 0
        e["pnl"] = round(e["pnl"] + p, 2)
        sd = r["side"] or "?"
        e = by_side.setdefault(sd, {"side": sd, "trades": 0, "wins": 0, "pnl": 0.0})
        e["trades"] += 1
        e["wins"] += p > 0
        e["pnl"] = round(e["pnl"] + p, 2)
        h = int(r["end_ts"] % 86400 // 3600)
        e = by_hour.setdefault(h, {"hour": h, "trades": 0, "pnl": 0.0})
        e["trades"] += 1
        e["pnl"] = round(e["pnl"] + p, 2)
        sk = r["strategy"]
        e = by_strat.setdefault(sk, {"strategy": sk, "trades": 0, "wins": 0, "pnl": 0.0})
        e["trades"] += 1
        e["wins"] += p > 0
        e["pnl"] = round(e["pnl"] + p, 2)
    return {
        "trades": len(rows), "wins": wins, "losses": sum(1 for p in pnls if p < 0),
        "tp_hits": tp_hits,
        "win_rate": round(wins / len(rows) * 100, 1) if rows else 0,
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl": round(sum(pnls) / len(pnls), 4) if pnls else 0,
        "best": round(max(pnls), 2) if pnls else 0,
        "worst": round(min(pnls), 2) if pnls else 0,
        "curve": curve,
        "daily": sorted(daily.values(), key=lambda x: x["date"]),
        "by_side": list(by_side.values()),
        "by_hour": [by_hour[h] for h in sorted(by_hour)],
        "by_strategy": sorted(by_strat.values(), key=lambda x: -x["pnl"]),
        "states": {r["state"]: r["c"] for r in states} | {"pending": pending},
    }
