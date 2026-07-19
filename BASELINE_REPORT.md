# claw-poly 第一阶段只读基线报告

## 1. 仓库与执行信息

- 执行时间：2026-07-19 15:54:58 +02:00（Europe/Belgrade）
- 项目路径：`F:\claw-poly-research\claw-poly`
- 远程仓库：`https://github.com/openclawby/claw-poly.git`
- 默认分支：`main`（`refs/remotes/origin/HEAD -> refs/remotes/origin/main`）
- 当前分支：`paper-only-hardening`（从 `main` 创建）
- 当前提交：`6ad8e25b0be00cfda79c57a52e191d4e5e83b8ab`
- 未创建 Git 提交。仓库实际只有 3 条提交，无法列出 5 条：

```text
6ad8e25b0be00cfda79c57a52e191d4e5e83b8ab | 2026-07-19T07:20:59+08:00 | Panda | MIT License
658978e1671a68951d05c93a6895487d3f87174c | 2026-07-19T07:18:40+08:00 | Panda | initial
fee4d79a692609e9fee10851bbf2ddca77c42ef2 | 2026-07-19T07:06:11+08:00 | Panda | Initial commit
```

```text
origin  https://github.com/openclawby/claw-poly.git (fetch)
origin  https://github.com/openclawby/claw-poly.git (push)
```

## 2. 安全边界与凭据声明

- 启动前确认 `CLAWBY_API_KEY`、`PM_PRIVATE_KEY`、`PM_FUNDER`、`PM_SIGNATURE_TYPE`、`LIVE`、`LIVE_ENABLED`、CLOB secret/passphrase 环境变量均不存在。
- 项目根目录不存在 `.env`。
- 未输入、请求、保存、显示或使用任何真实交易凭据、钱包私钥、助记词、CLOB secret/passphrase、真实账户地址或真实余额。
- 未连接真实钱包，未开启 LIVE，未创建真实订单，未执行链上赎回，未更改真实账户授权。
- 启动使用临时 SQLite 数据库；默认 `live_enabled=0`，状态为 `paper`。

## 3. 环境基线

| 项目 | 结果 | README 要求/判断 |
|---|---|---|
| 操作系统 | Windows 10.0.19045（build 19045.6466） | 未指定 |
| Shell | PowerShell Core 7.6.3 | 满足 |
| Python | 3.12.13（Codex 隔离运行时） | 3.10+，满足 |
| venv pip | 25.0.1 | 未升级 |
| Node.js | 24.14.0（Codex 隔离运行时） | 18+，满足 |
| npm | 11.7.0 | 满足 |
| Git | 2.45.1.windows.1 | 满足 |
| F: 可用空间 | 92.27 GiB | 足够 |
| 是否为 Git 仓库 | 是 | `.git` 存在 |

系统 PATH 中的 Windows Store Python 别名不可执行，Node/npm 也不在 PATH，因此使用隔离运行时创建项目 `.venv` 并运行 npm，未修改项目依赖声明。

## 4. 原始目录结构

```text
claw-poly/
├── .env.example
├── .gitattributes
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
├── app/
│   ├── __init__.py  admin.html  btc.py  clawby.py  config.py  db.py
│   └── engine.py  executor.py  main.py  markets.py  mystic.py  redeem.py  strategy.py
├── backtest/
│   ├── *.py（data/sim/report/optimize/accuracy 等）
│   ├── *.md（REPORT/OPT15/PREBET/COVER/ACCURACY）
│   └── *.json（参数、picks、accuracy）
├── docs/screenshots/
├── frontend/
│   ├── index.html  package.json  package-lock.json  vite.config.js
│   └── src/（App、i18n、util、pages）
└── tests/test_core.py
```

没有 `.github/workflows` 或其他 GitHub 工作流文件。配置/依赖文件为 `.env.example`、`.gitattributes`、`.gitignore`、`requirements.txt`、`frontend/package.json`、`frontend/package-lock.json`、`frontend/vite.config.js`。

## 5. Python 依赖安装

命令为创建 `.venv` 后执行 `.venv\Scripts\python.exe -m pip install -r requirements.txt`。第一次因沙箱网络限制失败，获联网许可后以相同命令成功，耗时约 84 秒。未修改 requirements、未升级依赖或 pip；无冲突/废弃警告，仅有 pip 新版提示。

