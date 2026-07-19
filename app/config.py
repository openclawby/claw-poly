"""Paper-only runtime configuration and research settings."""
import os

CLAWBY_API_KEY = os.environ.get("CLAWBY_API_KEY", "")
CLAWBY_BASE = os.environ.get("CLAWBY_BASE", "https://api.openclawby.com")

# 【PAPER_ONLY】Hard-coded: no environment, database, API, or UI override exists.
PAPER_ONLY = True
HOST = "127.0.0.1"
DB_PATH = os.environ.get("DB_PATH", "pmbot.db")
PORT = int(os.environ.get("PORT", "8643"))

SERIES_PREFIX = "btc-updown-5m"
ROUND_SEC = 300

LIVE_TRADING_CREDENTIAL_ENV_VARS = (
    "PM_PRIVATE_KEY",
    "PM_FUNDER",
    "PM_SIGNATURE_TYPE",
    "PM_RELAYER_API_KEY",
    "CLOB_API_KEY",
    "CLOB_API_SECRET",
    "CLOB_API_PASSPHRASE",
    "CLOB_SECRET",
    "CLOB_PASSPHRASE",
    "POLYMARKET_PRIVATE_KEY",
)

PAPER_ONLY_CREDENTIAL_ERROR = (
    "Paper-only research build detected a private key or live-trading "
    "credential. Remove it before starting."
)


def enforce_paper_only_environment():
    """Fail closed when a project-known live-trading variable is present."""
    if any(os.environ.get(name) for name in LIVE_TRADING_CREDENTIAL_ENV_VARS):
        raise RuntimeError(PAPER_ONLY_CREDENTIAL_ERROR)

DEFAULT_SETTINGS = {
    "usd_per_market": "5",        # fallback stake (per-strategy value wins)
    "take_profit_pct": "20",      # sell held tokens at entry*(1+X%)
    "horizon": "6",               # how many upcoming rounds to manage (30 min)
    "strategy": "pre_trend",      # legacy single-strategy key (kept for compat)
    "entry_delay_sec": "20",      # fallback entry delay (per-strategy wins)
    "daily_loss_halt_usd": "30",  # GLOBAL halt: stop opening after this loss/day
    "max_open_usd": "40",         # total exposure cap across all strategies
    "overpay_cap": "0.85",        # never buy a side above this probability
    # multi-strategy: which strategies run + per-strategy sizing/risk
    "enabled_strategies": '["pre_trend"]',
    "strat_cfg": '{"pre_trend": {"usd": 1, "daily_loss": 10, "entry_delay": 0},'
                 ' "fair_value": {"usd": 5, "daily_loss": 15, "entry_delay": 60},'
                 ' "tick_momo": {"usd": 5, "daily_loss": 10, "entry_delay": 60},'
                 ' "open_burst": {"usd": 5, "daily_loss": 10, "entry_delay": 60},'
                 ' "prev_reverse": {"usd": 5, "daily_loss": 10, "entry_delay": 10},'
                 ' "mystic_east": {"usd": 1, "daily_loss": 51, "entry_delay": 0}}',
    # per-strategy tunables (JSON, admin-editable)
    "params": '{"edge_min": 0.06, "price_margin": 0.02, "burst_min": 0.05,'
              ' "rev_min": 0.15, "momo_window": 60, "lead_sec": 600,'
              ' "lookback_sec": 600, "min_move_pct": 0.2, "signal": "revert",'
              ' "max_price": 0.51, "cover": 1}',
}
