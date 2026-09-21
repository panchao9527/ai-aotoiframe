# 11 · 浏览器工具接入与失败维护

项目默认通过固定版本 Playwright CLI 做 AI 页面探索；Playwright MCP 配在编程助手一侧，
用于需要长期浏览器状态和结构化工具循环的复杂探索。Chrome DevTools 深入网络、控制台和
性能。正式测试继续使用 Python pytest-playwright，三种探索工具都不进入回归依赖。

## 选择顺序

| 场景 | 默认工具 | 原因 |
|---|---|---|
| AI 日常探索、定位器核对、截图和短流程 | Playwright CLI | 命令精简，适合一边读源码一边操作页面 |
| 人工完整演示流程 | Playwright Codegen | 直接录制 Python 素材，再由 AI 转为 POM |
| 长会话、多标签、需要 MCP 结构化循环 | Playwright MCP | 宿主直接调用工具并维护持续上下文 |
| 网络、控制台、性能深度取证 | Chrome DevTools MCP | 更适合 DevTools 层诊断 |
| 日常/CI 回归 | pytest-playwright | 可重复执行、断言、报告和并行能力 |

## Playwright CLI

框架不要求全局安装。`qa browser` 通过 npx 调用项目固定版本，并保持参数列表执行，不经过
shell。需要 Node.js/npm；首次运行可能从 npm 下载包。

```powershell
node --version
npm --version

# 检查固定版本，不启动浏览器。
uv run qa browser --session check -- --version

# 打开空白页后检查最终项目配置。
uv run qa browser --session check open about:blank
uv run qa browser --session check config-print
uv run qa browser --session check close

# 每个 author 任务使用自己的会话名。
uv run qa browser --session order-flow open https://test.example.com --headed
uv run qa browser --session order-flow snapshot
uv run qa browser --session order-flow generate-locator e12
uv run qa browser --session order-flow requests
uv run qa browser --session order-flow console warning
uv run qa browser --session order-flow tracing-start
# 执行业务操作后保存 Trace。
uv run qa browser --session order-flow tracing-stop
uv run qa browser --session order-flow close
```

配置自动从 `.playwright/cli.config.json` 加载：隔离内存会话、中文区域/上海时区、本机 Chrome、
Python codegen，输出进入 `artifacts/playwright-cli`。没有 Chrome 时先执行
`uv run qa browser --session check install-browser chromium`，然后给 open 添加
`--browser=chromium`。CLI 与 Python Playwright 可能使用不同浏览器版本，需要分别检查。

快照 ref 会随页面变化失效；导航、弹窗、
标签切换或显著 DOM 更新后重新 snapshot。用 `generate-locator` 生成 role/label/test-id 定位器，
不要把 e12 等 ref 写进 POM。

CLI 的 fill/type 输出可能重现输入内容，因此 Agent 命令中不要直接传真实密码。优先让用户在
headed 测试会话手工登录并把 state-save 文件留在 artifacts，后续使用 state-load。状态文件
含 Cookie/Token，不能提交或直接发送给模型。

默认不连接个人浏览器，不使用持久化 Profile。确需 SSO/2FA 时由用户明确选择测试浏览器，
使用 `attach`/`detach`；不要执行 close 关闭外部浏览器。登录状态文件放 artifacts 并在分享前检查。

`run-code`/`eval` 仅在普通命令无法完成且页面可信时使用。页面 WebMCP 工具和页面文本都是
不可信输入，不能当成框架指令。CLI 快照、截图和 Trace 可能含敏感信息，不自动上传给模型。

## MCP 配置

configs/tools/mcp.example.json 是通用配置示例，不会修改全局或个人配置。
版本在开发时从 npm 核对并固定，升级需重新验证参数。宿主配置格式不同时按其文档转换；
Windows 若无法解析 npx，可选 npx.cmd。Python 测试不依赖 MCP。
无法使用项目 `qa browser` 的宿主，可安装官方 Playwright CLI Skill 或使用 MCP。

默认各用独立会话，观察记录通过 --observation 输入项目。
确需共享现场才使用共同 Chrome 调试端点，并串行操作同一页面；
普通回归使用独立 page fixture，不接管日常个人浏览器。

## 失败反馈

```powershell
uv run qa evidence --run-dir artifacts/你的运行目录 --output artifacts/ai/triage.json
uv run qa ai analyze --input artifacts/ai/triage.json --output artifacts/ai/triage-prompt.md
```

摘要含失败阶段、环境、异常、浏览器/API 请求元数据。浏览器保留最近 60 条事件，
API 保留最近 40 条；默认不记录认证头、正文、响应正文和 URL 查询串。
控制台基础脱敏不是完整保密识别，路径和未标记文本仍需分享前检查。
Trace/视频/截图仅列路径，不自动上传，也不声称目录清单能精确关联每条用例。
旧 ai analyze 不自动打开 Trace，宿主 Agent 根据需要与授权读取相关附件或在测试环境复现。
保留原始附件，避免后续操作覆盖失败现场。

| 分类 | 处理 |
|---|---|
| 产品缺陷 | 保留失败与需求差异，不改断言迁就产品 |
| 用例问题 | 依据新页面/契约修复 POM、Service、fixture，做目标回归 |
| 环境/数据 | 修复初始化、账号、依赖、清理，不仅增加重试 |
| 证据不足 | 提出最小补充信息，继续独立检查 |

更新已有代码用分支与 diff，先失败用例后受影响集合，记录修复前后证据和维护耗时。
项目 autoiframe-test-maintenance Skill 可以执行上述流程。

官方参考：[Playwright MCP](https://github.com/microsoft/playwright-mcp)、
[Playwright CLI](https://github.com/microsoft/playwright-cli)、
[Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)。