`pip freeze`：

```text
aiohappyeyeballs==2.7.1
aiohttp==3.14.1
aiosignal==1.4.0
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.14.2
attrs==26.1.0
bitarray==3.9.1
certifi==2026.6.17
charset-normalizer==3.4.9
ckzg==2.1.8
click==8.4.2
colorama==0.4.6
cytoolz==1.1.0
eth-account==0.13.7
eth-hash==0.8.0
eth-keyfile==0.8.1
eth-keys==0.7.0
eth-rlp==2.2.0
eth-typing==6.0.0
eth-utils==6.0.0
eth_abi==5.2.0
fastapi==0.139.2
frozenlist==1.8.0
h11==0.16.0
h2==4.3.0
hexbytes==1.3.1
hpack==4.2.0
httpcore==1.0.9
httpx==0.28.1
hyperframe==6.1.0
idna==3.18
iniconfig==2.3.0
multidict==6.7.1
packaging==26.2
parsimonious==0.10.0
pluggy==1.6.0
poly_eip712_structs==0.0.1
propcache==0.5.2
py_builder_signing_sdk==0.0.2
py_clob_client==0.34.6
py_order_utils==0.3.2
pycryptodome==3.23.0
pydantic==2.13.4
pydantic_core==2.46.4
Pygments==2.20.0
pytest==9.1.1
python-dotenv==1.2.2
pyunormalize==17.0.0
pywin32==312
regex==2026.7.19
requests==2.34.2
rlp==4.1.0
starlette==1.3.1
toolz==1.1.0
types-requests==2.33.0.20260712
typing-inspection==0.4.2
typing_extensions==4.16.0
urllib3==2.7.0
uvicorn==0.51.0
web3==7.16.0
websockets==15.0.1
yarl==1.24.2
zhdate==0.1
```

## 6. 前端安装与构建

- `package-lock.json` lockfileVersion 3；npm 11.7.0 执行 `npm ci`。
- 安装成功：added 218 packages，audited 219 packages，约 2 分钟。
- 8 packages seeking funding；2 vulnerabilities（1 moderate、1 high）。未执行 `npm audit fix`。
- `package.json` 和 `package-lock.json` 均未变化。
- 第一次临时 npm runner 因子进程找不到 Node 而退出；补充当前进程 PATH 后成功，未改项目文件。

构建命令 `npm run build`，结果：

```text
vite v5.4.21 building for production...
✓ 4844 modules transformed.
dist/index.html                    0.43 kB │ gzip:   0.30 kB
dist/assets/index-ChOBhSmR.js  2,783.82 kB │ gzip: 851.26 kB
✓ built in 1m
```

构建成功，无 TypeScript/JavaScript 错误；产物为被忽略的 `frontend/dist/`。

## 7. pytest 完整结果

命令：`.venv\Scripts\python.exe -m pytest tests\ -q -ra`

```text
.........                                                                [100%]
============================== warnings summary ===============================
tests/test_core.py::test_paper_order_arith
  F:\claw-poly-research\claw-poly\tests\test_core.py:67: DeprecationWarning: There is no current event loop
    oid, price, shares = asyncio.get_event_loop().run_until_complete(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
9 passed, 1 warning in 0.81s
```

总数 9；通过 9；失败 0；跳过 0；警告 1；无失败堆栈。

## 8. 本地模拟启动

使用临时 `DB_PATH`，等价命令：`.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8643`。

| 检查 | 结果 |
|---|---|
| 监听 | 仅 `127.0.0.1:8643` |
| `/` | 307 到 `/admin`，跟随后 200 |
| `/admin` | 200，React 管理台 |
| `/health` | 200，`ok=true`、`mode=paper` |
| `/api/state` | 200，`live_enabled=0` |
| `/api/private-key` | 200，`configured=false`，无地址 |
| `/api/rounds?limit=1` | 200，空列表 |
| 后台循环 | BTC WebSocket 与 engine loop 均启动 |
| ClobClient | 未初始化；engine 调用 `cancel_all()`，因无私钥立即返回 |
| 实盘行为 | 无订单、撤单或赎回 |
| 停止 | 已主动停止；8643 无 LISTEN 残留，仅 TIME_WAIT |

