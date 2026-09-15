# 04 · Android / iOS App 自动化从零接入

## 先理解你要准备什么

本项目使用 **pytest → Appium Python Client → Appium Server → 平台驱动 → 手机 App**。

| 部分 | 做什么 | 放在哪里 |
| --- | --- | --- |
| pytest / Python Client | 执行用例，把点击、输入等命令发送给服务 | 你的 Windows / macOS / Linux 电脑 |
| Appium Server | 接收命令，分配设备会话 | 连接设备的电脑，或设备云 |
| UiAutomator2 | 驱动 Android 真机和模拟器 | Android 测试服务器 |
| XCUITest / WebDriverAgent（WDA） | 驱动 iOS，WDA 是设备上的测试助手 | 本文推荐 Mac + Xcode 路线 |
| capabilities（能力配置） | 告诉服务：测试哪台设备、哪个 App、哪些端口 | `configs/devices/*.yaml` |
| Screen Object | 把页面定位和操作封装成方法 | `src/autotest/mobile/screens.py` |

**仓库没有附带 APK、IPA、真实设备或第三方 App 账号。** `tests/app/test_login.py` 是你们公司 App 的接入模板；其中四个 accessibility id 是示例契约，需要先与实际 App 对齐。框架单元测试可在无设备环境下运行，不能代表 App 业务已经在真机上跑通。

先按 README 安装 Python 依赖（`uv sync --locked`）。下面命令均在仓库根目录执行，除非标明在 Mac 或设备服务器执行。

## 1. 安装 Appium Server

Appium Server 和 Python Client 是两套依赖：`uv sync` 安装 Python Client，下面的 npm 命令安装服务端。

