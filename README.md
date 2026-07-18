# 🎲 claw-poly

**Automated multi-strategy trading bot for Polymarket's BTC 5-minute Up/Down markets** — pre-open betting, disciplined backtesting, a React admin console, and one fortune-telling strategy for fun.

**Polymarket BTC 5 分钟涨跌盘多策略自动交易机器人** —— 开盘前预下注、严格回测纪律、React 管理台,外加一个纯娱乐的命理策略。

![Dashboard](docs/screenshots/dashboard.png)

---

## English

### What it does

claw-poly trades Polymarket's `btc-updown-5m` series (a new "will BTC close up or down?" market every 5 minutes, all day). It discovers rounds up to 8 hours before they open, decides direction, places limit orders, manages take-profits, books settlements, and rolls forward — hands-free.

### Features

- **6 built-in strategies, running concurrently** — each with its own stake size, daily stop-loss, entry timing and tunable parameters; independent positions per round:
  - `pre_trend` — buys **before the round opens** (mean-reversion signal; full-coverage or trigger-only mode)
  - `fair_value` — computes theoretical P(Up) from drift + realized vol, buys only market mispricings (73% OOS win rate in our backtests)
  - `tick_momo` / `open_burst` / `prev_reverse` — in-round momentum & reversal plays
  - `mystic_east` 🔮 — **entertainment only**: name + lunar birthday + the day's Chinese almanac seed a deterministic 1–100-round "destiny chart". Zero science, honest disclaimers included.
- **Backtest suite** — 7/15-day BTC 1-second data, train/validate split (IS/OOS), parameter-plateau checks, spread sensitivity; reports readable in-app
- **Paper / Live modes** — paper by default; live requires an explicit switch. The private key is validated locally, written only to your local `.env`, never echoed or uploaded
- **Auto-redeem** — resolved live winnings are swept into USDC.e on-chain automatically (EOA accounts; settings toggle, default on)
- **React admin console** — dashboard, strategy center with inline parameter editing, open-positions view with live quotes, full round/order history with CSV export, bilingual UI (中/EN)
- **Resilience** — price buffer backfills on restart (no cold-start blind spots), REST fallback when the WebSocket drops, log rotation, per-strategy + global loss halts

![Strategies](docs/screenshots/strategies.png)

### ⚠️ Requires a Clawby account

