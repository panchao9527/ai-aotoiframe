# App 录制/探索转 Screen Object

输入必须说明 Android/iOS、应用初始状态、控件定位证据和预期。
Android 可使用 ARTEMIS 探索结果，Appium Inspector 支持的交互可录制为 Python；
自然语言执行成功、视频或截图都不等于稳定定位器和业务验收。

- 基于 app_driver fixture 和 autotest.mobile.screens.BaseScreen，不自己创建/关闭 driver。
- Android content-desc / iOS accessibilityIdentifier 优先；有依据时使用资源 ID。
- 页面动作放 src/autotest/mobile/<业务名>.py 的 Screen Object；断言在测试。
- 原生与 WebView 分开处理，多个 WebView 必须明确名称，用后恢复原生上下文。
- 滚动/手势需要明确目标和终止条件，系统弹窗/键盘应使用实际设备证据处理。
- API 准备/清理数据；跨测试不共享可变账号和业务对象。
- tests/app/<name>/ 下组织 fixture 和测试，使用 pytest.mark.app。
- 单台设备不启用多个 xdist worker。没有真实设备运行时明确标注未验证。
- ARTEMIS 的坐标、临时控件索引和模型推断仅作探索证据；优先从层级信息提取
  accessibility id/resource-id，无法稳定定位时写入 unresolved，不把坐标直接固化进 Screen。
- ARTEMIS 结果使用 observation 输入，正式草稿仍只能生成 Appium Screen Object 和 pytest。

已有 LoginScreen 是定位契约示例，不能未经确认认定任意真实 App 使用相同标识。
