# 🎲 claw-poly — PAPER ONLY research build

Strict paper-trading, backtesting, and strategy-research build for Polymarket BTC
5-minute Up/Down markets.

**This branch creates no real orders, connects no wallet, and uses no real
funds. Live-trading credentials are forbidden and make startup fail closed.**

## Features

- Six existing strategies with their original signal algorithms and defaults.
- Local simulated entry, take-profit, fill, cancellation, position, and PnL bookkeeping.
- Backtest and research reports.
- React administration console for paper dashboards, strategies, positions,
  rounds, orders, CSV export, and research parameters.
- Public/read-only market data through the Clawby relay.

## Requirements and installation

Prerequisites: Python 3.10+ and Node.js 18+.

```bash
python -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
```

`requirements-dev.txt` includes the runtime requirements plus the pinned pytest
version used by this branch. Runtime-only deployments may install
`requirements.txt` instead.

`CLAWBY_API_KEY` is an optional read-only market-data credential. Without it,
the application starts in a restricted local mode but cannot discover markets
or obtain relay orderbooks.

```bash
cp .env.example .env
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8643
```

Open `http://127.0.0.1:8643/admin`. Do not bind the service to a public or LAN
interface. The application enforces trusted local Host and write-origin checks.

## Paper-only safety boundary

- `PAPER_ONLY = True` is hard-coded and cannot be changed by environment,
  database, API, or UI.
- Wallet, signing, exchange-client, remote order-status, remote cancellation,
  and on-chain transaction implementations are absent.
- Known trading-credential environment variables cause startup rejection.
- Only order IDs beginning with `paper:` or `paper-tp:` can be cancelled locally.
- Legacy database trading controls and CLOB credentials are deleted without
  being read or logged during database initialization.

See [PAPER_ONLY_MIGRATION.md](PAPER_ONLY_MIGRATION.md) and
[SECURITY_AUDIT.md](SECURITY_AUDIT.md) for the complete boundary and evidence.

## Tests

```bash
./.venv/bin/python -m pytest tests/ -q
cd frontend && npm run build
```

## 中文

当前 `paper-only-hardening` 分支是严格的模拟盘、回测和策略研究版本。

**不会创建真实订单，不连接钱包，不使用真实资金。程序不接受交易凭据；检测到项目已知的私钥或交易凭据环境变量时会拒绝启动。**

保留功能：原有策略算法与默认参数、模拟下单与模拟撤单、模拟持仓与盈亏、回测、CSV 导出、公开/只读市场数据和本地研究管理台。

安装并构建后，只允许在本机启动：

```bash
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8643
```

`CLAWBY_API_KEY` 仅用于只读市场数据，可以保留；没有该 key 时应用仍能以受限研究模式启动，但行情与盘口 relay 不完整。不要配置任何钱包、签名、交易所或链上交易凭据。

## License

MIT — see [LICENSE](LICENSE).
