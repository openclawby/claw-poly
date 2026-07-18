"""Auto-redeem resolved LIVE winnings into USDC.e (Polygon on-chain).

Mechanics: winning outcome shares are ERC-1155 tokens on the Gnosis
Conditional Token Framework; `redeemPositions(collateral, 0x0, conditionId,
[1,2])` burns them and credits USDC.e. The btc-updown-5m series is
negRisk=false, so the plain CTF path is sufficient.

Scope guards (all must hold, otherwise this module is a no-op):
- live mode with PM_PRIVATE_KEY present
- signature type 0 (EOA). Proxy/Magic accounts (1/2) are auto-paid by
  Polymarket's operator and are skipped here.
- the condition is resolved on-chain (payoutDenominator > 0)
Losing positions are just marked redeemed (nothing to claim).
Gas: the signer wallet needs a little POL; txs are sent sequentially,
at most `limit` per sweep.
"""
import asyncio
import logging

from . import clawby, config, db

log = logging.getLogger("redeem")

CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDCE = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
ABI = [
    {"name": "redeemPositions", "type": "function",
     "stateMutability": "nonpayable", "outputs": [],
     "inputs": [{"name": "collateralToken", "type": "address"},
                {"name": "parentCollectionId", "type": "bytes32"},
                {"name": "conditionId", "type": "bytes32"},
                {"name": "indexSets", "type": "uint256[]"}]},
    {"name": "payoutDenominator", "type": "function",
     "stateMutability": "view",
     "inputs": [{"name": "", "type": "bytes32"}],
     "outputs": [{"name": "", "type": "uint256"}]},
]

_w3 = None
_ctf = None


def _get_w3():
    global _w3, _ctf
    if _w3 is None:
        from web3 import Web3
        _w3 = Web3(Web3.HTTPProvider(config.POLYGON_RPC,
                                     request_kwargs={"timeout": 20}))
        _ctf = _w3.eth.contract(address=Web3.to_checksum_address(CTF), abi=ABI)
    return _w3, _ctf


async def _condition_id(r):
    """rounds.condition_id, fetched once via relay if missing."""
    if r.get("condition_id"):
        return r["condition_id"]
    info = await clawby.market_by_slug(r["slug"])
    cid = (info or {}).get("condition_id")
    if cid:
        db.upsert_round(r["slug"], condition_id=cid)
    return cid


def _redeem_tx(cid):
    """Sync: check resolution + send redeemPositions. Returns tx hash or None."""
    from web3 import Web3
    w3, ctf = _get_w3()
    if not w3.is_connected():
        raise RuntimeError(f"RPC 不可达: {config.POLYGON_RPC}")
    cond = Web3.to_bytes(hexstr=cid)
    if ctf.functions.payoutDenominator(cond).call() == 0:
        return None                                   # oracle 未解决,下轮再试
    from eth_account import Account
    acct = Account.from_key(config.PM_PRIVATE_KEY)
    fn = ctf.functions.redeemPositions(
        Web3.to_checksum_address(USDCE), b"\x00" * 32, cond, [1, 2])
    tx = fn.build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 220000,
        "gasPrice": int(w3.eth.gas_price * 1.2),
        "chainId": config.CHAIN_ID,
    })
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction
                                    if hasattr(signed, "raw_transaction")
                                    else signed.rawTransaction)
    return h.hex()


async def run_once(limit=3):
    """One sweep: redeem up to `limit` resolved winning conditions."""
    if not config.PM_PRIVATE_KEY or config.PM_SIGNATURE_TYPE != 0:
        return
    rows = db.unredeemed_live(limit=20)
    sent = 0
    for r in rows:
        won = r["won"]
        if not won:                                    # 输的没东西可赎,直接标记
            db.mark_redeemed(r["slug"])
            continue
        if sent >= limit:
            break
        try:
            cid = await _condition_id(r)
            if not cid:
                continue
            txh = await asyncio.to_thread(_redeem_tx, cid)
            if txh is None:
                continue                               # 未解决,保留待下轮
            db.mark_redeemed(r["slug"])
            db.log_order(r["slug"], "redeem", note=f"tx={txh}", mode="live")
            log.info("redeemed %s tx=%s", r["slug"], txh)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("redeem %s failed: %s", r["slug"], exc)
            break                                      # RPC/gas 问题,别刷循环
