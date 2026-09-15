# Python 全栈自动化测试框架

用一套 Python 项目管理 **接口、Web、Android 和 iOS 自动化测试**。适合先从本地示例学会，再迁移到公司的真实业务。每个目录都有明确职责，核心代码和示例用中文注释解释。

## 你会得到什么

| 能力 | 技术 | 在本项目中的用途 |
| --- | --- | --- |
| 统一执行、参数化、前后置 | pytest | 所有测试共用一个入口和 fixture 体系 |
| 接口测试 | HTTPX + JSON Schema | 请求、鉴权、业务断言、结构校验 |
| Web 测试 | Playwright + pytest-playwright | 页面对象、自动等待、iframe、失败截图和 Trace |
| App 测试 | Appium Python Client | Android / UiAutomator2、iOS / XCUITest 接入 |
| 数据和环境 | YAML + 环境变量 | 本地练习与公司环境分离 |
| 报告 | pytest-html + JUnit XML + Allure results | 人看结果、CI 汇总、后续生成 Allure 页面 |
| 并行 | pytest-xdist | 按需增加进程，本地示例数据隔离 |
| AI 入口 | 离线提示词 + 可配置模型接口 | 生成用例草稿、辅助分析失败，人工审查后执行 |
| 工程质量 | uv + Ruff + CI | 锁定依赖、代码检查、自动运行和保存报告 |

**交付边界：** 仓库包含可在本机运行的接口 / Web 演示系统和测试；App 提供真实驱动接入、页面对象与示例，运行需要设备 / 模拟器和被测应用。iOS 执行节点需要 macOS 与 Xcode。AI 在线调用需要你配置模型服务。GitHub Actions / Jenkins 配置需要放到你的 CI 环境首次执行验证。

## 先跑通：Windows PowerShell

在项目根目录打开终端，先确认电脑有 Python 3.11 和 uv。安装步骤见 [从零安装](docs/01-getting-started.md)。

```powershell
# 1. 按锁文件安装依赖，自动创建 .venv 虚拟环境。
uv sync --frozen

# 2. 先跑接口；默认自动启动本地演示服务，不用准备公司接口。
uv run python -m autotest run --suite api

# 3. 为 Web 测试安装 Chromium 浏览器，只需在首次安装或升级后执行。
uv run python -m playwright install chromium

# 4. 跑 Web，最后执行全部示例。
uv run python -m autotest run --suite web
uv run python -m autotest run --suite all
```

依赖和浏览器首次安装需要网络；安装完成后默认 `demo` 接口 / Web 示例使用本机服务。执行结束后，终端会打印本次 `artifacts/` 报告目录。App 未启用时显示 `skipped`，表示没有执行，不能算作 App 验证通过。带 `demo` 标记的演示业务在其他环境自动跳过；公司用例需要你按真实业务新增。

> `uv run` 的作用是使用这个项目的 Python 虚拟环境执行命令，无需先激活 `.venv`。切换项目后不会混用另一家公司的依赖。

## 常用命令

```powershell
# 查看环境诊断与帮助。
uv run python -m autotest doctor
uv run python -m autotest --help

# 打开浏览器看测试过程。
uv run python -m autotest run --suite web -- --headed --browser chromium

# 使用两个进程运行（真实项目先确保账号和测试数据相互独立）。
uv run python -m autotest run --suite all -- -n 2

# 仅收集测试名称，不执行。
uv run python -m pytest --collect-only -q

# 生成需要补全的接口用例模板，未实现的模板会明确失败。
uv run python -m autotest new --kind api --name order --output tests/api/test_order.py

# 手工体验演示页面；浏览器打开 http://127.0.0.1:8765。
uv run python -m autotest demo --port 8765
```

演示账号：`demo`，密码：`demo123`。`demo` 是练习服务，数据保存在内存，重启后消失。

## 按这个顺序学习

1. [从零安装与第一次运行](docs/01-getting-started.md)：Python、uv、Windows / macOS / Linux、报告。
2. [读懂架构与目录](docs/02-architecture.md)：fixture、配置、分层、数据隔离。
3. [从复制第一个用例到独立编写](docs/03-writing-tests.md)：AAA、参数化、接口断言、POM、iframe。
4. [Android 和 iOS 接入](docs/04-app.md)：设备、驱动、应用配置、常见连接问题。
5. [AI 生成与失败分析](docs/05-ai.md)：离线入口、在线配置、审查与复跑。
6. [迁移到新公司 / 新项目](docs/06-new-project.md)：环境、账号、业务层、迁移验收表。
7. [CI 与排错手册](docs/07-ci-troubleshooting.md)：GitHub Actions、Jenkins、Trace、30 天学习路线。
8. [本次交付验证记录](docs/08-validation.md)：已运行的 122 条测试、失败附件检查和待接入范围。

## 维护约定

- 测试文件回答“要验证什么”；页面对象封装“点哪里”；接口服务层封装“怎样调用业务接口”。
- 用例自行准备并清理数据。不要依赖其他用例先登录、先下单或按固定顺序运行。
- 优先使用稳定的 label / role / test id / accessibility id；不要用固定睡眠处理页面加载。
- `.env`、真实账号、令牌不提交到 Git；示例 YAML 只放普通配置。
- AI 的结果先作为草稿审查；定位器变化与真实产品缺陷需要区分，修改后重新运行验证。
- 使用 `uv lock` 更新锁文件，审查依赖变更后再提交；CI 使用 `uv sync --frozen` 复现它。

## 官方参考

[pytest](https://docs.pytest.org/en/stable/) · [Playwright Python](https://playwright.dev/python/docs/intro) · [HTTPX](https://www.python-httpx.org/) · [Appium](https://appium.io/docs/en/latest/) · [uv](https://docs.astral.sh/uv/) · [Allure pytest](https://allurereport.org/docs/pytest/)
