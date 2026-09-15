# 07 · CI、失败排查与学习路线

## 1. CI 是什么

CI（持续集成）就是“每次提交后，让一台固定机器按相同步骤安装、检查、运行测试、保存报告”。本地用例通过后，CI 可以持续发现后续改动造成的回归。

仓库提供 GitHub Actions 与 Jenkins 配置。它们是已写好的接入文件，需要你推送到自己的仓库 / 配置执行节点后首次验证；本地测试通过不能证明远程 CI 已经通过。

## 2. GitHub Actions

文件：`.github/workflows/tests.yml`。使用 GitHub.com 的 Ubuntu 托管节点：

1. 检出当前代码。
2. 准备 uv 与 Python 3.11。
3. 用 `uv sync --frozen` 安装锁定依赖。
4. 安装 Chromium 及 Linux 系统依赖。
5. 执行 Ruff 检查。
6. 执行本地 demo 的 unit、api、web 与默认跳过的 app 测试。
7. 无论成功失败，尝试上传 `artifacts/`，保留 7 天。

在仓库 **Actions** 页面选择工作流，进入某次运行后下载 Artifacts。解压后打开 HTML；Trace 用 `playwright show-trace` 查看。

工作流不需要公司账号和 AI Key。迁移为公司测试环境时，将参数改为对应环境，把变量通过 GitHub Actions Secrets 注入；不要将私网凭证交给来自不受信任分支的执行。公司内网可能需要专用 runner。

