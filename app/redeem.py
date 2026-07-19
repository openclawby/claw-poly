"""Compatibility boundary for the removed on-chain redemption feature."""

PAPER_ONLY_REDEEM_ERROR = (
    "On-chain redemption is disabled in this PAPER_ONLY research build."
)


async def run_once(limit=3):
    """【PAPER_ONLY】Fail closed; no Web3 account, signing, or RPC path exists."""
    raise RuntimeError(PAPER_ONLY_REDEEM_ERROR)
