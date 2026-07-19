# PAPER_ONLY 改造变更日志

## 2026-07-19

### 后端边界

- 新增不可配置 `PAPER_ONLY = True` 与固定 localhost host。
- 启动拒绝项目已知交易凭据；允许 CLAWBY_API_KEY。
- executor 重写为纯模拟下单、止盈、成交判断和本地撤单。
- 删除 CLOB client、凭据派生、真实订单提交/查询/撤销代码。
- 删除 engine 启动全撤与自动赎回调用。
- redeem 改为固定 fail-closed 兼容边界。
- 删除私钥、funder、signature type API 和 `.env` 写入逻辑。
- settings 改为白名单及类型/范围验证。
- 旧 DB 敏感 settings/meta 键安全删除并阻止后续读写。
- 读 API/CSV/state 只返回 paper mode 数据。
- 加入 Trusted Host、本地 write Origin/client 保护和 PAPER_ONLY 启动日志。

### 前端与文档

- 删除 React 与 legacy admin 的私钥、账户、签名、LIVE、自动赎回入口。
- 删除真实模式筛选和误导文案。
- 增加“模拟研究模式 / PAPER ONLY”及无钱包/无真实资金声明。
- README 改为研究版安装、安全边界与本机启动说明。

### 依赖

- 从 requirements 删除仅用于实盘的 `py-clob-client` 与 `web3`。
- 未修改 npm 依赖版本或 package lock；仅生成漏洞审计报告。

### 测试与报告

- 将原赎回测试改为研究版 fail-closed 断言，其余原有策略测试不变。
- 新增 31 项 paper-only 安全测试；最终 40 项全部通过。
- 新增安全审计、迁移、依赖、测试和变更报告。

### Git

- 所有工作只在 `paper-only-hardening`。
- 基线提交 `6ad8e25b0be00cfda79c57a52e191d4e5e83b8ab` 与原始历史保留。
- 未切换、修改、合并或推送 main。
- 未修改 `app/strategy.py`、backtest 算法或任何策略默认参数。
