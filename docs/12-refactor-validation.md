# 12 · AI 编写工作流重构验证记录

验证日期：2026-09-16。发布仓库：`panchao9527/ai-aotoiframe`。
原始执行框架来自 `panchao9527/autoiframe`。
重构基线：`70f7f7c98d054df046ffce93f434e4b71b6c453f`。
工作分支：`codex/ai-authoring-workflows`。

本次在原有 HTTPX / Playwright / Appium + pytest 执行层之上增加材料整理、
多文件草稿、隔离验证、入库和失败反馈。原有 `ai generate/analyze` 入口继续保留。
本记录区分框架测试、本地演示业务和需要用户提供环境才能执行的业务验收。

## 1. 交付内容

| 入口 | 已实现行为 |
|---|---|
| `author prepare` | 整理需求、选定源码、OpenAPI、录制及观察记录；附带已有对象和 fixture 签名，生成脱敏上下文及模板提示词 |
| `author generate` | 导入编程助手的标准 JSON 回复，或显式 `--send` 调用模型；生成 API 服务、Page / Screen 对象、fixture 与测试等多文件草稿 |
| `author validate` | 默认静态检查；显式指定环境后复制项目到临时目录执行草稿，记录结果、证据与内容指纹 |
| `author promote` | 仅接收已经审查且当前内容执行通过的新增文件；草稿或项目依赖变化后需重新验证，不覆盖已有文件 |
| `record web` | 调用 Playwright Codegen 录制 Python pytest 脚本，再转换为项目 POM 用例 |
| `record app` | 提供 Appium Inspector 录制接入说明；已有录制/观察记录可送入 App 模板 |
| `evidence` | 汇总失败信息、浏览器事件与附件路径，交给 AI 分析入口或编程助手诊断 |
| pytest 执行统计 | 区分 API、Web、App、框架单测；要求业务执行时，全跳过不会显示为验收通过 |

编写模板在 `templates/authoring/`，四个项目 Skill 在 `.agents/skills/`。
MCP 配置为项目内示例，不修改用户全局工具配置。

## 2. 最终回归结果

执行命令：

```powershell
uv sync --frozen
uv run --frozen python -m autotest run --suite all -- --env demo -n 2
```

本次运行使用本机 demo 服务，未使用外部业务地址、业务 Token 或公司固定数据。

| 范围 | 通过 | 失败/错误 | 跳过 | 说明 |
|---|---:|---:|---:|---|
| 框架单测 | 132 | 0 | 0 | 包含草稿、脱敏、入库门槛、执行统计和模型协议 mock 验证 |
| API 演示业务 | 11 | 0 | 0 | 本地服务、动态数据与清理 |
| Web 演示业务 | 5 | 0 | 0 | 真实 Chromium，包含 iframe 和草稿生成到独立 POM 执行 |
| App | 0 | 0 | 1 | 未提供应用与设备，明确未执行 |
| 合计 | **148** | **0** | **1** | 149 条收集结果，退出码 0 |

首次重构结果目录：`artifacts/20260916-053514-6639e4/`。
GitHub 发布前复查再次运行相同集合，结果仍为 **148 passed, 1 skipped**，退出码 0；
本机复查结果目录：`artifacts/20260916-093624-2befd4/`。
`run.json` 记录完整执行命令与退出码；`execution.json` 记录分组执行数；
`junit.xml` 记录 149 条结果，`report.html` 为可阅读报告。
运行产物被 Git 忽略，不作为仓库源码提交。

关键验证包括：

- 草稿通过前，正式测试目录没有候选文件；隔离环境能导入新生成的 API / POM 代码。
- 通过后修改草稿、源码、fixture 或配置，旧验证记录不能用于入库；恢复完全相同内容后才可复用。
- 语法错误、路径越界、Windows 保留名称、目标已存在、未确认业务条件均被阻止。
- 无断言、常量断言、显式跳过、固定睡眠和空异常处理被静态规则识别；规则是辅助检查，不等价于业务审查。
- 运行时失败、全部跳过、部分跳过，均不能成为草稿完整验收通过的证据。
- 单测通过但目标业务全部跳过时，业务执行门槛返回非零退出码。
- OpenAPI 按操作筛选后保留契约引用；敏感字段定义保留，示例值与敏感默认值脱敏；认证下载不跟随重定向。
- 多文件模型输出经过完整协议及路径检查后才写入；在线模型响应由 mock 验证协议，未实际发送外部模型请求。