Appium 3 官方 Node.js 范围为 `^20.19.0 || ^22.12.0 || >=24.0.0`，npm 至少 10。新项目可以从 Node 24 LTS 开始，并在团队内固定实际验证过的 Node、Appium 和 driver 版本。[官方升级说明](https://appium.io/docs/en/3.2/guides/migrating-2-to-3/)

```powershell
node --version
npm --version
npm install --global appium@3
appium --version
appium driver list --installed
```

Appium 主程序安装完成后，仍需单独安装下面的 Android/iOS driver。`uv.lock` 只锁定 Python 依赖，不能锁定 Node、SDK、Xcode 或手机系统；把实际版本写入团队设备环境说明，在 CI 镜像或设备服务器统一维护。

## 2. Android：从能看到设备开始

### 2.1 准备 SDK、JDK 和模拟器/真机

1. 安装 [Android Studio](https://developer.android.com/studio)。打开 SDK Manager，安装 **Android SDK Platform-Tools、Android SDK Command-line Tools、Build-Tools** 和与你们 App 匹配的 Android SDK Platform。
2. 使用模拟器：在 Device Manager 创建 AVD，下载目标版本系统镜像，启动到桌面。使用真机：开启开发者选项和 USB 调试，连接电脑并在手机上允许该电脑调试。
3. 安装与工具链兼容的 JDK。新环境可先使用 JDK 17，设置 `JAVA_HOME` 指向其安装目录；如果公司构建工具要求其他版本，以团队实际验证配置为准。
4. 设置 `ANDROID_HOME` 指向 SDK 目录，把 SDK 的 `platform-tools`、`emulator`、`cmdline-tools/latest/bin` 和 JDK `bin` 加入 PATH。环境变量中的目录必须是本机实际安装路径。

Windows PowerShell 示例（只影响当前终端；长期配置可在 Windows“编辑系统环境变量”中保存）：

```powershell
# SDK 默认安装位置通常如此；请在 Android Studio 中核对实际位置。
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
# 替换成你自己的 JDK 安装路径。
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:PATH = "$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:ANDROID_HOME\cmdline-tools\latest\bin;$env:PATH"
java -version
adb version
adb devices -l
```

`adb devices -l` 应显示设备序列号及 `device` 状态。`unauthorized` 表示未授权，`offline` 表示连接尚未就绪；先解决这一步再执行测试。Android `deviceName` 只是描述，**`udid` 才明确选中设备**。UiAutomator2 6+ 支持 Android 8 / API 26 起；老系统需要另外选择兼容的驱动版本。[UiAutomator2 官方要求及能力配置](https://github.com/appium/appium-uiautomator2-driver)

### 2.2 安装驱动、检查依赖、启动服务

```powershell
appium driver install uiautomator2
appium driver doctor uiautomator2
appium --address 127.0.0.1 --port 4723
```

最后一条会持续运行并显示日志，请保持终端开启，再开第二个终端运行 Python 用例。Appium 2/3 默认路径为 `/`，服务地址为 `http://127.0.0.1:4723`；旧教程的 `/wd/hub` 只有在服务显式设置该 base path 时才适用。[Python Client 官方用法](https://github.com/appium/python-client)

### 2.3 配置 APK 并运行

从开发/构建平台拿到**测试环境 APK**。在第二个 PowerShell 终端设置：

```powershell
$env:ANDROID_UDID = 'emulator-5554' # 替换成 adb devices 中实际的序列号
$env:APP_ANDROID_PATH = 'C:\builds\your-company-test.apk'
$env:APP_TEST_USERNAME = 'your-test-user'
$env:APP_TEST_PASSWORD = 'your-test-password'
uv run pytest tests/app -n 0 --run-app --app-platform android --app-caps configs/devices/android.yaml --appium-url http://127.0.0.1:4723
```

运行前先完成本文第 4 节的定位适配；否则你会得到明确的找不到元素错误。`appium:app` 可以是 Appium **服务器所在机器**上的绝对路径，或该服务器可下载的 URL；远程设备服务不认识 Windows 客户端上的 `C:\builds`。

**预装 App 模式：**复制设备模板为项目自己的文件，删除 `appium:app` 行，启用模板底部 `appium:appPackage` 和 `appium:appActivity` 两行，设置对应环境变量。package 是 Android 包名，activity 是启动界面名，向开发同事获取最准确。文件中的 `${NAME}` 仅在对应行启用时解析，未定义或为空会立刻失败，不会启动“随便一个 App”。

## 3. iOS：推荐 Mac 服务端，Windows 也能写和运行 Python

### 3.1 Mac 上的基础环境

1. 安装与设备 iOS 版本匹配的 Xcode 和 macOS，启动 Xcode 完成初始安装，在 Xcode Settings 中选择 Command Line Tools。
2. 在 Mac 上安装前述 Node / npm / Appium 3；再执行下面命令。
3. 模拟器在 Xcode 中安装对应 iOS runtime，拿到开发为 **iOS Simulator 构建的 `.app` 或 `.app.zip`**。真机用的 IPA 不能当作模拟器包使用。

```bash
xcode-select -p
xcodebuild -version
xcrun simctl list devices available
appium driver install xcuitest
appium driver doctor xcuitest
appium --address 127.0.0.1 --port 4723
```

XCUITest 10+ 对应 Appium 3；iOS、Xcode、macOS 和 driver 需要成套匹配。本文采用常规 Mac 路线；官方也有依赖预先准备 WDA 的非 macOS 高级路径，初次落地优先远程连接 Mac。[XCUITest 兼容要求](https://appium.github.io/appium-xcuitest-driver/latest/installation/requirements/)、[Apple Xcode 系统要求](https://developer.apple.com/xcode/system-requirements)

### 3.2 真机还要配置 WDA 签名

WDA 是 Appium 安装到 iPhone 上的测试应用。真机必须允许其安装并运行，这与被测 App 自己的签名是两个问题。

1. 连接 iPhone，在手机上信任 Mac，在 Xcode 的 Devices and Simulators 中确认设备可用。
2. 开启 iOS 开发者模式；按设备版本在开发者设置中允许 UI Automation。
3. 与 iOS 开发同事确认 Apple Development 证书、Team ID、包含这台设备 UDID 的 provisioning profile。
4. 在 iOS YAML 中启用 `appium:xcodeOrgId`、`appium:xcodeSigningId`、`appium:updatedWDABundleId`，填写团队已配置的值。WDA bundle id 必须能被该签名配置授权。
5. 初次签名失败时，在 Mac 的 Appium 日志中找 `xcodebuild` 输出，检查证书、设备注册、bundle id、profile；不要反复重试 Python 用例掩盖环境问题。

WDA 的设备信任、开发者模式和签名准备详见 [官方设备配置](https://github.com/appium/appium-xcuitest-driver/blob/master/docs/getting-started/device-setup.md) 与 [官方 Provisioning Profile 指南](https://appium.github.io/appium-xcuitest-driver/latest/getting-started/provisioning-profile/)。需要在 Xcode 中手动检查 WDA 工程时，可以在 Mac 执行 `appium driver run xcuitest open-wda`。

### 3.3 设置设备参数

同一台 Mac 上执行测试时：

```bash
export IOS_DEVICE_NAME='Your iPhone Simulator'
export IOS_UDID='从 simctl 或 Xcode 获取的实际 UDID'
export IOS_PLATFORM_VERSION='设备实际系统版本'
export APP_IOS_PATH='/Users/yourname/builds/YourApp.app'
export APP_TEST_USERNAME='your-test-user'
export APP_TEST_PASSWORD='your-test-password'
uv run pytest tests/app -n 0 --run-app --app-platform ios --app-caps configs/devices/ios.yaml --appium-url http://127.0.0.1:4723
```

真机时把 App 路径换成已签名的真机包，并设置签名变量。预装 App 时删除 `appium:app` 行，启用 `appium:bundleId`，设置 `IOS_BUNDLE_ID`。

**Windows 客户端 → Mac 服务端：**Mac 上将 Appium 监听地址设为自己的可信局域网地址，例如 `appium --address 192.168.1.20 --port 4723`。Windows 运行相同 pytest 命令，只把 `--appium-url` 改成 `http://192.168.1.20:4723`；`APP_IOS_PATH` 仍是 Mac 上的路径。仅在团队受控网络中允许该端口，不应把无认证设备控制服务直接暴露到公网。

## 4. 用 Inspector 找定位，然后维护 Screen Object

1. 从 [Appium Inspector 官方仓库](https://github.com/appium/appium-inspector) 安装对应桌面版本。
2. 填服务器 host、port、path `/`，将 YAML 中的 capabilities 转成 Inspector 的 JSON，并手动填入环境变量实际值。Inspector 不会替本框架解析 `${NAME}`。
3. 点击 Start Session，点击目标元素，查看 `accessibility id`、Android `resource-id` 或 iOS identifier。
4. 优先请开发给关键元素加稳定的 accessibility id。Android 通常来自 `content-desc`，iOS 来自 `accessibilityIdentifier`。不依赖展示文案、屏幕坐标或一大串绝对 XPath。
5. **结束 Inspector 会话后再跑 pytest**，避免两个会话争抢同一设备。

仓库的登录契约是：

| 元素 | 示例 accessibility id | 修改位置 |
| --- | --- | --- |
| 用户名输入框 | `login.username` | `LoginScreen.USERNAME` |
| 密码输入框 | `login.password` | `LoginScreen.PASSWORD` |
| 登录按钮 | `login.submit` | `LoginScreen.SUBMIT` |
| 登录成功后的首页根节点 | `home.screen` | `LoginScreen.HOME` |

你需要修改 `src/autotest/mobile/screens.py` 的四个定位常量。若 Android/iOS 标识不同，新增 `AndroidLoginScreen` 和 `IOSLoginScreen` 子类，覆盖常量；保持 `login()` 等业务方法名一致，用 fixture 按平台选择类。不要在每条用例复制两套点击过程。

```python
from appium.webdriver.common.appiumby import AppiumBy
from autotest.mobile.screens import BaseScreen


class OrdersScreen(BaseScreen):
    # 下面是讲解结构的假设定位，需先在你们 App 中确认。
    FIRST_ORDER = (AppiumBy.ACCESSIBILITY_ID, "orders.first")
    ORDER_NUMBER = (AppiumBy.ACCESSIBILITY_ID, "order.number")

    def open_first_order(self):
        self.tap(self.FIRST_ORDER)  # 自动等到可点击；超时即失败

    def order_number(self):
        return self.text(self.ORDER_NUMBER)
```

测试负责准备业务数据和断言；Screen 负责元素定位与交互。比如先通过 API 为独立测试账号创建订单，再进入订单页验证确切订单号。不要只断言“某元素存在”就认为整条业务正确。

## 5. 混合 App 的 WebView

WebView 是 App 中嵌入的网页，与原生控件属于不同 context。先让开发提供可调试的测试包；Android 还需要与目标 WebView 匹配的 ChromeDriver，iOS 需要按官方要求开启 Safari Web Inspector/远程自动化。原生元素用 accessibility id，网页元素使用 Selenium 的 CSS 选择器。

```python
from selenium.webdriver.common.by import By
from autotest.mobile.screens import BaseScreen

screen = BaseScreen(app_driver)
with screen.webview("WEBVIEW_com.company.app"):
    # 这是结构示例：context 名和 CSS 要换成 Inspector 中的实际值。
    screen.fill((By.CSS_SELECTOR, '[data-testid="coupon"]'), "TEST10")
    screen.tap((By.CSS_SELECTOR, '[data-testid="apply-coupon"]'))
# 即使 with 块中断言失败，finally 也会切回 NATIVE_APP。
```

无参数时只允许唯一 WebView；多个 WebView 时必须传确切名称，防止选中广告等无关网页。切 context 和网页 iframe 是不同概念：进入网页后若目标还在 iframe 内，需要 Selenium 的 frame 切换。

## 6. 等待、重置与并发原则

- **显式等待**：`BaseScreen` 等元素可见/可点击；不写固定 `sleep(5)`。默认隐式等待为 0。
- **三类超时**：`APP_WAIT_SECONDS` 是页面元素等待秒数；`create_driver(command_timeout=120)` 是单条 HTTP 命令的客户端超时；capabilities 的 `appium:newCommandTimeout` 是两条命令间空闲多久后结束会话。安装/WDA 启动另有驱动能力项，单位可能是毫秒。
- **状态隔离**：每个用例独立 driver，会在成功或失败后 `quit()`。`noReset: false` 不等于清除一切业务状态，尤其 iOS 的钥匙串登录信息、服务端数据；用 API、退出登录步骤或团队测试入口显式准备前置状态。
- **权限弹窗**：按需求编写首次启动处理步骤。仅当当前测试不验证权限流程时才考虑驱动自动授权配置。
- **一份设备配置一台设备**：本框架阻止 `--run-app -n 2` / `-n auto`。单台手机不能让多 worker 同时抢 UI；设备云也必须给每个会话分配独立设备。
- **真正多设备**：先用独立 CI job，各自传 YAML、udid 和报告目录。Android 的 `systemPort`、WebView 的 `chromedriverPort` 等，iOS 的 `wdaLocalPort`、`mjpegServerPort` 及 `derivedDataPath` 需要隔离。初期每台设备一个 Appium 服务（如 4723/4725），排查更简单。[iOS 并发官方说明](https://appium.github.io/appium-xcuitest-driver/latest/guides/parallel-tests/)

例如两台 Android：device-a YAML 配 `udid=A, systemPort=8200`，device-b 配 `udid=B, systemPort=8201`。两条独立任务分别运行 `--app-caps configs/devices/device-a.yaml` / `device-b.yaml`；不要只换 pytest worker 数量。服务共享同一电脑时，确认所有转发端口没有冲突。

## 7. 常见失败怎么查

| 现象 | 优先检查 |
| --- | --- |
| App 用例显示 skipped | 默认行为；准备设备后加 `--run-app` |
| 提示缺环境变量 | 检查对应 YAML 中启用的 `${NAME}`；`.env`/终端中必须有非空值 |
| Connection refused | Appium 是否启动、URL/端口/防火墙是否正确 |
| 404 / unknown command | Appium 地址是否错误沿用 `/wd/hub`；驱动与客户端是否兼容 |
| Could not find driver | 对应服务电脑上是否安装 uiautomator2 / xcuitest |
| 找不到 Android 设备 | `adb devices -l`、USB 调试授权、正确 `udid` |
| 找不到 App 安装包 | 文件是否在服务端电脑；是否误用了客户端本地路径 |
| iOS xcodebuild 65 / WDA 启动失败 | Mac 日志、签名 profile、Team ID、WDA bundle id、设备信任及 Xcode 兼容性 |
| 页面定位超时 | 先看失败截图/源码和 Inspector：页面是否正确、弹窗是否阻挡、定位是否变更 |
| 已登录导致找不到登录输入框 | 前置状态没有隔离；补退出登录/API 清理，核对 iOS 钥匙串状态 |
| Native 找不到网页按钮 | context 是否为正确 WebView，网页是否在 iframe 内 |

AI 可以读取**脱敏后的**堆栈、相关 Screen 代码和你补充的页面信息，提出定位或等待修改建议；提交前需要人审查，之后重新在目标设备验证。AI 无法仅凭代码推断你们 App 的实际 accessibility id，也不应直接删除断言让失败变绿。

## 8. 最短接入清单

1. SDK/驱动 doctor 通过，设备可识别。
2. Inspector 能安装并打开你们的测试 App。
3. 配好目标平台 YAML、测试账号和服务地址。
4. 替换四个登录定位，处理首次启动弹窗，保证未登录前置状态。
5. 先串行跑一条登录测试，再增加订单等核心路径。
6. 在 Android 和 iOS 各实际执行一次，保存设备、系统、App 构建版本及报告。
7. 把通过的环境固定到团队设备服务器或 CI；后续按公司项目复制 Screen、用例和设备配置。