Market data (round discovery, orderbooks, price history) flows through the **[Clawby](https://openclawby.com)** relay. **You must register at [openclawby.com](https://openclawby.com) and get an API key** — the bot will not function without it. The free tier is sufficient for paper trading. Order signing happens locally via `py-clob-client` and never touches Clawby.

### Install

Prerequisites: Python 3.10+, Node.js 18+.

```bash
git clone <this repo> && cd claw-poly

# 1. backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 2. frontend (build once; rebuild only after UI changes)
cd frontend && npm install && npm run build && cd ..

# 3. config — put your Clawby key in .env
cp .env.example .env        # edit: CLAWBY_API_KEY=pk_...

# 4. run
set -a; source .env; set +a
./.venv/bin/uvicorn app.main:app --port 8643
# open http://127.0.0.1:8643/admin  (no login; binds to localhost only)
```

Backtests (optional but recommended reading):

```bash
./.venv/bin/python -m backtest.data      # 7-day BTC 1s + real-round odds samples
./.venv/bin/python -m backtest.report    # strategy grids -> backtest/REPORT.md
./.venv/bin/python -m backtest.data15    # 15-day dataset
./.venv/bin/python -m backtest.opt15     # pre_trend optimization -> OPT15.md
./.venv/bin/python -m pytest tests/ -q   # unit tests
```

### Going live (real money — read carefully)

1. In **Settings → Wallet private key**, paste your key: it is verified locally (address derivation), written to your local `.env`, and takes effect without restart. Set your **funder address** and **signature type** (0 = EOA, 1 = Magic/email, 2 = web proxy wallet).
2. Make sure the account has **USDC.e** balance + exchange allowance on Polygon, and (EOA accounts) a little **POL** for auto-redeem gas.
3. Flip the **LIVE** switch. Start small; compare real fills against paper before sizing up.

### Project structure

```
app/
├── main.py       FastAPI app · REST API · static admin hosting
├── engine.py     15s multi-strategy engine (position state machine, risk gates)
├── strategy.py   6 strategies + bilingual metadata
├── executor.py   paper simulation / live py-clob-client orders
├── redeem.py     on-chain auto-redeem of resolved winnings (CTF)
├── mystic.py     Chinese almanac math + destiny-chart generator (for fun)
├── markets.py    round discovery & settlement    ├── btc.py     BTC 1s price feed
├── clawby.py     Clawby relay client (throttled) ├── db.py      SQLite storage
└── admin.html    legacy single-page admin (/admin-lite)
frontend/         React 18 + Ant Design 5 + @ant-design/plots admin (Vite)
└── src/pages/    Dashboard · Strategies · Mystic · Positions · Rounds · Orders · Settings
backtest/         data fetchers · simulators · optimizers · reports (REPORT/OPT15/PREBET/COVER)
tests/            unit tests
```

### Disclaimer

5-minute binary markets are fast and close to efficiently priced. Backtests here use optimistic fill models; paper results are the honest referee. **This software is not financial advice; trade at your own risk.**

---

## 中文

### 这是什么

claw-poly 自动交易 Polymarket 的 `btc-updown-5m` 系列(每 5 分钟一个"BTC 涨还是跌"盘口,全天滚动)。盘口最早提前 8 小时挂牌,机器人自动发现、判方向、挂限价单、管理止盈、结算记账、滚动续盘,全程无人值守。

### 功能

- **6 个内置策略,支持同时运行** —— 每个策略独立设置每单金额、日止损、入场时机与参数,同一盘口各自独立持仓记账:
  - `pre_trend` 提前下注 —— **开盘前就买入**(均值回归信号,可全覆盖或只做强触发)
  - `fair_value` 理论定价套利 —— 漂移+波动率算理论概率,只买市场定错价的一边(回测验证段胜率 73%)
  - `tick_momo` 秒级动量 / `open_burst` 开盘冲量 / `prev_reverse` 前盘反转 —— 盘中策略
  - `mystic_east` 神秘的东方力量 🔮 —— **纯娱乐**:姓名+农历生辰+当日黄历(内置万年历推演干支/建除十二神)生成确定性命盘,一次推演 1~100 盘,买完自动收工。零科学性,免责声明写死在页面上。
- **回测体系** —— 7/15 天 BTC 秒级数据,训练/验证分离(IS/OOS),参数邻域平原检验、点差敏感性;报告管理台直接看
- **模拟 / 实盘双模式** —— 默认模拟;实盘需显式开关。私钥本地校验推导地址、只写入本机 `.env`,永不回显/上传
- **自动赎回** —— 实盘赢面份额链上自动赎回成 USDC.e(EOA 账户;设置页开关,默认开启)
- **React 管理台** —— 仪表盘、策略中心(卡片内直接调参)、当前持仓(实时报价+浮盈)、盘口/订单全量历史+CSV 导出、中英双语
- **可靠性** —— 重启自动回填价格缓冲(无冷启动盲区)、WebSocket 断线 REST 兜底、日志自动轮转、策略级+全局双层熔断

![Positions](docs/screenshots/positions.png)

### ⚠️ 必须注册 Clawby 才能完整使用

市场数据(盘口发现、订单簿、价格历史)通过 **[Clawby](https://openclawby.com)** 数据通道获取。**请先到 [openclawby.com](https://openclawby.com) 注册并获取 API Key**,填入 `.env` 后机器人才能工作;免费档足够跑模拟盘。下单签名由本地 `py-clob-client` 完成,私钥不经过 Clawby。

### 安装

前置:Python 3.10+、Node.js 18+。

```bash
git clone <本仓库> && cd claw-poly

# 1. 后端
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 2. 前端(构建一次即可;改 UI 后重跑 build)
cd frontend && npm install && npm run build && cd ..

# 3. 配置 —— 把 Clawby Key 填进 .env
cp .env.example .env        # 编辑:CLAWBY_API_KEY=pk_...

# 4. 启动
set -a; source .env; set +a
./.venv/bin/uvicorn app.main:app --port 8643
# 打开 http://127.0.0.1:8643/admin(免登录,仅监听本机)
```

回测(可选,但建议先看报告再交易):

```bash
./.venv/bin/python -m backtest.data      # 7 天 BTC 秒级数据 + 真实盘口赔率样本
./.venv/bin/python -m backtest.report    # 策略网格 -> backtest/REPORT.md
./.venv/bin/python -m backtest.data15    # 15 天数据集
./.venv/bin/python -m backtest.opt15     # pre_trend 调参 -> OPT15.md
./.venv/bin/python -m pytest tests/ -q   # 单元测试
```

### 切实盘(真金白银,务必细读)

1. 在**参数设置 → 钱包私钥**粘贴私钥:本地校验推导地址后写入本机 `.env`,免重启生效;同页设置**资金地址**与**签名类型**(0=EOA 直签,1=邮箱 Magic,2=网页代理钱包)。
2. 确认账户在 Polygon 上有 **USDC.e** 余额与交易所授权;EOA 账户另备少量 **POL** 作自动赎回 gas。
3. 打开**实盘开关**。建议先小额试运行,对比实盘成交与模拟盘的差距后再加仓。

### 项目结构

```
app/
├── main.py       FastAPI 应用 · REST API · 管理台静态托管
├── engine.py     15 秒多策略引擎(仓位状态机、双层风控)
├── strategy.py   6 个策略 + 双语元数据
├── executor.py   模拟撮合 / 实盘 py-clob-client 下单
├── redeem.py     链上自动赎回(CTF redeemPositions)
├── mystic.py     内置万年历推演 + 命盘生成(娱乐)
├── markets.py    盘口发现与结算                ├── btc.py     BTC 秒级行情
├── clawby.py     Clawby 数据通道客户端(限速)  ├── db.py      SQLite 存储
└── admin.html    旧版单页管理台(/admin-lite)
frontend/         React 18 + Ant Design 5 + @ant-design/plots(Vite 构建)
└── src/pages/    仪表盘 · 策略中心 · 神秘的东方力量 · 当前持仓 · 盘口记录 · 订单流水 · 参数设置
backtest/         数据拉取 · 模拟器 · 调参器 · 报告(REPORT/OPT15/PREBET/COVER)
tests/            单元测试
```

### 风险提示

5 分钟二元盘波动极快且接近有效定价;本仓库回测采用偏乐观的成交假设,模拟盘实测才是裁判。**本软件不构成任何投资建议,盈亏自负。**