## 3. 失败维护链路

另外执行了一条故意失败的教学用例，用来验证失败信息确实能够回流：

```powershell
uv run --frozen python -m pytest examples/failure_demo.py --env demo --artifact-dir artifacts/refactor-failure --output artifacts/refactor-failure/web --tracing retain-on-failure --screenshot only-on-failure --video retain-on-failure -q
uv run qa evidence --run-dir artifacts/refactor-failure --output artifacts/ai/refactor-triage.json
uv run qa ai analyze --input artifacts/ai/refactor-triage.json --output artifacts/ai/refactor-triage-prompt.md
```

第一条命令预期退出码为 1，实际符合；它不属于上面的日常通过集合。
已检查失败 JSON、浏览器网络事件摘要、PNG 截图、可读的 Trace ZIP 及 WebM 视频存在。
证据汇总和离线诊断提示词成功生成。汇总文件只引用二进制附件路径，不自动上传这些附件。

## 4. 工具和静态检查

- `ruff check .`、`ruff format --check .`、`git diff --check` 通过。
- 四个项目 Skill 均通过 `skill-creator` 提供的 `quick_validate.py`。
- Playwright Python 1.63.0，pytest 9.1.1，Python 3.11.16。
- MCP 示例固定使用 `@playwright/mcp@0.0.81` 和 `chrome-devtools-mcp@1.9.0`。
  已通过 npm 查询版本并运行各自 `--help` 核对配置参数；这仅验证包与参数，
  不代表已经在用户浏览器或真实业务上跑过 MCP 全流程。
- Playwright 录制命令构造已检查；Web 集成测试使用维护的录制协议样例，
  不将它声称为本次人工操作录制的结果。
- 发布前复查了新模块、入库门槛及 CI 配置；三个 GitHub Actions 的固定 SHA
  均与官方对应版本标签一致。完整历史共检查 103 个文本/文件 blob，
  未发现所扫描的常见密钥格式，也没有 `.env`、运行产物或虚拟环境文件入库。
  该检查覆盖明确模式，不等价于对任意敏感内容的保证。

## 5. 接入真实项目时仍需验证

1. 提供对应版本的需求、前后端代码与原始 OpenAPI JSON/YAML 地址，确认接口契约冲突及业务预期。
2. 配置测试环境、隔离账号及可清理数据，运行生成的业务测试；本地 demo 通过不能替代公司业务验收。
3. Web 在实际页面上核对定位器和登录态；Playwright MCP 用于探索/操作，Chrome DevTools MCP 用于诊断与取证。
4. App 需要实际安装包、设备、Appium 驱动、定位器与业务账号；本次没有 Android/iOS 真机或模拟器执行证据。
5. 在线模型、真实私有 Swagger 下载、用户 MCP 会话、Jenkins 和公司环境 CI 尚未验证。

现有用例维护使用 Git diff 和目标回归；`promote` 仅负责新增文件，不自动覆盖人工维护代码。
项目没有实现“失败后自动放宽断言”或无需业务证据的自动修复。

## 6. GitHub 发布后验证

2026-09-16，向 `panchao9527/ai-aotoiframe` 的 `main` 分支推送提交
`3a27c63909dfcdc138f0208bb668e99210497ded` 后，仓库自带 GitHub Actions 已完成：

- Ubuntu 24.04 上锁定依赖安装、Chromium 及系统库安装成功。
- Ruff 检查和格式检查通过。
- 框架、API 和真实浏览器测试为 **148 passed, 1 skipped**；跳过项仍为未配置设备的 App。
- 报告和失败证据上传步骤成功。

对应的 [GitHub Actions 运行记录](https://github.com/panchao9527/ai-aotoiframe/actions/runs/35080647087)
可按提交核对。本节之后的文档补记不改变该次测试所验证的代码。

使用步骤见 [AI 编写工作流](09-authoring-workflows.md)、
[App 编写接入](10-mobile-authoring.md) 和 [工具接入与失败维护](11-tool-integration.md)。
