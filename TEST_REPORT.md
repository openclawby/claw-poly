# PAPER_ONLY 验证报告

执行日期：2026-07-19。

## pytest

- 基线：9 passed，1 warning。
- 新增安全测试：42。
- 最终：51 total / 51 passed / 0 failed / 0 skipped / 2 warnings。
- 全新隔离环境用时：2.39 秒。

```text
...................................................                      [100%]
51 passed, 2 warnings in 2.39s
```

警告：FastAPI TestClient 的 Starlette/httpx 弃用提示；原测试 `asyncio.get_event_loop()` 弃用提示。两者均不是测试失败。

覆盖：固定 paper mode、凭据启动拒绝、Clawby allow、无 Clawby 受限启动、CLOB client fail closed、模拟下单/止盈/撤单、非模拟 ID 拒绝、redeem fail closed、敏感路由 404、settings 敏感字段/类型/范围、整数参数小数拒绝、极大整数溢出与非有限数值拒绝、Host/Origin、旧 DB 清理、前端敏感控件和源代码执行调用缺失。

在全新 Python 3.12.13 虚拟环境中，仅执行 `pip install -r requirements-dev.txt` 后完成上述测试。环境中的 pytest 为 9.1.1；`pip check` 报告无依赖冲突；`py-clob-client` 与 `web3` 均未安装。

测试没有连接真实 Polymarket 交易端点，没有使用真实凭据。

## 前端

项目没有独立前端测试脚本。生产构建：

```text
vite v5.4.21 building for production...
✓ 4844 modules transformed.
dist/index.html                    0.43 kB │ gzip:   0.30 kB
dist/assets/index-okd9YD7f.js  2,773.38 kB │ gzip: 847.25 kB
✓ built in 35.65s
```

## 本地启动与 HTTP

- 仅监听 `127.0.0.1:8643`。
- `/health` 200：`mode=paper`、`paper_only=true`。
- `/admin` 200。
- 小数整数参数 `params.cover=1.9` 返回 400。
- 启动日志：`PAPER_ONLY research build | localhost only | no wallet | no live trading`。
- 后台 engine 启动，没有 ClobClient 初始化、远端撤单或赎回。
- 停止后 `PORT_8643_LISTENING_AFTER_STOP=False`。

敏感路由实际验证：

```text
POST /api/private-key          404
POST /api/private-key/context  404
POST /api/funder               404
POST /api/signature-type       404
POST /api/live                 404
POST /api/auto-redeem          404
GET  /api/private-key          404
POST /api/settings {live_enabled} 400
POST /api/settings {params: {cover: 1.9}} 400
```

## 模拟订单冒烟

```text
mode=paper
entry prefix=paper:
take-profit prefix=paper-tp:
entry cancellation=True
take-profit cancellation=True
non-paper rejected=True
executor has client state=False
py_clob_client loaded=False
```

服务启动、HTTP 检查、模拟冒烟和进程停止均未输入或使用真实凭据。
