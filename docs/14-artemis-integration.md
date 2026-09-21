# 14 · ARTEMIS Android AI 探索

ARTEMIS 接收自然语言任务，在 Android 真机或模拟器上探索页面、跨 App 操作并收集截图、
层级、Logcat、视频和轨迹。本项目把它放在“编写素材层”，正式回归仍使用 Appium：

```text
需求 + Android 测试设备
        ↓
独立 ARTEMIS 服务（Python 3.12+、ADB、模型、图像处理）
        ↓  HTTP 轻量客户端或宿主 MCP
autoiframe artifacts/artemis/result.json
        ↓  author prepare --observation
AI 生成 Appium Screen Object + pytest 草稿
        ↓
真实 Appium 设备验证和 CI 回归
```

## 1. 为什么独立部署

完整 ARTEMIS 依赖 Python 3.12+、LangGraph、多个模型 SDK、ADB、UIAutomator2、OpenCV 和
FFmpeg。本项目继续支持 Python 3.11，不能把整套 Agent 依赖加入执行环境。

`artemis` extra 只安装上游仓库的 `artemis-client` 子包。该客户端支持 Python 3.10+，没有
运行依赖，只通过 HTTP 调用设备主机。本项目固定上游提交
`371aa6df56880643da57b30da936e9812fb0ec66`，升级时重新审查协议并更新 `uv.lock`。

```powershell
uv sync --extra artemis --frozen
uv run python -c "import artemis_client; print(artemis_client.__version__)"
```

没有安装 extra 时，API/Web/Appium 原有能力不受影响；调用 `qa artemis` 会明确提示安装。

## 2. 准备独立设备主机

在连接专用 Android 测试机或模拟器的主机上单独克隆 ARTEMIS，按其 README 安装。模型 API
Key 只放 ARTEMIS 主机的 `.env`，不能写入本项目或聊天。首次评估建议：

- 使用模拟器或专用测试手机，不选择个人手机；
- 设置 `ARTEMIS_HELPER_AUTO_INSTALL=false`，由设备管理员明确安装/检查 Helper；
- 不执行 `artemis mcp --install all`，避免自动修改所有 IDE 的全局 MCP 和规则；
- 先运行 `artemis doctor`，确认 ADB、设备授权、模型和视频工具链；
- 评估公司页面截图、控件文字和日志能否发送给选定模型服务。

ARTEMIS 管理 API 当前不应直接暴露公网。推荐同机 `127.0.0.1`、SSH 隧道，或在服务前放置
HTTPS + Bearer 认证反向代理。本框架拒绝通过普通 HTTP 连接非 loopback 地址。

## 3. 配置 autoiframe

`.env` 示例：

```dotenv
TEST_ENV=test
ARTEMIS_BASE_URL=http://127.0.0.1:8000
# 只有 HTTPS 认证代理才需要客户端 Token。
# ARTEMIS_TOKEN=replace-with-proxy-token
ARTEMIS_DEVICE_SERIAL=emulator-5554
ARTEMIS_PROFILE=flash
ARTEMIS_TIMEOUT_SECONDS=600
```

先执行只读检查：

```powershell
# 快速检查调度服务。
uv run qa artemis --env test check

# 深度检查可能访问设备、截图和 UI 层级，耗时更长。
uv run qa artemis --env test check --deep

# 查看设备 serial、状态和是否忙碌；不会执行页面动作。
uv run qa artemis --env test devices
```

## 4. 执行有边界的探索任务

把任务写到 UTF-8 文件，例如 `artifacts/artemis-goals/login.md`。该目录被 Git 忽略。任务内容
应写清起始状态、允许范围、操作目标、预期证据和停止条件，不能包含真实密码或生产数据。

```markdown
打开已安装的测试应用，从登录页使用已经准备好的测试登录态进入首页。
只检查是否出现异常弹窗，返回首页标题、可见主导航和相关 Logcat 错误。
不要修改系统设置，不要操作其他 App，不要购买、支付或删除数据。
```

Flash 适合短且明确的探索：

```powershell
# 先离线检查范围；只输出任务文件 SHA-256，不连接 ARTEMIS 或设备。
uv run qa artemis --env test run `
  --goal-file artifacts/artemis-goals/login.md `
  --device emulator-5554 `
  --package com.example.test `
  --profile flash `
  --dry-run

