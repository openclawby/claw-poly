"""Deterministic Polymarket wallet addresses derived from the signer EOA.

Polymarket账户体系过渡期:网页端仍用旧代理钱包(Gnosis Safe),API/SDK 用新的
充值钱包。两者都由同一把私钥控制,地址均为 CREATE2 确定性推导(常量取自官方
SDK 的 production 环境配置),因此无需保存,随时可从私钥重算。
"""
from eth_utils import keccak, to_checksum_address

SAFE_FACTORY = "0xaacFeEa03eb1561C4e67d661e40682Bd20E3541b"
SAFE_INIT_CODE_HASH = "0x2bce2127ff07fb632d16c8347c4ebf501f4841168bed00d9e6ef715ddb6fcecf"


def _create2(factory: str, salt: bytes, init_code_hash: str) -> str:
    payload = (b"\xff" + bytes.fromhex(factory[2:])
               + salt + bytes.fromhex(init_code_hash[2:]))
    return to_checksum_address(keccak(payload)[12:])


def legacy_safe_address(signer: str) -> str:
    """Website-side proxy wallet (signature type 2) for this signer."""
    if not (signer or "").startswith("0x") or len(signer) != 42:
        return ""
    salt = keccak(bytes(12) + bytes.fromhex(signer[2:]))
    return _create2(SAFE_FACTORY, salt, SAFE_INIT_CODE_HASH)


PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"     # Polymarket USD


def pusd_balance(address: str, rpc: str) -> float:
    """On-chain pUSD balance (USD). 0.0 on any failure."""
    if not address:
        return 0.0
    import json as _j
    import urllib.request
    data = "0x70a08231" + "0" * 24 + address[2:].lower()
    body = _j.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                     "params": [{"to": PUSD, "data": data}, "latest"]}).encode()
    req = urllib.request.Request(rpc, body, {"Content-Type": "application/json",
                                             "User-Agent": "claw-poly/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return round(int(_j.loads(r.read())["result"], 16) / 1e6, 2)
    except Exception:  # noqa: BLE001
        return 0.0


def signer_address(private_key: str) -> str:
    if not private_key:
        return ""
    from eth_account import Account
    return Account.from_key(private_key).address
