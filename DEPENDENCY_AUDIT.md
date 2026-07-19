# 依赖安全审计

审计日期：2026-07-19。没有执行 `npm audit fix --force`、主版本升级或批量依赖升级。

## npm audit

命令：`npm 11.7.0 audit --json`。

结果：2 个漏洞聚合项（1 high、1 moderate；0 critical）。依赖树：

```text
polymarketbot-ui
├─ @vitejs/plugin-react@4.7.0
│  └─ vite@5.4.21 (deduped)
└─ vite@5.4.21
   └─ esbuild@0.21.5
```

| 包 | 直接性 | 等级 | 公告/影响 | 当前影响范围 | 建议 |
|---|---|---|---|---|---|
| `vite@5.4.21` | 直接 devDependency | high（聚合） | GHSA-4w7w-66w2-5vf9：optimized deps sourcemap path traversal；GHSA-v6wh-96g9-6wx3：Windows UNC/NTLMv2 hash disclosure；GHSA-fx2h-pf6j-xcff：Windows alternate-path `server.fs.deny` bypass（CVSS 7.5） | 主要影响 Vite 开发服务器；生产构建由 FastAPI 静态提供，不运行 Vite dev server | 禁止向 LAN/公网开放 dev server；后续在独立分支验证升级到审计建议的 patched Vite major |
| `esbuild@0.21.5` | 经 Vite 传递 | moderate | GHSA-67mh-4wv8-2f99：任意网站可能向开发服务器发请求并读取响应（CWE-346） | 仅开发服务器场景；当前生产静态 bundle 不启动 esbuild server | 随 Vite 升级解决；升级前只在 loopback 开发 |

`npm audit` 给出的自动修复为 `vite@8.1.5`，标记 `isSemVerMajor=true`。本阶段按要求不执行；应另行做兼容性、构建和浏览器回归验证后再升级。

## Python audit

使用系统临时隔离 venv 安装 `pip-audit 2.10.1`，执行：

```text
python -m pip_audit -r requirements.txt --progress-spinner off
No known vulnerabilities found
```

当前 requirements：FastAPI、Uvicorn、HTTPX、websockets、zhdate；没有已知漏洞命中。`py-clob-client` 与 `web3` 已从研究版 requirements 删除，因为实盘签名和链上能力已移除。基线 `.venv` 可能仍物理保留旧包，重新创建 `.venv` 后不会安装它们。

## 限制

Python requirements 使用最低版本约束而非完整 lock，审计时解析结果会随包索引变化。建议后续生成可审查的 hash lock，并在 CI 中固定运行 `pip-audit` 与 `npm audit`；这属于后续依赖治理，本阶段未改策略或做大规模升级。
