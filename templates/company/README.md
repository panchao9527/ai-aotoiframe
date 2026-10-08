# __PROJECT_NAME__ · 公司自动化测试项目

本项目由 ai-aotoiframe 生成，包含独立源码、依赖锁文件、API / Web / Android / iOS 入口、
报告与框架单测。默认环境为 `company_test`。每个端有一条需要填写真实预期的冒烟样板，
不包含原仓库的 demo 业务用例；`--env demo` 只用于框架自测。

## 1. 安装

准备 Python 3.11 和 uv，进入本目录执行（Windows PowerShell / macOS / Linux 通用）：

```text
uv sync --frozen
uv run --frozen python -m playwright install chromium
uv run --frozen qa doctor
```

Linux Web 节点首次安装可用 `python -m playwright install --with-deps chromium` 准备系统库。
Appium 服务与驱动由设备节点单独准备。iOS 的设备执行服务需要 macOS、Xcode 和 WDA；
Windows 可以远程连接该服务。详见 [App 接入](docs/04-app.md)。

## 2. 填写三类配置

| 文件 | 需要填写 |
| --- | --- |
| `configs/environments/company_test.yaml` | API/Web 测试地址、Appium 地址、设备配置路径 |
| `.env`（复制 `.env.example`） | 账号、Token、设备 ID、安装包路径；禁止提交 Git |
| `configs/business/smoke.yaml` | 只读 API 路径和预期字段；Web 标题；App 首屏标识和文本 |

Windows：`Copy-Item .env.example .env`；macOS/Linux：`cp .env.example .env`。
已有 `.env` 时直接编辑。变量优先级为：CLI 环境名 > TEST_ENV；系统变量 > .env > YAML。
新增环境时复制 YAML 并用 `--env 环境名` 指定，所有路径相对本项目根目录。

API 样板使用 `role_clients()`，角色在 `configs/auth/company.yaml`。
初始 `mode: none` 适用于公开只读接口；需要 Bearer 时改成 `mode: bearer`、
`token_env: API_TOKEN`。只填 `.env` 的 Token 不会改变 `none` 角色。
JSON 登录可按该文件注释改成 `mode: login`，填写真实登录路径、账号字段与 Token 字段。
Cookie、SSO、OAuth、签名协议在项目 fixture 中适配，不假定公司的登录协议。

内部 CA 设置 `API_CA_BUNDLE=.secrets/company-ca.pem`，框架会保留默认可信根并追加 CA。
公司网络需要代理时显式设 `API_TRUST_ENV=true`，再配置 `HTTPS_PROXY` / `NO_PROXY`。
默认不读取系统代理；显式 CA 配置优先于 HTTPX 的环境证书设置。
Web 的证书信任需在浏览器/系统中配置，API CA 不会改变浏览器信任。

Web 可设置 `WEB_STORAGE_STATE=.auth/operator.json`。通过已登录的 Playwright context
调用 `context.storage_state(path=".auth/operator.json")` 导出（先创建 `.auth` 目录），
或使用自己的登录 fixture。每个测试仍创建独立浏览器 context；文件过期需要重新登录。
测试登录流程本身时，在专属 fixture 中覆盖 `storage_state`，使用空 cookies/origins。

App 的 Android/iOS YAML 位于 `configs/devices/`，按注释填写 `.env` 变量。
安装包路径由 **Appium 服务所在机器**解释。一个设备一次只运行一个会话。

## 3. 按端检查和执行

先完成对应端的配置；不要求第一天同时准备好手机与所有环境。

```text
uv run --frozen qa project check --env company_test --suite api
uv run --frozen qa run --suite api -- --env company_test

uv run --frozen qa project check --env company_test --suite web
uv run --frozen qa run --suite web -- --env company_test --browser chromium

uv run --frozen qa project check --env company_test --suite app --app-platform android --app-caps configs/devices/android.yaml
uv run --frozen qa run --suite app -- --env company_test --run-app --app-platform android --app-caps configs/devices/android.yaml -n 0

uv run --frozen qa project check --env company_test --suite app --app-platform ios --app-caps configs/devices/ios.yaml
uv run --frozen qa run --suite app -- --env company_test --run-app --app-platform ios --app-caps configs/devices/ios.yaml -n 0
```

`project check` 只检查配置，不发送业务请求、不连接设备，也不验证账号有效期。
`smoke.yaml` 留空会使样板明确失败；完成配置后还需要真实运行确认业务预期。
`run --suite all` 要求 API 和 Web 都实际执行，带 `--run-app` 后也要求 App 实际执行；
Android 和 iOS 仍需分两次验收。全跳过不算通过。仅调试单条用例时可直接用
`uv run --frozen python -m pytest tests/api/test_company_smoke.py -q --env company_test`。

报告输出到本次 `artifacts/时间戳/`，包含 HTML、JUnit、Allure、日志和失败证据。
框架单测单独执行：`uv run --frozen qa run --suite unit -- --env demo`。

## 4. 添加公司业务

API 的 Service 在 `src/autotest/api/company_service.py`；Web 的 Page 在
`src/autotest/web/company_page.py`；App 的 Screen 在 `src/autotest/mobile/company_screen.py`。
测试放 `tests/api/`、`tests/web/`、`tests/app/`，业务断言留在测试中。
新增业务使用专属模块和 fixture，创建的数据及时通过 `data_factory` 登记清理。
样板只覆盖首条只读/首屏检查，订单等流程应按真实需求增加断言和清理步骤。

[AI 编写流程](docs/09-authoring-workflows.md)可继续使用；草稿验证后再入库。
复制的 `examples/` 是框架单测与学习材料，不在公司默认测试集合中。
源码和文档均已复制，不依赖原电脑路径或原仓库虚拟环境。
`docs/` 保留完整框架参考，其中 demo 演示和原仓库 CI 步骤用于学习；
公司业务安装与执行以本 README 为准，CI 使用下面的公司模板。

## 5. 接入 CI

先本地跑通，再按 [公司 CI 说明](templates/company-ci/README.md) 选择 GitHub Actions
或 Jenkins 模板。模板默认手动选择单端运行，预检失败停止，设备串行执行，失败仍归档报告。
公司地址、Secret、执行节点和设备资源需要由团队配置；模板不代表远端 CI 已验收。

迁移验收以真实结果为准：三端分别通过、Android/iOS 分别验证、故意改错断言能失败、
同一业务连续运行三次不污染数据，最后让一位同事按本文从头安装并执行。
