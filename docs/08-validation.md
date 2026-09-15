# 08 · 本次交付验证记录

验证日期：2026-09-16（北京时间）。以下是本机实际运行结果，迁移项目后需要重新验证。

## 环境与锁定版本

Windows、Python 3.11.6、uv 0.12.15。关键依赖已在 `uv.lock` 锁定：

| 工具 | 本次安装版本 |
| --- | --- |
| pytest | 9.1.1 |
| HTTPX | 0.28.1 |
| Playwright / pytest-playwright | 1.63.0 / 0.9.0 |
| Appium Python Client / Selenium | 6.0.6 / 4.49.0 |
| pytest-html / allure-pytest | 4.2.0 / 2.16.0 |
| pytest-xdist | 3.8.0 |

Chromium 与无头浏览器、FFmpeg 已安装。`uv sync --frozen` 重装检查成功，
Ruff 代码检查与格式检查通过。

## 实际测试

运行 `python -m autotest run --suite all -- -n 2`：**122 passed，1 skipped，0 failed，0 errors**。

- 框架单元测试：配置优先级与错误、HTTP 客户端、AI 协议与草稿行为、脱敏、
  Appium Options/会话清理/WebView 切换、模板、失败证据等。
- 接口业务测试：本地练习服务的参数化登录、鉴权、创建/查询/删除、字段校验、错误输入。
- Web 业务测试：真实启动 Chromium，验证登录成功/失败、项目创建及 API 核对清理、iframe 表单。
- App 登录业务示例：默认跳过，未连接设备。这条 skipped 不计入已通过的 122 条。

## 失败路径验证

显式执行 `examples/failure_demo.py` 的错误断言，串行和两个 worker 均正确返回失败，退出码为 1。
已验证生成独立 HTML、JUnit、Allure 原始结果、脱敏 `call.json`、PNG 截图、WebM 视频和
可正常解压的 `trace.zip`。截图同时嵌入自包含 HTML，并作为 Allure 附件保存。
这是预期失败的独立实验，不属于默认测试集合。

单元测试还通过子进程制造 setup/call/teardown 三个阶段的失败，检查退出码和各自摘要。

## AI 验证范围

实际生成过接口用例离线提示词，以及来自真实 Web 失败摘要的离线分析提示词。
模拟 HTTP 响应覆盖在线协议、认证头、超时、错误响应、空响应、语法检查和不执行草稿的行为。
没有向真实模型发送公司数据，没有使用 API Key 或调用付费服务；模型输出质量待接入后评估。

## 尚需你接入的部分

- Android/iOS：自己的安装包、实际页面定位、测试账号、设备和 Appium 服务；iOS 常规执行节点需要 Mac/Xcode。
- 公司接口/Web：真实测试环境、接口契约、鉴权和业务断言，参见迁移手册。
- GitHub Actions/Jenkins：已提供配置，但尚未推送到远程或在你的 CI 执行。
- Firefox/WebKit、macOS/Linux：有标准工具入口，尚未在本次 Windows 验证中实际运行。

`artifacts/` 是本机生成物，不提交 Git。换机器后重新运行会生成新目录，不能把本机报告当作新环境的验收结果。
