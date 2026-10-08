# 16 · 新公司三端接入改造与验证

日期：2026-10-08。目标是让未知技术栈的新项目可以独立配置 API、Web、Android/iOS，
复用执行、日志、报告与 AI 编写流程。真实业务契约和定位由新公司资料决定。

## 已交付

- `qa project init --name company-qa --output ../company-qa`：从完整源码生成独立公司项目。
  复制核心源码、锁文件、框架单测、参考材料与 CI 模板，生成自己的 README 和三端业务样板。
  默认环境 `company_test`；拒绝覆盖已有目录。过滤 `.env`、会话/密钥目录、证书私钥、缓存、报告和安装包。
- `qa project check --env company_test --suite api|web|app|all`：按端离线检查地址、角色、
  CA/代理、Web 登录态与 App capabilities；拒绝示例域名，App 需要明确设备选择。
- `API_CA_BUNDLE`、`API_TRUST_ENV`、`WEB_STORAGE_STATE`：配置企业 CA、显式环境代理与 Web 登录态。
  TLS 仍启用；Web 的证书信任由浏览器/系统负责。
- 修复只跑 API 也要求 Web 地址的问题；真正的 Web 用例缺地址时仍明确失败，允许项目自定义 base_url。
- `all` 分别要求 API/Web 实际执行；显式 `--run-app` 时也要求 App 实际执行。
  控制台和 console.log 同步基础脱敏，不让一端通过掩盖另一端全跳过。
- GitHub Actions/Jenkins 公司模板：按端预检后执行、App 串行、设备节点/锁与 Secret 接入示例、失败归档。

## 本地验证结果

环境为 Windows、Python 3.11.6，依赖来自 `uv sync --frozen`。

| 检查 | 结果 |
| --- | --- |
| Ruff check / format --check | 通过 |
| `qa run --suite all -- --env demo -n 2` | **350 passed，1 skipped** |
| 其中框架单测 | 325 passed |
| 其中本地 API 演示 | 20 passed |
| 其中 Chromium Web 演示 | 5 passed |
| App 演示 | 1 skipped：未提供真实设备和应用 |
| 导出项目全新虚拟环境 `uv sync --frozen` | 通过，不依赖原虚拟环境 |
| 导出项目框架单测 | 325 passed |
| 导出公司 API 样板接本地测试服务 | 实际 GET 和字段断言通过；改错预期后返回失败 |
| 导出公司 Web 样板接本地测试服务 | Chromium 导出已登录状态，复用该状态进入受保护页面并验证标题，通过 |
| 未填配置与门禁 | 占位域名/未填业务参数失败；全跳过或单端缺失不会误判通过 |

上述公司样板使用 `company_test` 配置指向本地测试服务，证明接入路径可运行，
不代表新公司的业务已通过。控制台中的 App skip 不能作为设备验证证据。

## 接入后仍需验收

公司真实 API/Web、鉴权协议、VPN/代理/证书环境、数据清理策略；Android/iOS 的应用、
设备、签名、定位；公司 GitHub/Jenkins 节点与 Secret；在线 AI 服务。
本轮没有连接公司环境、真实手机、远端 Jenkins 或在线 AI。
公司的 CI 模板已做本地命令与结构验证，最终验收需要在相应节点实际执行。
