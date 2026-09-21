# 01 · 从零安装与第一次运行

目标：先在你的电脑上跑出一份真正的接口测试报告，再运行 Web。这个阶段不用手机，也不用公司账号。

## 1. 认识三个工具

| 工具 | 可以这样理解 | 安装位置 |
| --- | --- | --- |
| Python | 解释并运行 `.py` 文件的程序 | 系统安装，或由 uv 管理 |
| uv | 安装依赖、管理项目虚拟环境的工具 | 系统命令 |
| VS Code | 阅读、修改、调试代码的编辑器 | 可选，但适合新手 |

虚拟环境 `.venv` 是这个项目独有的一套 Python 包。项目 A 用某个版本、项目 B 用另一个版本时，二者不会互相覆盖。不要将 `.venv` 复制到另一台电脑；在那里重新执行 `uv sync --frozen`。

## 2. Windows 安装

1. 从 [Python 官网](https://www.python.org/downloads/) 安装 Python 3.11，安装时选中添加 Python 到 PATH。若公司统一提供 Python，优先使用公司版本和安装源。
2. 从 [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/) 安装 uv。已经有 Python 时可运行下方命令。
3. 重新打开 PowerShell，再检查版本。

```powershell
# py 是 Windows 的 Python 启动器；这里明确选择 Python 3.11。
py -3.11 --version
py -3.11 -m pip install --user uv
uv --version
```

如果提示找不到 `uv`，先重开终端。仍找不到时可使用 `py -3.11 -m uv --version`，把后续命令开头的 `uv` 替换成 `py -3.11 -m uv`。这是 PATH 配置问题，不是框架代码问题。

## 3. 安装项目依赖

在包含 `pyproject.toml` 的目录运行命令；不要在 `tests/` 子目录运行。

```powershell
# frozen：严格按 uv.lock 安装，避免换一台电脑就安装到不同版本。
uv sync --frozen

# 查看实际使用的 Python，正常应落在当前项目的 .venv 中。
uv run python -c "import sys; print(sys.executable)"

# 先运行不需要浏览器、手机和模型服务的接口示例。
uv run python -m autotest run --suite api
```

首次命令会下载依赖、创建 `.venv` 并安装当前 `autotest` 包。演示服务会自动启动在 `127.0.0.1` 的空闲端口，测试结束后关闭。自动测试无需另开终端启动 `demo`。

预期结果：终端出现用例数量、`passed` 以及报告路径。出现失败时，先看错误最下面一段，再看 [排错手册](07-ci-troubleshooting.md)。不要通过删除断言让结果变绿。

## 4. 安装浏览器并运行 Web

```powershell
# Python 的 Playwright 包与浏览器程序是两样东西，浏览器需要单独安装。
uv run python -m playwright install chromium

# 默认无头模式：不打开可见窗口，速度较快。
uv run python -m autotest run --suite web

# 调试时打开可见窗口。
uv run python -m autotest run --suite web -- --headed
```

Playwright 升级后要重新安装对应浏览器。公司的下载代理、证书或防火墙限制，需要按公司网络规范配置，具体提示见 [Playwright 浏览器管理](https://playwright.dev/python/docs/browsers)。

### AI 操作页面需要 Node.js

正式 Python Web 回归不要求 Node.js。只有让 AI 使用项目 Playwright CLI 探索页面时才需要
Node.js 20+ 和 npm/npx。安装公司允许的 Node.js 后检查：

```powershell
node --version
npm --version
npx --version

# 框架固定 CLI 版本，不要求 npm 全局安装。
uv run qa browser --session check -- --version
```

项目默认使用本机 Chrome。没有 Chrome 或需要开源 Chromium 时，先安装 CLI 对应浏览器，
随后在 `open` 命令增加 `--browser=chromium`：

```powershell
uv run qa browser --session check install-browser chromium
uv run qa browser --session item-flow open https://test.example.com --browser=chromium
```

CLI 与 Python Playwright 可能需要不同浏览器版本，不能以 Python Chromium 已安装推断 CLI
浏览器也可用。更多命令和工具选择见 [浏览器工具接入](11-tool-integration.md)。

## 5. macOS / Linux

安装 Python 3.11 与 uv 后，其余 `uv run ...` 命令相同。Linux 上通常还需要浏览器的系统依赖：

```bash
uv sync --frozen
uv run python -m playwright install --with-deps chromium
uv run python -m autotest run --suite all
```

`--with-deps` 可能需要系统管理员权限安装 Linux 软件包。已在公司镜像中准备好系统依赖时，仅执行 `playwright install chromium`。

## 6. 想不用 uv 怎么办

推荐保留 uv 工作流以复用锁文件。如果受公司工具限制，也可以使用 pip：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m autotest run --suite api
```

这里安装了运行测试需要的包。`dev` dependency group 中的 Ruff 开发工具需要按公司工具规范另装。pip 安装不会自动严格使用 `uv.lock`，要遵守团队自己的版本固定规范。macOS / Linux 的解释器路径为 `.venv/bin/python`。

无需执行 `Activate.ps1`。直接调用 `.venv` 中的 Python 或使用 `uv run`，可以避开 PowerShell 脚本执行策略问题。

## 7. 如何看报告

统一命令 `python -m autotest run` 为每次执行创建单独的 `artifacts/` 子目录。名称使用 UTC 时间加随机后缀，和你本地显示时间可能有时区差异。请以终端打印的实际路径为准：

- HTML：用浏览器打开，查看通过 / 失败 / 跳过数量和失败堆栈。
- JUnit XML：供 CI 统计结果，通常不需要手工阅读。
- Allure results：原始结果文件，**不是能直接双击的 Allure 网页**。
- Web 失败附件：截图、视频、Trace 等，具体是否生成取决于失败发生阶段。

```text
artifacts/<UTC时间-随机后缀>/
├── report.html             # 可直接打开的测试报告
├── junit.xml               # CI 汇总文件
├── run.json                # 本次命令、套件、退出码
├── allure-results/         # Allure 原始结果
├── web/                    # Playwright 按用例保存失败 Trace / 视频 / 截图
└── failures/<用例标识>/     # 仅失败时创建
    ├── call.json           # 正文失败；前置/后置失败为 setup.json / teardown.json
    ├── web.png             # 可取得页面时的截图
    ├── app.png             # 可取得 App 会话时的截图
    └── app.xml             # App 页面结构
```

`call.json` 包含用例、环境、错误和附件位置，可作为 AI 失败分析的文本输入。详见 [AI 手册](05-ai.md)。各附件是否存在取决于本次测试类型和实际失败阶段。

如果失败发生在启动浏览器之前，没有页面可截图是正常情况。Trace 可用 Playwright 本地查看器打开：

```powershell
# 将路径改成本次报告目录下实际找到的 trace.zip。
uv run python -m playwright show-trace "artifacts/本次运行目录/实际附件目录/trace.zip"
```

如需 Allure 的趋势和分类视图，另装 [Allure 命令行工具](https://allurereport.org/docs/install/)，再针对本次 `allure-results` 路径执行 `allure serve "实际路径"`。HTML 报告不依赖安装这个工具。

## 8. 编辑器第一次配置

用 VS Code 打开整个仓库文件夹。安装仓库推荐的 Python、Pylance、Ruff 扩展；运行命令面板的 **Python: Select Interpreter**，选择当前项目 `.venv`。

仓库 `.vscode/settings.json` 已启用 pytest。测试面板能收集到 `tests/` 后，先运行一个接口用例。IDE 直接运行 pytest 时不会自动使用 CLI 的每次报告参数；需要完整附件和报告时使用统一 `run` 命令。

下一步：[读懂架构与目录](02-architecture.md)。
