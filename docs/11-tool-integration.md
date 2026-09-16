# 11 · 浏览器工具接入与失败维护

MCP 配在编程助手一侧，项目提供模板、上下文和验证命令。Playwright MCP/CLI 用于页面操作，
Chrome DevTools 深入网络/控制台/性能；按需选择，不必每次同时启用。

## 配置

configs/tools/mcp.example.json 是通用配置示例，不会修改全局或个人配置。
版本在开发时从 npm 核对并固定，升级需重新验证参数。宿主配置格式不同时按其文档转换；
Windows 若无法解析 npx，可选 npx.cmd。Python 测试不依赖 MCP。
已有 Playwright CLI + Skills 的助手也可直接使用。

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
