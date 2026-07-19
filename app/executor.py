"""Local paper-order execution for the research build."""
import logging
import time

from . import clawby, db

log = logging.getLogger("executor")

PAPER_ONLY_ERROR = "Live trading is disabled in this PAPER_ONLY research build."


def mode(settings=None):
    """The research build has exactly one execution mode."""
    return "paper"


async def _get_client():
    """【PAPER_ONLY】There is deliberately no CLOB client implementation."""
    raise RuntimeError(PAPER_ONLY_ERROR)


async def place_limit(round_row, side, usd, limit_price, settings, strategy=""):
    """Record a local simulated GTC buy and return its paper order id."""
    token = round_row["token_up"] if side == "up" else round_row["token_down"]
    if not token:
        raise ValueError("paper order requires a market token")
    tick = round_row.get("tick") or 0.01
    price = max(tick, min(round(round(limit_price / tick) * tick, 4), 1 - tick))
    shares = round(usd / price, 2)
    oid = f"paper:{round_row['slug']}:{side}:{time.time_ns()}"
    db.log_order(round_row["slug"], "buy_limit", side, price, usd, oid, "paper",
                 strategy=strategy)
    return oid, price, shares


async def place_tp(round_row, settings, strategy="", tp_price=None):
    """Record a local simulated take-profit order."""
    side = round_row["side"]
    tick = round_row.get("tick") or 0.01
    if tp_price is None:
        tp_price = round_row["entry_price"] * (1 + settings["take_profit_pct"] / 100)
    tp_price = max(tick, min(round(round(tp_price / tick) * tick, 4), 1 - tick))
    oid = f"paper-tp:{round_row['slug']}:{strategy or 'default'}:{time.time_ns()}"
    db.log_order(round_row["slug"], "sell_tp", side, tp_price, None, oid, "paper",
                 strategy=strategy)
    return oid, tp_price


async def order_filled(round_row, settings):
    """Simulate a fill when the public-data ask reaches the local limit."""
    token = round_row["token_up"] if round_row["side"] == "up" else round_row["token_down"]
    px = await clawby.best_prices(token)
    return bool(px and px["ask"] is not None
                and px["ask"] <= round_row["entry_price"] + 1e-9)


async def cancel_all():
    """【PAPER_ONLY】No remote cancellation exists; engine does not call this."""
    log.info("paper-only cancel_all requested; no remote client exists")
    return 0


async def cancel_order(order_id):
    """Cancel only local ids with an explicit simulated-order prefix."""
    if order_id.startswith("paper:"):
        parts = order_id.split(":", 3)
        slug = parts[1] if len(parts) > 1 else "paper-order"
    elif order_id.startswith("paper-tp:"):
        parts = order_id.split(":", 3)
        slug = parts[1] if len(parts) > 1 else "paper-order"
    else:
        log.warning("PAPER_ONLY rejected a non-simulated order cancellation")
        return False
    db.log_order(slug, "cancel", order_id=order_id, mode="paper",
                 note="local paper cancellation")
    return True
