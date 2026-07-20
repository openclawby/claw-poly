"""Wallet operations runner (executed with .venv-sdk python >=3.11).
Usage: wallet_ops.py balance | withdraw <to> <amount_usd>
       | pull <legacy_addr> <amount_usd>   (legacy website wallet -> trading wallet)
Prints a single JSON line. Uses the official polymarket-client via relayer
(gasless). pUSD (Polymarket USD) is the transferred token."""
import json
import os
import sys

PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"


def main():
    from eth_account import Account
    from polymarket import PRODUCTION, SecureClient
    from polymarket.auth import RelayerApiKey

    signer = os.environ.get("PM_SIGNER_ADDRESS") or Account.from_key(
        os.environ["PM_PRIVATE_KEY"]).address        # 缺省从私钥推导
    ak = RelayerApiKey(key=os.environ["PM_RELAYER_API_KEY"], address=signer)
    c = SecureClient.create(private_key=os.environ["PM_PRIVATE_KEY"],
                            environment=PRODUCTION, api_key=ak)
    cmd = sys.argv[1]
    if cmd == "balance":
        b = c.get_balance_allowance(asset_type="COLLATERAL")
        print(json.dumps({"ok": True, "address": str(c.wallet),
                          "balance": round(b.balance / 1e6, 2)}))
    elif cmd == "status":
        # 交易账户体检:地址 / 是否已部署 / 授权 / 余额
        b = c.get_balance_allowance(asset_type="COLLATERAL")
        allow = [int(v) for v in (b.allowances or {}).values()]
        print(json.dumps({
            "ok": True, "wallet": str(c.wallet), "wallet_type": str(c.wallet_type),
            "balance": round(b.balance / 1e6, 2),
            "approved": bool(allow) and max(allow) > 0,
        }))
    elif cmd == "onboard":
        # 幂等开通:SecureClient.create 已自动部署充值钱包;此处补交易授权
        b = c.get_balance_allowance(asset_type="COLLATERAL")
        allow = [int(v) for v in (b.allowances or {}).values()]
        approved = bool(allow) and max(allow) > 0
        tx = None
        if not approved:
            h = c.setup_trading_approvals()
            out = h.wait()
            tx = getattr(out, "transaction_hash", None) or str(out)
            b = c.get_balance_allowance(asset_type="COLLATERAL")
        print(json.dumps({"ok": True, "wallet": str(c.wallet),
                          "wallet_type": str(c.wallet_type),
                          "approved_tx": tx, "already": approved,
                          "balance": round(b.balance / 1e6, 2)}))
    elif cmd == "pull":
        legacy, amt = sys.argv[2], int(round(float(sys.argv[3]) * 1e6))
        dest = str(c.wallet)                       # 当前交易账户(充值钱包)
        cl = SecureClient.create(private_key=os.environ["PM_PRIVATE_KEY"],
                                 environment=PRODUCTION, api_key=ak, wallet=legacy)
        h = cl.transfer_erc20(token_address=PUSD, recipient_address=dest,
                              amount=amt, metadata="claw-poly pull from legacy")
        out = h.wait()
        tx = getattr(out, "transaction_hash", None) or str(out)
        print(json.dumps({"ok": True, "tx": tx, "to": dest}))
    elif cmd == "withdraw":
        to, amt = sys.argv[2], int(round(float(sys.argv[3]) * 1e6))
        h = c.transfer_erc20(token_address=PUSD, recipient_address=to,
                             amount=amt, metadata="claw-poly admin withdraw")
        out = h.wait()
        tx = getattr(out, "transaction_hash", None) or str(out)
        print(json.dumps({"ok": True, "tx": tx}))
    else:
        print(json.dumps({"ok": False, "error": f"unknown cmd {cmd}"}))
        sys.exit(2)


if __name__ == "__main__":
    main()
