"""Env secrets + runtime-default settings (seeded into DB, admin-editable)."""
import os

CLAWBY_API_KEY = os.environ.get("CLAWBY_API_KEY", "")
CLAWBY_BASE = os.environ.get("CLAWBY_BASE", "https://api.openclawby.com")

PM_PRIVATE_KEY = os.environ.get("PM_PRIVATE_KEY", "")
PM_FUNDER = os.environ.get("PM_FUNDER", "")
PM_SIGNATURE_TYPE = int(os.environ.get("PM_SIGNATURE_TYPE", "0"))
PM_RELAYER_API_KEY = os.environ.get("PM_RELAYER_API_KEY", "")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
DB_PATH = os.environ.get("DB_PATH", "pmbot.db")
PORT = int(os.environ.get("PORT", "8643"))

POLYGON_RPC = os.environ.get("POLYGON_RPC", "https://polygon-bor-rpc.publicnode.com")

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
SERIES_PREFIX = "btc-updown-5m"
ROUND_SEC = 300

DEFAULT_SETTINGS = {
    "usd_per_market": "5",        # fallback stake (per-strategy value wins)
    "take_profit_pct": "20",      # sell held tokens at entry*(1+X%)
    "horizon": "6",               # how many upcoming rounds to manage (30 min)
    "strategy": "pre_trend",      # legacy single-strategy key (kept for compat)
    "entry_delay_sec": "20",      # fallback entry delay (per-strategy wins)
    "live_enabled": "0",          # master switch — OFF until user flips it
    "auto_redeem": "1",           # live: auto redeemPositions for resolved wins
    "daily_loss_halt_usd": "30",  # GLOBAL halt: stop opening after this loss/day
    "max_open_usd": "40",         # total exposure cap across all strategies
    "overpay_cap": "0.85",        # never buy a side above this probability
    # multi-strategy: which strategies run + per-strategy sizing/risk
    "enabled_strategies": '["pre_trend"]',
    "strat_cfg": '{"pre_trend": {"shares": 5, "daily_loss": 10, "entry_delay": 0},'
                 ' "fair_value": {"shares": 10, "daily_loss": 15, "entry_delay": 60},'
                 ' "tick_momo": {"shares": 10, "daily_loss": 10, "entry_delay": 60},'
                 ' "open_burst": {"shares": 10, "daily_loss": 10, "entry_delay": 60},'
                 ' "prev_reverse": {"shares": 10, "daily_loss": 10, "entry_delay": 10},'
                 ' "mystic_east": {"shares": 5, "daily_loss": 260, "entry_delay": 0}}',
    # per-strategy tunables (JSON, admin-editable)
    "params": '{"edge_min": 0.06, "price_margin": 0.02, "burst_min": 0.05,'
              ' "rev_min": 0.15, "momo_window": 60, "lead_sec": 600,'
              ' "lookback_sec": 600, "min_move_pct": 0.2, "signal": "revert",'
              ' "max_price": 0.51, "cover": 1}',
}
