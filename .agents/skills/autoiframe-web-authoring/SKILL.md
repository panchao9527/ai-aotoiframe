---
name: autoiframe-web-authoring
description: 将 Playwright 页面探索或人工录制整理为 autoiframe 的 Python POM 与 pytest 用例，适用于新增 Web 业务测试。
---

# Web 录制与探索

阅读 templates/authoring/web.md 和 docs/09-authoring-workflows.md 的 Web 流程。
有录制时使用录制素材；用户要求 AI 操作时默认使用项目 `qa browser` 包装的
Playwright CLI。需要长时间持续推理、宿主没有终端能力或 CLI 无法完成时再使用 MCP。
工具不可用则说明并继续处理已有素材，不虚构页面观察结果。

- 记录 URL 路径、页面/iframe、已验证的语义定位、观察行为、需求预期和未知项到 observation。
  CLI/MCP snapshot ref 是临时值，不进入长期定位器；页面变化后重新 snapshot。
- CLI 先使用独立任务会话：`uv run qa browser --session NAME open URL --headed`，再执行
  `snapshot`、`generate-locator REF` 和必要动作。NAME 使用本次 author 任务名。
- 默认不使用 `--persistent`、`attach` 或个人浏览器。确需复用测试登录态时使用测试账号和
  `state-load`；状态、快照、截图和 Trace 保存在 artifacts，不提交 Git，也不直接发给模型。
- 普通定位和流程使用 CLI；复杂长会话、需要 MCP 客户端结构化工具时使用 Playwright MCP；
  网络、控制台仍无法定位，或需要性能证据时再使用 Chrome DevTools MCP。
- 人工演示可用 qa record web --name NAME --url URL；关闭录制后检查输入值。
- author prepare --kind web --requirement ... --recording ... --observation ... 按拥有的素材调用，
  不要求两种素材同时存在。读取已有 POM/fixture，优先复用。
- 多文件回复分开页面对象与测试，保留 page/base_url，移除重复动作、硬编码凭据和浏览器创建。
- 导入标准 response.json，执行目标用例并读取 Trace/摘要。深入网络或性能问题再用 DevTools。
  共同调试一个浏览器时只安排一个操作控制者，避免相互改变页面。
- 审查业务预期、清理和实际结果后入库。已有授权覆盖的工作持续完成。
- 探索结束执行 `uv run qa browser --session NAME close`；附着外部浏览器时用 detach。

页面当前行为不能代替需求；接口错误时保留产品失败，不能删断言、加 skip 或无限重试。