# 审查通过后执行。
uv run qa artemis --env test run `
  --goal-file artifacts/artemis-goals/login.md `
  --device emulator-5554 `
  --package com.example.test `
  --profile flash `
  --expected-output "最终页面、关键控件、截图/日志证据"
```

Pro 适合长流程和严格检查：

```powershell
uv run qa artemis --env test run `
  --goal-file artifacts/artemis-goals/order-flow.md `
  --device emulator-5554 `
  --package com.example.test `
  --profile pro `
  --verification-level strict `
  --explorer-mode pro `
  --timeout 1200
```

默认必须指定设备和 package。只有明确需要时才使用：

- `--allow-auto-device`：授权服务自动选择空闲设备；
- `--allow-cross-app`：授权离开目标 package，例如进入系统设置或浏览器。

两项开关只说明执行范围，不能代替业务授权。生产设备、生产账号、支付、删除、系统设置修改
仍不在默认范围内。

结果保存在 `artifacts/artemis/<时间>/result.json`，包含任务 ID、状态、设备、回合数和脱敏输出，
不保存原始服务响应和原始任务文本。文本脱敏不是图片/日志 DLP，分享前仍需人工检查。

## 5. 转成正式 Appium 用例

ARTEMIS 成功表示模型完成了本次探索，不代表稳定回归或业务验收。把结果作为 observation：

```powershell
uv run qa author prepare login-flow --kind app `
  --requirement requirements/login.md `
  --observation artifacts/artemis/20260921-xxxxxx/result.json
uv run qa author generate login-flow --response artifacts/ai/login-flow/response.json
uv run qa author validate login-flow
```

生成时遵守以下规则：

- 坐标和临时控件索引不进入 Screen Object；
- 优先使用已验证的 accessibility id、resource-id、文本语义；
- 页面观察属于 `basis="observation"`，不能冒充需求预期；
- 不稳定定位、未知权限、登录状态和无法清理的数据写入 `unresolved`；
- 配置真实 Appium capabilities 后执行 `author validate --execute --env test --run-app`；
- ARTEMIS 探索结果与 Appium 真机执行结果分别保留，不能互相替代。

## 6. MCP 接入

ARTEMIS 自带 MCP，可让 Codex 等宿主直接使用 `mobile_run_task`、`mobile_get_device_state`、
`mobile_inspect_trace` 和 `mobile_diagnose`。在 ARTEMIS checkout 中使用
`uv run artemis mcp --generate-config codex` 生成配置，再由用户审查路径和权限后安装。

本仓库不会自动修改全局 Codex 配置或复制 ARTEMIS 全局规则。无论通过 HTTP 客户端还是 MCP，
最终观察材料和 Appium 生成协议保持一致。

## 7. 当前边界

- 当前接入只面向 Android；iOS 继续使用 Appium/XCUITest；
- 没有 ARTEMIS 服务和测试设备时，只能验证客户端协议和错误边界；
- AI 探索存在模型成本、延迟和非确定性，不放入默认 CI 回归；
- 多设备由 ARTEMIS 服务调度，Appium 正式回归仍按独立 CI job 管理；
- 当前客户端属于早期版本，升级固定提交前必须重新运行框架和真实设备试点。

## 8. 本轮验证记录（2026-09-21）

- `uv lock` 成功锁定 `artemis-client 0.1.0` 与上游提交 `371aa6df`；
- `uv sync --extra artemis --frozen` 成功构建、安装并导入轻量客户端；
- `uv sync --frozen` 会移除该可选客户端，原有默认依赖保持不变；
- 客户端配置、HTTPS/隧道边界、设备/package 授权、Flash/Pro 参数、任务文件大小、
  脱敏产物和 CLI 转发均有离线单测；
- 完整默认集合为 **224 passed, 1 skipped**，App 跳过项仍是未配置真实设备；
- Ruff、格式和差异检查通过。

本次没有 ARTEMIS 服务地址、模型 API Key 或 Android 测试设备，因此没有执行自然语言设备任务，
也没有验证 Helper、真实截图/Logcat、MCP 或多设备调度。离线客户端通过不能替代真实设备试点。
本地报告目录为 `artifacts/20260921-032953-d6df10/`。
