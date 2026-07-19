# PAPER_ONLY 迁移说明

## 当前研究分支安全边界

`paper-only-hardening` 是不可配置的模拟盘、回测和策略研究版本。`app/config.py` 直接定义 `PAPER_ONLY = True`，没有关闭它的正常运行方式。`executor.mode()` 无条件返回 `paper`。

允许：

- `CLAWBY_API_KEY` 和明确只读的公开市场数据凭据；
- 公共行情、盘口与订单簿读取；
- 本地模拟挂单、止盈、成交判断、持仓、撤单和盈亏记账；
- 回测、策略研究、模拟参数调整、CSV 导出。

禁止：

- 钱包私钥、funder、signature type、CLOB key/secret/passphrase 和任何签名/转资凭据；
- 钱包地址交易派生、CLOB 凭据创建、真实订单提交/查询/撤销；
- Web3 账户、链上签名、Polygon 交易与赎回；
- LIVE 与自动赎回开关。

已删除 API：

- `GET /api/private-key`
- `POST /api/private-key`
- `POST /api/private-key/context`
- 任何 funder、signature type、LIVE、自动赎回或交易凭据替代路由

通用 `POST /api/settings` 只接受研究字段白名单，敏感和未知字段返回 400。

## 禁用函数

- `executor._get_client()` 固定抛出 `Live trading is disabled in this PAPER_ONLY research build.`
- `redeem.run_once()` 固定抛出 `On-chain redemption is disabled in this PAPER_ONLY research build.`
- `executor.cancel_all()` 没有客户端或远端副作用，engine 不再调用它。
- executor 不包含 CLOB client、credential derivation、sign/post/get/cancel 调用。

## 模拟订单与撤单

- 入场订单：`paper:<slug>:<side>:<local nonce>`。
- 模拟止盈：`paper-tp:<slug>:<strategy>:<local nonce>`。
- 仍记录到本地 SQLite，成交判断仍使用只读订单簿 ask。
- `cancel_order` 仅接受 `paper:` 和 `paper-tp:`；其他 ID 返回 false，并输出不含 ID 的安全警告。
- 本地撤单写入 `kind=cancel` 的 paper 订单流水。

## 旧数据库处理

DB 初始化时直接删除旧 settings 中的 `live_enabled`、`auto_redeem` 和交易凭据类键，并直接删除 meta 中的 `clob_creds`、`api_secret`、`api_passphrase`。代码不读取、回显或记录这些值；后续 get 返回缺省，set 拒绝写入。API 与 CSV 只读取 paper mode。

## 验证不能实盘

1. 运行 `python -m pytest tests/ -q`，确认 53 项全部通过。
2. 搜索 executor，确认无 CLOB 初始化和真实 order 调用。
3. 设置任一项目已知交易凭据环境变量，lifespan 在 DB/后台任务前拒绝启动。
4. 请求敏感路由，确认 404；向 settings 发送敏感字段，确认 400。
5. 启动日志必须显示 `PAPER_ONLY | localhost only | no wallet | no live trading`。
6. 模拟冒烟中确认订单前缀、非 paper ID 拒绝、`py_clob_client` 未加载。

## Git 历史声明

原始只读基线提交 `6ad8e25b0be00cfda79c57a52e191d4e5e83b8ab` 继续作为当前分支祖先保留。没有重写、删除、reset 或变基原始历史；没有修改、合并或推送 `main`。当前研究分支不支持任何真实资金交易。
