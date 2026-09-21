# 10 · App 录制、AI 整理和设备执行

正式 App 回归使用 Appium；Android AI 探索可选用 ARTEMIS。浏览器 MCP 不是原生 App
通用驱动。先完成 [App 接入](04-app.md) 的设备、应用、账号与 capabilities 配置。

## 人工录制

在 Appium Inspector 建立会话，开启 Recorder、选择 Python，通过 Inspector 操作并保存代码。
记录平台、开始页面、预期、定位依据与未知项。直接在手机上任意触摸不保证会被录制。
qa record app 显示此路径，不声称已经启动 Inspector 或连接设备。

```powershell
uv run qa author prepare profile-flow --kind app --requirement examples/authoring/app-requirement.md --recording examples/authoring/app-recording.py
uv run qa author generate profile-flow --response examples/authoring/responses/app.json
uv run qa author validate profile-flow
```

此教学样例保留真实定位与登录条件未知项，静态验证预期失败。接入实际应用后核实并修改 draft，
清除已解决的 manifest.json/unresolved，配置 APP_CAPS_FILE、APPIUM_SERVER_URL、APP_PLATFORM
以及账号环境变量，再执行：

```powershell
uv run qa author validate profile-flow --execute --env test --run-app
uv run qa author promote profile-flow --reviewed
```

## AI 自主操作

Android 默认路由为：已部署 ARTEMIS 时使用 `qa artemis` 或 ARTEMIS MCP 获取截图、层级、
Logcat 与轨迹；没有 ARTEMIS 时使用 Appium Inspector。iOS 继续使用 Appium 工具链。
二者最终都生成相同的 Screen/pytest 产物，不能虚构真实设备观察结果。

ARTEMIS 作为独立服务部署，不与本项目 Python 环境混装。客户端安装、环境配置、设备选择、
命令示例和安全边界见 [ARTEMIS Android AI 探索](14-artemis-integration.md)。

Screen 复用 BaseScreen，定位/动作集中，业务断言留在测试。API 造数清理，设备只做目标交互。
Android/iOS 流程可复用但不假设定位相同；多个 WebView 明确选择，单设备不多 worker。
分别记录静态、mock、设备连接与业务执行范围。iOS 需要适合的 macOS/Xcode 执行节点，
Windows 重构不代表完成 iOS 验收。

官方参考：[ARTEMIS](https://github.com/google/artemis)、
[Recorder](https://github.com/appium/appium-inspector/blob/main/docs/session-inspector/recorder.md)、
[Context](https://appium.io/docs/en/latest/guides/context/)。
