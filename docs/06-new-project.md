# 06 · 带到新公司 / 新项目使用

目标是复用工程结构，再补上公司业务。地址、账号和定位器会改变；测试的组织方式、报告入口和分层原则可以继续使用。

## 推荐入口：一条命令生成公司项目

```text
uv run --frozen qa project init --name company-qa --output ../company-qa
cd ../company-qa
uv sync --frozen
```

在生成项目中按 README 配置 `company_test.yaml`、`.env`、`configs/business/smoke.yaml`，
然后分别运行 `qa project check --env company_test --suite api`、`--suite web`、`--suite app`。
`--suite all` 会汇总三端配置问题；App 的 `--app-platform`、`--app-caps` 可覆盖 YAML。
占位域名、缺少账号变量、无效 CA/登录态、未明确设备选择会在离线预检中失败。
预检不会登录、操作页面或连接手机，不能替代真实测试。

生成目录自带源码、锁文件、框架单测、业务 Service/Page/Screen 和 GitHub/Jenkins 模板。
公司业务没有 demo 标记；默认环境为 `company_test`。未填业务冒烟预期时明确失败，
App 未启用时跳过。`run --suite all` 要求 API/Web 分别实际执行，显式启用 App 后也检查 App。
Android/iOS 分别执行验收。`.env`、报告、Git 历史、原环境文件不随初始化复制。
初始化只能用于完整源码仓库，拒绝覆盖现有目录。公司 CI 指南在生成项目的
`templates/company-ci/README.md`。

企业网络与 Web 登录态配置：

| 变量 | 行为 |
| --- | --- |
| `API_CA_BUNDLE` | 本地 PEM CA 文件，追加到默认可信根；始终验证 TLS |
| `API_TRUST_ENV` | 默认 false；true 时读取 HTTPX 代理和环境证书设置 |
| `HTTPS_PROXY` / `NO_PROXY` | 仅 API_TRUST_ENV=true 时作用于 API 客户端 |
| `WEB_STORAGE_STATE` | Playwright 导出的 JSON 登录态，每个 context 独立使用；不保证会话未过期 |

显式 API_CA_BUNDLE 优先于 SSL_CERT_FILE/DIR；Web 证书由系统/浏览器配置。
将登录态放 `.auth/`、证书放 `.secrets/`，这些目录已加入 Git 忽略。
登录态可由自己的登录 fixture 用 `context.storage_state(path=...)` 导出。
初始公司 API 角色为 `none`；受保护接口需把 `configs/auth/company.yaml` 的角色改为
`bearer`（引用 API_TOKEN）或 `login`。不猜 Cookie/SSO/OAuth 等公司的真实协议。

以下手工接入步骤仍适用于已有的业务项目。

## 1. 第一周先完成一条稳定链路

先挑一个明确且可重复的业务，例如“测试用户登录 → 创建订单 → 查询订单 → 取消订单”。先跑接口，再为关键用户流程加 Web / App。以下清单可复制到公司的接入任务中：

| 事项 | 需要拿到的内容 | 完成标准 |
| --- | --- | --- |
| 环境 | 测试环境 URL、网络 / VPN / 证书要求 | 本机和 CI 都能访问 |
| 接口契约 | OpenAPI / 接口文档、状态码、字段、鉴权规则 | 能手工完成一条请求并知道预期 |
| 账号 | 专用测试账号、权限、租户、有效期 | 测试使用的身份可追溯 |
| 数据 | 可造数入口、唯一键、清理方式 | 同一条用例连续跑三次不冲突 |
| Web | 页面路径、稳定标签或 test id | 关键控件有可维护的定位 |
| App | APK / APP、包名、签名、设备、无障碍标识 | 手工安装并能创建 Appium 会话 |
| Android AI 探索（可选） | 独立 ARTEMIS 主机、模型许可、专用设备、数据出境规则 | check/devices 通过且探索结果可转为 Appium 定位 |
| CI | 执行节点、依赖源、Secret、报告存储 | 提交后能看到真实测试结果 |
| 负责人 | 产品预期、环境与测试代码维护人 | 遇到失败能找到相应负责人 |

## 2. 创建自己的环境文件

复制 `configs/environments/test.yaml` 为 `configs/environments/company_test.yaml`。保留当前已支持的键，只修改普通配置，例如：

```yaml
# 注意缩进使用空格，不用 Tab。地址必须带 http:// 或 https://。
api_base_url: "https://api.test.example.com"
web_base_url: "https://web.test.example.com"
timeout_seconds: 20
web_timeout_ms: 10000
```

这两个域名是示例占位，必须替换成公司的地址。密码、Token 和模型密钥写入 `.env` 或 CI Secret，不写进该文件。

```powershell
# 复制只执行一次，已有 .env 时请直接编辑，避免覆盖个人配置。
Copy-Item .env.example .env

# 在 .env 中修改 TEST_ENV=company_test，并填入需要的变量。
# 命令行也可以明确选择环境。
uv run python -m autotest run --suite api -- --env company_test
```

上面的运行方式展示环境切换；仓库中的 `demo` 业务在非 demo 环境会自动跳过。先新增一条公司的健康检查 / 只读接口用例，标记为 `api`，不加 `demo`，再执行那一条。大量 `skipped` 不能作为公司业务接入完成的证据。

