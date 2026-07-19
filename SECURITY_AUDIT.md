# PAPER_ONLY 安全审计

审计日期：2026-07-19。对照基线：`6ad8e25b0be00cfda79c57a52e191d4e5e83b8ab`。

| 风险编号 | 等级 | 原文件/函数 | 原风险 | 修改方式 | 验证测试 | 状态 | 剩余风险 |
|---|---|---|---|---|---|---|---|
| SA-001 | 高 | `app/engine.py:loop`、`app/executor.py:cancel_all` | engine 启动即可能构造交易客户端并执行真实全撤，未要求 DB LIVE 开关 | 删除 engine 启动全撤；`cancel_all` 仅为无远端副作用的 paper no-op | `test_cancel_all_has_no_client_path`；源代码搜索 | 已修复 | 本地 paper 全撤目前只返回 0，不做批量状态变更 |
| SA-002 | 严重 | `app/executor.py:_get_client/place_limit/place_tp/order_filled/cancel_order` | 可创建/派生 CLOB 凭据、签单、提交订单、查询和撤销真实订单 | executor 重写为纯模拟；`_get_client` 固定抛错；移除 `py-clob-client` 依赖 | `_get_client`、下单、止盈、撤单与 source tests | 已修复 | 公共订单簿读取仍由 Clawby relay 提供，属于只读数据面 |
| SA-003 | 严重 | `app/main.py:api_private_key_*` | 无认证读写私钥、funder、签名类型并写 `.env` | 路由及 `_persist_env` 完全删除，不接受请求体 | 7 条敏感路径 404 测试与真实启动检查 | 已修复 | 无 |
| SA-004 | 严重 | `app/redeem.py`、`engine.loop` | 可初始化 Web3 账户、签名并发送 Polygon `redeemPositions` | redeem 改为不可绕过抛错边界；删除 engine 调用；移除 `web3` 依赖 | `test_redeem_always_fails_closed`、源搜索 | 已修复 | 文件保留仅为兼容导入，任何调用都失败 |
| SA-005 | 严重 | `executor._get_client`、SQLite `meta.clob_creds` | CLOB key/secret/passphrase 明文存 SQLite | 不再创建/读取；DB init 直接 DELETE 旧键；get/set meta 对敏感键 fail closed | legacy DB migration test | 已修复 | 已有数据库物理页可能需另行安全销毁/压缩；本阶段不读取或显示其值 |
| SA-006 | 高 | `app/config.py` | 运行时读取钱包/交易环境变量 | `PAPER_ONLY=True` 硬编码；启动只检查项目已知交易凭据，存在即统一报错；只允许 Clawby 数据 key | 凭据参数化测试、lifespan 测试、Clawby allow test | 已修复 | 新增交易凭据变量时必须同步拒绝列表 |
| SA-007 | 严重 | `POST /api/settings` | 通用接口可写 LIVE、自动赎回或未知字段，范围验证弱 | 明确字段白名单、结构/类型/范围验证；所有敏感/未知字段 400 | 9 个敏感/未知字段测试、范围测试 | 已修复 | 本地用户仍可改模拟资金和策略研究参数，这是设计允许行为 |
| SA-008 | 高 | FastAPI 部署边界 | 无 Trusted Host、Origin/CSRF 或 loopback 写请求保护 | TrustedHost 仅允许 localhost/test；写请求要求本地 Origin 或本地 client；文档固定 `127.0.0.1` | bad Host 400、bad Origin 403、真实监听验证 | 已修复 | 无用户账户系统；同机恶意进程仍可访问本地服务 |
| SA-009 | 高 | React Settings、App、filters、admin-lite | 暴露私钥、funder、签名、LIVE、赎回入口和误导文案 | 删除控件/API 调用/模式筛选/文案；增加显著 PAPER ONLY 声明 | frontend source test、Vite build | 已修复 | 浏览器缓存旧 bundle 时需硬刷新 |
| SA-010 | 中 | 读取与 CSV API | 可能返回/导出旧数据库真实模式历史 | API 强制 `mode=paper`，拒绝其他 mode；state 仅取 paper 订单/仓位 | API 代码审计与 settings/route tests | 已修复 | 旧数据库内容仍可能物理存在，但研究 API 不读取/导出该模式 |
| SA-011 | 中 | npm 开发依赖 | Vite/esbuild 存在 1 high、1 moderate 审计项 | 仅报告；不使用公开 Vite dev server；未做破坏性主版本升级 | `npm audit`、`npm ls` | 待后续 | 详见 `DEPENDENCY_AUDIT.md` |

## 安全不变量

- `PAPER_ONLY` 不从环境、数据库、API 或前端读取。
- executor 中不存在交易客户端初始化、真实签单、提交、查询或撤单调用。
- engine 启动、循环和关闭均没有远端撤单或链上赎回调用。
- 只有 `paper:` 与 `paper-tp:` 订单 ID 可进入本地撤单逻辑。
- CLAWBY_API_KEY 只用于只读 relay；无该 key 也允许受限启动。

## 剩余整体风险

管理台没有云端账户系统，安全模型是单机 loopback。可信 Host 与写 Origin 防护显著降低误暴露和浏览器跨站写风险，但无法阻止已经控制本机用户会话的恶意进程。市场数据仍依赖外部 relay 的正确性与可用性；模拟成交模型不等同真实成交表现。开发期不得向 LAN/公网暴露 Vite dev server。
