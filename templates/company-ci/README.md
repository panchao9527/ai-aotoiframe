# 公司项目 CI 接入

这里的模板用于 `project init` 生成的独立公司项目。仓库原有 CI 继续验证练习系统；
公司 CI 使用自己的环境、账号、用例与设备。先完成公司业务模板中的 TODO 和真实断言。

每次选 `api`、`web` 或 `app` 一个套件，入口先执行 `project check --suite ...`，
预检失败立即结束；预检通过才执行 `run`。全跳过、未收集到用例及测试失败都会返回非零。
离线预检不验证网络、账号权限或真机可用性。`--env demo` 在公司 CI 入口被拒绝。

## GitHub Actions

1. 把 `github-actions.yml` 复制到公司项目 `.github/workflows/company-tests.yml`。
2. 保留整个 `templates/company-ci/` 目录，提交项目源码、`pyproject.toml` 与 `uv.lock`。
3. 创建 GitHub Environment，例如 `company_test`，对应
   `configs/environments/company_test.yaml`。在 Environment 中配置表内变量和秘密。
4. 按需配置仓库级 runner 变量，然后手动运行工作流，选择环境与套件。

| 类型 | 名称 | 用途 |
| --- | --- | --- |
| Repository variable | `QA_LINUX_RUNNER` | API/Web runner 单个标签，默认 `ubuntu-24.04`；内网改为公司节点 |
| Repository variable | `QA_ANDROID_RUNNER_LABELS` | JSON 标签数组，默认 `["self-hosted","Linux","qa-android-device"]` |
| Repository variable | `QA_IOS_RUNNER_LABELS` | JSON 标签数组，默认 `["self-hosted","macOS","qa-ios-device"]` |
| Environment variable | `API_BASE_URL`、`WEB_BASE_URL` | 覆盖公司 YAML 中的目标地址；空值保留 YAML |
| Environment variable | `API_AUTH_FILE` | 可选角色鉴权 YAML 路径，角色变量按文件里的引用配置 |
| Environment secret | `API_TOKEN` | 使用统一 Bearer Token 时填写 |
| Environment secret | `TEST_USERNAME`、`TEST_PASSWORD` | Web 账号示意；业务 fixture 使用何种名称，就绑定何种 Secret |
| Environment secret | `TEST_OPERATOR_USERNAME`、`TEST_OPERATOR_PASSWORD`、`TEST_TENANT_ID`、`TEST_READER_TOKEN` | 使用现有角色鉴权示例时按所需角色填写 |
| Environment secret | `APP_TEST_USERNAME`、`APP_TEST_PASSWORD` | App 登录账号示意 |
| Environment variable | `APPIUM_SERVER_URL` | 设备节点可访问的 Appium 地址，不在 URL 内嵌凭据 |
| Environment variable | `ANDROID_UDID`、`APP_ANDROID_PATH` | 明确的测试设备与 Appium 服务端可读取的 Android 安装包路径 |
| Environment variable | `IOS_UDID`、`IOS_DEVICE_NAME`、`IOS_PLATFORM_VERSION`、`APP_IOS_PATH` | iOS 设备、版本和与设备类型匹配的安装包 |

已预装 App 可按设备 YAML 注释改为 `ANDROID_APP_PACKAGE` / `ANDROID_APP_ACTIVITY` 或
`IOS_BUNDLE_ID`，并配置同名变量；iOS 签名变量按公司 WDA 配置填写。
如果下载地址含签名或凭据，把对应 `${{ vars.APP_ANDROID_PATH }}` / `${{ vars.APP_IOS_PATH }}`
改用 `secrets`。不要把真实账号、Token 或安装包写进 Git。

API/Web 节点必须能访问被测网络。自托管 Web 节点需要提前安装 Playwright 系统依赖；
模板在自托管节点只下载 Chromium，在 GitHub 托管 Ubuntu 节点同时安装系统依赖。

App runner 的标签应指向绑定了明确测试设备的专用节点，服务和驱动由节点预先准备；
不自动启动 Appium、安装手机 SDK 或选取个人手机。iOS lane 要求 macOS + Xcode/WDA。
同一平台 job 使用固定设备并发组，且 pytest 强制 `-n 0`。GitHub 并发组只在当前仓库内有效；
多仓库共享设备应使用设备服务的统一租约/锁，或为每个仓库分配专用设备。

## Jenkins

1. 把此处 `Jenkinsfile` 复制到公司项目根目录。
2. 配置参数中的 Linux/Android/iOS agent 标签；所有节点预装 Python 3.11 和 `uv`。
3. 在 Jenkins Credentials 新建 **Secret file**，默认 ID `company-test-env`，
   内容采用 dotenv 格式。按实际套件填写下面的相关变量即可：

```dotenv
API_BASE_URL=https://api.qa.your-company.test
WEB_BASE_URL=https://qa.your-company.test
API_TOKEN=真实测试凭据只写入JenkinsSecretFile
TEST_USERNAME=测试账号
TEST_PASSWORD=测试密码
APPIUM_SERVER_URL=http://127.0.0.1:4723
ANDROID_UDID=明确的测试设备编号
APP_ANDROID_PATH=/srv/builds/company.apk
```

需要角色鉴权、App 账号或 iOS 的变量时，使用上表对应的名称；不需要的行删掉，
不要把这个真实 Secret file 加入源码。未使用秘密时，可清空 `ENV_CREDENTIALS_ID`，
直接由公司 YAML 和节点环境提供配置。

App 构建需要 Jenkins **Lockable Resources** 插件。`DEVICE_RESOURCE` 必须与同设备的
其他 job 共用同一名字；Android/iOS 使用不同设备时可分别配置锁。
本 job 还禁用自身并发，pytest 固定单进程；节点 label 不是设备锁的替代品。

## 报告和验证范围

执行退出码原样向 CI 传播，不使用 `|| true`、`continue-on-error` 或忽略失败。
无论成功或失败都尝试归档 `artifacts/`，包含 HTML、JUnit、Allure 原始结果及失败证据。
在安装或离线预检阶段失败时没有测试报告是正常的；CI 仍然失败，不会被当作通过。
JUnit 的 skip 计数和 `execution.json` 可用于区分真实执行与跳过。

归档使用 7 天保留期示例。报告可能含页面截图与设备页面结构，按公司访问权限和保留规则管理。
模板需要接入公司 CI 和专用设备后实跑；本地语法/命令检查不代表 CI 或真机验证已经通过。

配置语法参考：[GitHub vars 上下文](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#vars-context)、
[Jenkins Pipeline 参数与节点](https://www.jenkins.io/doc/book/pipeline/syntax/)。