## 3. 适配鉴权

### 固定测试 Token

已有合法测试 Token 时，使用 `API_TOKEN`。框架默认以 Bearer 方式加到 API 请求。不要把 Token 拼进 URL。

### 登录获取 Token

如果每次需要登录，在业务 fixture 中调用公司的登录接口，解析真实响应，再构造带 Token 的 `ApiClient`。例如下面是**需要按公司接口改写**的示意：

```python
import os

import pytest

from autotest.api.client import ApiClient


@pytest.fixture
def company_api(settings):
    # 只读取环境 / CI 的账号，不把密码写入源代码。
    username = os.environ["COMPANY_TEST_USERNAME"]
    password = os.environ["COMPANY_TEST_PASSWORD"]
    with ApiClient(settings.api_base_url) as anonymous:
        response = anonymous.post(
            "/replace-with-company-login-path",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200, "测试账号登录失败"
        # 这里字段名只是示意，替换为公司真实响应结构。
        token = response.json()["access_token"]

    # yield 前创建鉴权客户端；结束后 with 会关闭连接。
    with ApiClient(settings.api_base_url, token=token) as client:
        yield client
```

上例可放到公司业务目录的 `conftest.py`。业务 fixture 可以组合登录、造数、清理，通用客户端只管理传输。

若使用 Cookie、OAuth、签名请求或短期 Token 刷新，在业务层实现对应协议。不要把演示 Token 或演示登录接口当作公司通用鉴权方案。

## 4. 把演示页面换成公司页面

新增 `src/autotest/web/order_page.py`，将订单页面的定位器和操作放在里面。测试调用 `OrderPage` 并验证订单状态。先与研发约定稳定的 `data-testid`，减少 CSS 重构对测试的影响。

UI 测试准备复杂数据时，优先调用 API 造数；这样用例可以集中验证当前页面。只有“登录本身”是测试目标时才每次从 UI 登录；其他场景可以后续引入受控的登录状态复用，注意账号权限和会话过期。

本仓库初始 Web 示例保留直观的 UI 登录，便于新手读懂。复杂权限和多账号会话复用属于接入公司业务时的扩展。

## 5. 接入 App

先完成 [App 安装和设备配置](04-app.md)，再替换应用路径、包名 / bundle id、启动 Activity 和页面无障碍标识。

Android 与 iOS 可以共用业务场景思路，但两个平台的定位与系统弹窗经常不同。把平台差异放在页面对象 / 驱动配置中，用例尽量表达同一业务含义。真实设备或模拟器一次由一个独立会话控制。

## 6. 保留哪些，逐步替换哪些

| 可以直接保留 | 需要按业务替换 |
| --- | --- |
| pytest / uv / Ruff / 报告执行入口 | 公司环境地址、Secret 来源 |
| 配置加载与客户端基础能力 | 登录协议、签名、多租户上下文 |
| unit 测试，用于保护框架功能 | 演示 API 路径、字段、状态码 |
| 页面对象组织方式 | Web 与 App 真实页面定位 |
| CI 的步骤结构与产物归档 | CI 节点标签、私有源、设备资源 |
| AI 的离线与模型适配入口 | 允许发送的数据、公司模型地址 |

把演示业务与公司业务分目录，例如新增 `tests/company_api/` 时，先用 `python -m pytest tests/company_api` 运行；再按团队需要调整 CLI 套件映射。想继续直接使用 `--suite api`，可在 `tests/api/company/` 内新增业务测试并逐步迁出 `tests/api/` 中的演示文件。

迁出示例时不要删掉框架 `tests/unit/`。在公司仓库中保留一份 demo 运行方式，方便判断“框架坏了”还是“公司环境坏了”。

## 7. 迁移验收表

- [ ] 新电脑只依据文档与锁文件即可安装，不依赖某个人的全局 Python 包。
- [ ] 环境名、地址、账号来源明确；环境配置拼错时能尽早报错。
- [ ] 第一条接口用例与第一条 Web 用例单独执行成功。
- [ ] 关键字段故意改错时断言能失败，报告里能定位对应条件。
- [ ] 单条用例连续执行三次，数据不会互相污染。
- [ ] 开两个 worker 时账号、数据与文件名不冲突；未满足时先保持串行。
- [ ] 失败能留下报告；页面已经启动的失败能找到对应 Trace / 截图。
- [ ] 真实 Android 和 iOS 各完成至少一条明确执行的用例，跳过不算验收。
- [ ] CI 中运行的是同一份锁文件、同一组命令，失败退出码没有被吞掉。
- [ ] 另一个同事按文档新增一条用例并能解释各层职责。

## 8. 后续怎么扩展

先积累真实需求，再逐项增加：OpenAPI 生成接口模型、数据库造数、消息队列验证、云设备池、专用鉴权、业务报告分类、定时回归。每次扩展保留可独立运行的测试和使用例子。

性能测试、安全测试、视觉回归和大规模设备调度需要各自的方案，本仓库以功能自动化为基础。把核心链路稳定运行起来后再扩展，维护成本更可控。