日志摘要：

```text
INFO engine: engine started (tick 15s, multi-strategy)
INFO: Application startup complete.
INFO: Uvicorn running on http://127.0.0.1:8643
WARNING btc: btc backfill failed (will warm up live): All connection attempts failed
WARNING clawby: relay polymarket_events ... All connection attempts failed
```

缺少 `CLAWBY_API_KEY` 时服务仍启动，但 relay、行情、盘口发现、订单簿和完整策略循环不可用；应用带空 `X-API-Key` 重试。本阶段未索取密钥、未绕过认证。网络错误也受执行环境网络限制影响。

## 9. 实盘、私钥、CLOB 与 `.env` 位置

| 位置 | 函数/类与用途 | 资金接触 | 风险 |
|---|---|---|---|
| `app/config.py:4-18` | 读取 Clawby key、私钥、funder、签名类型、RPC；定义 CLOB host | 是 | 高 |
| `app/config.py:23-46` | `DEFAULT_SETTINGS`：live 默认关、auto-redeem 默认开 | 门禁 | 中 |
| `app/db.py:53-101` | `init`：SQLite settings/meta，可存 live/CLOB creds | 是 | 高 |
| `app/db.py:104-144` | `get_settings`/`save_settings` | 是 | 高 |
| `app/main.py:122-138` | `_persist_env` 明文写项目 `.env` | 是 | 严重 |
| `app/main.py:141-153` | 无认证 `api_private_key_status` | 信息暴露 | 高 |
| `app/main.py:156-191` | 无认证 `api_private_key_set`，写/清私钥、清 CLOB creds | 是 | 严重 |
| `app/main.py:194-217` | 无认证 `api_private_key_context`，写 funder/signature | 是 | 严重 |
| `app/main.py:413-464` | 无认证 `api_settings`，可切 LIVE/改参数 | 是 | 严重 |
| `app/executor.py:20-24` | `mode`：live 需 DB 开关 + 私钥 | 门禁 | 高 |
| `app/executor.py:27-59` | `_get_client`：懒建 `ClobClient`，创建/派生 API creds；key/secret/passphrase 明文 JSON 存 SQLite `clob_creds` | 是 | 严重 |
| `app/executor.py:62-92` | `place_limit`：真实 BUY `create_order`/`post_order` | 是 | 严重 |
| `app/executor.py:95-125` | `place_tp`：真实 SELL 止盈 | 是 | 严重 |
| `app/executor.py:128-148` | `order_filled` 查询订单 | 只读账户 | 中 |
| `app/executor.py:151-170` | `cancel_all`/`cancel_order` | 是 | 高 |
| `app/engine.py:195-204` | `loop` 启动即 `cancel_all()`，不检查 DB live | 是 | 高 |
| `app/engine.py:240-270` | 市场状态机；live + auto-redeem 时赎回 | 是 | 严重 |
| `app/redeem.py:43-88` | `_get_w3`/`_redeem_tx` 签名发送 `redeemPositions` | 是 | 严重 |
| `app/redeem.py:91-117` | `run_once` 仅检查私钥 + EOA 类型，自身不检查 DB live | 是 | 高 |
| `frontend/src/pages/Settings.jsx:15-134` | 私钥框、funder、signature type、保存/清除 | 是 | 严重 |
| `frontend/src/pages/Settings.jsx:166-284` | LIVE、auto-redeem 开关 | 是 | 严重 |
| `app/admin.html:30-68` | legacy admin 的 LIVE 控件 | 是 | 高 |
| `.env.example:1-17` | 凭据变量占位说明，无真实值 | 潜在 | 中 |
| `README.md:27-75,120-168` | `.env`、私钥、LIVE、赎回文档 | 文档 | 低 |
| `backtest/data.py:28` | 读取只读 Clawby key | 否 | 低 |

没有发现 `subprocess`、`os.system`、Python `eval`/`exec`、`0.0.0.0`、`CORSMiddleware` 或 `allow_origins`。测试与前端 i18n/util 中的其余命中仅用于 paper/redeem 门禁测试和界面标签。