示例采用官方当时可用的 Action 版本，并固定提交 SHA。以后升级时核对其官方发布说明与自建 runner 要求。GitHub Enterprise Server 的产物上传版本兼容性与 GitHub.com 不同，应遵照组织平台版本适配：[checkout](https://github.com/actions/checkout)、[setup-uv](https://github.com/astral-sh/setup-uv)、[upload-artifact](https://github.com/actions/upload-artifact)。

## 3. Jenkins

文件：`Jenkinsfile`。示例面向标签为 `linux` 的 Linux agent，需要 Jenkins Pipeline 与 JUnit 支持。创建 Pipeline from SCM，指向仓库中的 `Jenkinsfile`。

执行节点需预先具备：

- Git、Python 3.11、uv，并让运行 Jenkins 的账户能在 PATH 找到它们。
- Chromium 所需 Linux 系统库。管理员可在构建镜像中提前运行 Playwright 的依赖安装。
- 访问依赖源的网络、足够磁盘空间与工作目录写权限。

流水线只下载当前版本浏览器，避免在每次 Jenkins 构建中依赖交互式 sudo。需要代理 / 内部源时由团队配置到节点。每次构建先清空该工作区的 `artifacts/`，避免上次报告混入本次统计；已归档历史报告仍由 Jenkins 保留。`junit` 汇总测试趋势，`archiveArtifacts` 保留整份报告和附件。

接入 App 后另设有设备的节点：Android 节点准备 SDK / 模拟器 / USB；iOS 节点是 macOS 并准备 Xcode 和签名。先按 [App 手册](04-app.md) 跑通一条，再把同样命令搬进流水线。

## 4. 按顺序分析一次失败

先保留当前报告，再按以下顺序判断，不要立刻加重试：

1. **用例收集是否成功？** ImportError、配置键拼错、未注册 marker 属于执行前问题。
2. **连接是否成功？** 服务地址、网络、浏览器安装、Appium 和设备连接。
3. **准备数据是否成功？** 登录失败、权限变更、固定数据被别的用例删除。
4. **操作是否完成？** 定位错了、遮罩挡住、页面未进入预期状态。
5. **真实结果是否符合需求？** 核对接口契约、产品规则和发布变更。

记录用例 node id、代码版本、环境、发生时间、实际与预期，附上对应失败证据。提交缺陷前，用单条复跑判断是否稳定复现。

```powershell
# -x 遇到首个失败就停止；-vv 展示更详细的名称。
uv run python -m autotest run --suite api -- -x -vv

# 调试 Web 时显示浏览器，仅运行匹配场景。
uv run python -m autotest run --suite web -- --headed -k login -x

# 只读诊断依赖和工具，不会替你安装或修改设备。
uv run python -m autotest doctor
```

## 5. 常见问题速查

| 现象 | 常见原因 | 第一步 |
| --- | --- | --- |
| `uv` 找不到 | 终端未更新 PATH | 重开终端，或用 `py -3.11 -m uv` |
| `No module named autotest` | 不在项目环境，或没有安装当前包 | 回到根目录执行 `uv sync --frozen`，用 `uv run` |
| Playwright `Executable doesn't exist` | 未安装对应版本浏览器 | 执行 `uv run python -m playwright install chromium` |
| Linux 浏览器缺库 | 系统依赖不齐 | 在允许的节点安装 `playwright install --with-deps chromium` |
| `Connection refused` | 地址 / 端口错，服务未启动 | 核对环境；demo 测试会自动启动服务 |
| demo 却请求公司 URL | `.env` 或系统变量覆盖 | 检查 `API_BASE_URL`、`WEB_BASE_URL`、`TEST_ENV` |
| 配置校验失败 | 拼错键、URL 缺协议、超时不合法 | 对照 `Settings` 与 YAML 示例修改 |
| 401 / 403 | Token 过期或权限不匹配 | 按当前账号权限重新获取测试身份 |
| `TimeoutError` 定位失败 | 定位变化、iframe、页面状态不对 | 先看截图和 Trace，核对实际 DOM |
| `strict mode violation` | 同一 Locator 匹配多个元素 | 加稳定范围 / 条件，确认业务目标唯一 |
| App 用例 `skipped` | 未显式启用 | 完成设备配置，再按 App 手册显式运行 |
| 换环境后演示业务全 `skipped` | 演示业务只适用于 demo | 新增不带 demo 标记的公司用例 |
| Allure results 无法双击 | 原始结果不是网页 | 装 Allure CLI 后 serve，或直接看 HTML 报告 |
| 加 `-n 2` 才失败 | 账号 / 数据 / 设备共享 | 暂时串行，再按 worker 做资源隔离 |
| CI 没有报告附件 | 安装 / 检查阶段就失败 | 先看流水线中第一个失败步骤 |
| AI 生成代码不能运行 | 草稿缺少真实接口 / 定位信息 | 补上下文，审查导入、fixture、断言，再单条运行 |

HTTPX 客户端默认 `trust_env=False`，因此不会自动继承系统 HTTP 代理；公司接口必须经过代理或私有 CA 时，在 `ApiClient` 中按公司规范显式配置 transport / proxy / SSL context 并加相应验证。不要用关闭 TLS 校验当作长期解决办法。

`doctor` 主要检查基础 Python 依赖和可选工具位置。基础依赖齐全时它可能返回成功，同时提示 Chromium 未安装或 App 工具缺失；它不代表浏览器已能启动、设备已连接或公司业务已连通。

## 6. Web 失败附件怎么读

先看截图，确认停留的页面是否正确；再打开 Trace，看每次操作的时间、定位器、页面快照与网络请求。视频适合观察跳转或遮罩出现的时序。

```powershell
# 先列出附件，找到本次失败的 Trace。
Get-ChildItem artifacts -Recurse -Filter trace.zip

# 用实际文件路径替换示例。
uv run python -m playwright show-trace "artifacts/本次运行/附件目录/trace.zip"
```

截图、Trace 和报告可能包含被测业务数据。按公司访问权限保存和分享；向 AI 发送时使用 [AI 手册](05-ai.md) 中明确选择输入、预览和审查的流程。文本脱敏不能保证截图中所有敏感信息被遮盖。

### 用一次故意失败练习排查

```powershell
uv run python -m autotest run --suite web -- examples/failure_demo.py -k expected_web_failure
```

这条命令只执行教学用的错误断言，**预期 1 failed、退出码 1**。终端会显示独立报告目录；
打开 HTML，再检查 `failures/` 中的 `call.json`、`web.png`，以及 `web/` 中的
`trace.zip`、截图和 `.webm` 视频。可把这份 `call.json` 显式交给离线 AI 分析入口。
该文件不在默认 `tests/` 集合中，日常 `run --suite all` 不会执行它。

## 7. 依赖更新与质量检查

```powershell
# 日常检查。
uv run ruff check .
uv run ruff format --check .

# 需要统一格式时执行，之后查看 Git diff。
uv run ruff format .

# 有计划地更新依赖，再运行相应测试并审查 uv.lock 的改动。
uv lock --upgrade
uv sync --frozen
uv run python -m playwright install chromium
uv run python -m autotest run --suite all
```

不要在每次 CI 构建中自动更新所有依赖。先在单独改动里升级、验证，再提交新的 `uv.lock`。框架变化优先跑 `tests/unit/`，接口 / 页面改动跑对应业务测试。

## 8. 30 天上手路线

| 时间 | 实践任务 | 自检标准 |
| --- | --- | --- |
| 第 1–3 天 | 安装、跑 API / Web、打开报告，读一个简单测试 | 能解释输入、操作、断言与失败原因 |
| 第 4–7 天 | 学 Python 函数、字典、列表、导入、异常；新增参数化登录场景 | 能独立改三组输入和预期 |
| 第 8–10 天 | 写创建 / 查询 / 删除接口流程，补结构和业务断言 | 单条连续执行三次无残留影响 |
| 第 11–14 天 | 学 fixture、yield 清理、环境覆盖、Service 分层 | 改接口路径只改服务层 |
| 第 15–18 天 | 学 Playwright Locator、expect、POM 与 iframe | 改按钮定位只改页面对象 |
| 第 19–22 天 | 跑 Android；有 Mac 节点后跑 iOS | 能区分 skipped、驱动失败和业务失败 |
| 第 23–25 天 | 接入 CI，练习看 HTML、JUnit、Trace | 同事可下载报告并复现失败 |
| 第 26–28 天 | 让 AI 生成一个草稿、分析一个已知失败 | 能审查并说明 AI 哪些建议有证据 |
| 第 29–30 天 | 迁移一条公司真实业务链路，邀请同事照文档复现 | 别人无需口头补充就能跑通 |

把每次遇到的问题、原因和正确处理方式补进团队文档。稳定的一条业务链路，比许多没有断言或无法复现的脚本更有用。
