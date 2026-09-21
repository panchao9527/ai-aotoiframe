---
name: autoiframe-app-authoring
description: 将 ARTEMIS Android 探索、Appium Inspector 录制或真实设备观察整理为 autoiframe Screen Object 和 pytest App 用例，区分探索证据与正式回归。
---

# App 用例编写

阅读 templates/authoring/app.md 与 docs/10-mobile-authoring.md。
输入需说明平台、应用初始状态、需求、ARTEMIS 结果、Inspector Python 录制或控件证据。

1. Android AI 探索优先使用已配置的 `qa artemis` 或宿主 ARTEMIS MCP；先执行 check/devices，
   明确测试设备和 package。iOS、无 ARTEMIS 或人工演示使用 Appium Inspector。
   浏览器 MCP 不能代替通用原生 App 控制。
2. 标明定位来源、平台和验证状态；优先 accessibility id/resource-id。
   系统权限、键盘、滚动和多个 WebView 按实际证据处理，不编造定位。
3. ARTEMIS 只提供当前实现观察和诊断证据，不把自然语言任务结果直接当稳定回归。
   author prepare NAME --kind app --requirement ... --recording ... --observation ...。
4. 复用 BaseScreen/app_driver，动作和定位放 Screen，业务断言放测试，API 准备数据。
   导入标准 response.json，未知条件放 unresolved。
5. 解决未知项并配置具体设备后 author validate NAME --execute --env ENV --run-app。
   单设备不启用多 worker；结合设备证据审查后入库，不重复索取已有授权。
6. 没有设备时交付可审阅代码和未验证项；mock、静态检查、连接成功都不代表真实业务通过。
7. 不自动选择个人手机，不自动安装 Helper，不执行 `mcp --install all` 修改全局配置；这些动作
   仅在用户明确选择测试设备和部署方式后进行。ARTEMIS 失败不通过放宽 Appium 断言处理。