## 10. 管理后台暴露面

- 私钥输入：`frontend/src/pages/Settings.jsx:65-73`。
- funder 地址：`Settings.jsx:90-94`；signature type：`Settings.jsx:102-112`。
- LIVE：`Settings.jsx:274-283`；自动赎回：`Settings.jsx:268-273`。
- 读/写私钥 API：`GET/POST /api/private-key`；funder/signature：`POST /api/private-key/context`。
- `.env` 写入：`main._persist_env()`；CLOB 凭据派生：`executor._get_client()`。
- 真实下单/撤单/赎回由后台 engine 调用；没有直接 HTTP 下单、撤单或赎回路由。
- README 要求 localhost，但应用无强制监听、Host 校验或 loopback 客户端校验，实际绑定取决于 uvicorn 参数。
- 身份认证：无。`ADMIN_PASSWORD` 仅在 `config.py:12` 定义，未使用。
- Host 校验：无；CSRF/Origin 校验：无；CORS middleware：无。浏览器默认同源限制不等于认证或 CSRF 防护。

无认证写路由：

| 路由 | 位置 | 影响 | 风险 |
|---|---|---|---|
| `POST /api/private-key` | `main.py:156` | 写/清私钥与 `.env` | 严重 |
| `POST /api/private-key/context` | `main.py:194` | 写 funder/signature | 严重 |
| `POST /api/settings` | `main.py:413` | 策略、金额、风险、赎回、LIVE | 严重 |
| `POST /api/mystic/start` | `main.py:306` | 创建计划并启用策略 | 高 |
| `POST /api/mystic/stop` | `main.py:351` | 停止策略 | 中 |

无认证读路由：`/health`、`/api/rounds`、`/api/orders`、`/api/export`、`/api/equity`、`/api/stats`、`/api/private-key`、`/api/strategies`、`/api/positions/open`、`/api/mystic`、`/api/backtest`、`/api/state`。其中订单、持仓、策略、业绩、私钥状态及 funder/signature 信息敏感。

## 11. 初步风险与下一阶段建议

1. **严重**：无认证私钥、funder、LIVE、策略写接口；若被错误暴露可控制实盘面。
2. **严重**：私钥明文写 `.env`，CLOB key/secret/passphrase 明文写 SQLite。
3. **高**：engine 读取 live setting 前无条件调用 `cancel_all()`；环境中只要有私钥，paper DB 也可能撤真实挂单。
4. **高**：无认证、Host allowlist、CSRF/Origin 校验；`ADMIN_PASSWORD` 未使用。
5. **高**：npm 报 1 high、1 moderate 漏洞，本阶段未修复。
6. **高**：`redeem.run_once()` 自身不检查 DB live，只有 engine 调用点检查。
7. **中**：缺少 Clawby key 仍持续重试；requirements 仅下限约束也削弱可复现性。

建议下一阶段：隔离 paper/live 进程；所有执行层实施 fail-closed 多重门禁；移除启动全撤副作用；为所有 API 增加强认证、Host/loopback 限制、CSRF/Origin 校验；移除 HTTP 私钥输入和秘密明文持久化，改用 OS 密钥库/外部签名器；分离读写 API；对 LIVE/撤单/赎回二次确认并审计；缺 Clawby key 时明确进入受限模式；独立评估 npm 漏洞与依赖锁定；补充“paper 启动不得初始化 CLOB/撤单/赎回”安全测试。

## 12. 工作区状态与最终声明

安装/测试/构建生成且被 `.gitignore` 排除：

```text
.venv/
frontend/node_modules/
frontend/dist/
.pytest_cache/
app/__pycache__/
tests/__pycache__/
```

启动数据库与日志位于系统临时目录；仓库内没有生成 `.env`、数据库或日志。最终预期：

```text
git status --short
?? BASELINE_REPORT.md
```

**本阶段未修改任何项目代码、配置逻辑、策略参数、依赖版本、`requirements.txt`、`package.json` 或 `package-lock.json`；唯一未跟踪项目文件为 `BASELINE_REPORT.md`。**

**本阶段未发现、输入、请求、保存、显示或使用任何真实交易凭据；未发生任何真实交易、撤单、赎回、授权或资金操作。**
