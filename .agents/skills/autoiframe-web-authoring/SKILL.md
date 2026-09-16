---
name: autoiframe-web-authoring
description: 将 Playwright 页面探索或人工录制整理为 autoiframe 的 Python POM 与 pytest 用例，适用于新增 Web 业务测试。
---

# Web 录制与探索

阅读 templates/authoring/web.md 和 docs/09-authoring-workflows.md 的 Web 流程。
有录制时使用录制素材；用户要求 AI 操作时使用宿主可用的 Playwright MCP/CLI。
工具不可用则说明并继续处理已有素材，不虚构页面观察结果。

- 记录 URL 路径、页面/iframe、已验证的语义定位、观察行为、需求预期和未知项到 observation。
  MCP snapshot ref 是临时值，不进入长期定位器。
- 人工演示可用 qa record web --name NAME --url URL；关闭录制后检查输入值。
- author prepare --kind web --requirement ... --recording ... --observation ... 按拥有的素材调用，
  不要求两种素材同时存在。读取已有 POM/fixture，优先复用。
- 多文件回复分开页面对象与测试，保留 page/base_url，移除重复动作、硬编码凭据和浏览器创建。
- 导入标准 response.json，执行目标用例并读取 Trace/摘要。深入网络或性能问题再用 DevTools。
  共同调试一个浏览器时只安排一个操作控制者，避免相互改变页面。
- 审查业务预期、清理和实际结果后入库。已有授权覆盖的工作持续完成。

页面当前行为不能代替需求；接口错误时保留产品失败，不能删断言、加 skip 或无限重试。
