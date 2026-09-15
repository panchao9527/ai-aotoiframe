# 03 · 从第一个用例到独立编写

## 1. pytest 怎么找到我的用例

遵守两个命名规则：文件名以 `test_` 开头，测试函数名也以 `test_` 开头。例如 `tests/api/test_orders.py` 中的 `def test_create_order(...)`。每条用例只验证一个明确场景。

```powershell
# 查看测试集合。
uv run python -m pytest tests/api --collect-only -q

# 运行一个文件；保持完整报告输出。
uv run python -m autotest run --suite api -- -k login

# 精确执行某个函数：先从 --collect-only 输出复制 node id。
uv run python -m pytest tests/api/test_orders.py::test_create_order -v
```

最后一条是你新增订单用例后的写法；初始仓库没有该业务文件。`-k login` 表示筛选名字包含 `login` 的用例。

## 2. 先读懂 AAA

AAA 是三个英文单词的首字母：Arrange 准备、Act 操作、Assert 断言。三段结构让你很容易看出失败的是哪一步。

下面是可以复制到 `tests/api/test_health_extra.py` 的完整示例：

```python
import pytest


@pytest.mark.api  # 标记测试类别，后续可用 -m api 筛选。
@pytest.mark.demo  # 这是本地练习服务的场景；切到公司环境会跳过。
def test_health_status(api_client):
    """验证服务可访问。api_client 由 fixture 自动注入。"""
    # Arrange：准备请求路径；客户端的地址已由环境配置提供。
    path = "/health"

    # Act：真正发出请求，返回 HTTPX Response 对象。
    response = api_client.get(path)

    # Assert：比较实际状态码与预期状态码。
    assert response.status_code == 200
```

运行 `uv run python -m autotest run --suite api -- -k health_status`。`assert` 后面的表达式为假时，pytest 把这条用例记录为失败。不要写 `try/except: pass` 吞掉异常。

## 3. 请求、鉴权与负向场景

```python
import pytest


@pytest.mark.api
@pytest.mark.demo
def test_wrong_password_is_rejected(api_client):
    # json= 会序列化字典并设置 JSON Content-Type。
    response = api_client.post(
        "/api/login",
        json={"username": "demo", "password": "wrong-password"},
    )
    # 负向测试预期失败响应，这是业务断言成功的条件。
    assert response.status_code == 401
```

客户端不自动把 4xx 当作 Python 异常抛出，因此你可以验证错误响应。它也不自动重试创建、删除请求；重试 POST 可能重复创建订单。

通用 Bearer Token 可以来自 `API_TOKEN`，客户端会统一设置 `Authorization` 请求头。演示登录接口返回的 Token 只适用于演示系统；公司的 Cookie、OAuth、签名或多租户身份，需要在公司业务 fixture / 服务对象中实现。Token 和 Cookie 不应写入参数化 YAML 或断言提示。

`api_client.raw_client` 保留 HTTPX 原生能力，例如 `raw_client.headers`、Cookie、文件上传。不要把高级需求强行编码成难维护的 YAML 指令语言。

## 4. 参数化：一套步骤，多个输入

当测试步骤相同、输入和预期不同，使用 `pytest.mark.parametrize`：

```python
import pytest


@pytest.mark.api
@pytest.mark.demo
@pytest.mark.parametrize(
    ("username", "password", "expected_status"),
    [
        pytest.param("demo", "demo123", 200, id="valid-credentials"),
        pytest.param("demo", "wrong-password", 401, id="wrong-password"),
        pytest.param("unknown-user", "demo123", 401, id="unknown-user"),
    ],
)
def test_login_matrix(api_client, username, password, expected_status):
    """每组数据是一条独立用例，报告会显示上面的 id。"""
    response = api_client.post(
        "/api/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == expected_status
```

这里 `api_client` 来自 fixture；另外三个参数来自参数化数据。二者能一起使用。

数据较多时参照仓库的 `tests/data/login_cases.yaml` 示例，使用 `yaml.safe_load()` 读取，并明确字段结构。少量简单数据直接留在 Python 中更容易跳转和重构。YAML 适合“输入和预期”，不要把复杂循环、条件、断言逻辑都塞进去。

## 5. 不只断言 200

HTTP 200 只能说明请求按 HTTP 层面的成功响应返回，不保证返回的业务数据正确。按接口契约分三步验证：

1. **传输层**：状态码和必要响应头。
2. **结构层**：字段是否存在、类型是否正确，必要时使用 JSON Schema。
3. **业务层**：创建后的名称、金额、状态、权限范围是否符合预期。

下面是结构校验的独立原理示例，Schema 应来自你项目的真实接口契约：

```python
from jsonschema import validate


def test_schema_example():
    body = {"name": "学习项目", "enabled": True}
    schema = {
        "type": "object",
        "required": ["name", "enabled"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "enabled": {"type": "boolean"},
        },
    }
    validate(instance=body, schema=schema)  # 字段不符合时抛异常，测试失败。
    assert body["name"] == "学习项目"  # 业务断言仍然需要单独写。
```

项目创建 / 查询 / 删除的完整接口示例在 `tests/api/`；共用路径封装在 `src/autotest/api/services.py` 的 `ItemsService`。公司接口改路径时修改 Service，业务规则变化时修改测试。

## 6. Web：页面对象与业务断言

下面使用仓库已提供的两个页面对象：

```python
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from autotest.web.pages import ItemsPage, LoginPage


@pytest.mark.web
@pytest.mark.demo
def test_user_can_create_item(page, base_url):
    # Arrange：浏览器页面由 page fixture 提供，每条用例独立 Cookie。
    login = LoginPage(page)
    login.open(base_url)
    login.login("demo", "demo123")
    items = ItemsPage(page)
    expect(items.heading).to_be_visible()  # 等待登录后的页面状态。
    name = f"学习项目-{uuid4().hex[:8]}"  # 减少重名造成的测试干扰。

    # Act：页面对象负责具体填哪里、点哪个按钮。
    items.create(name)

    # Assert：业务规则写在测试中；expect 会在超时时间内自动重试检查。
    expect(items.item(name)).to_be_visible()
```

演示服务每次运行结束后清空内存。迁移到持久化的公司环境时，应补充 fixture / API 清理，不能只创建不删除。

推荐定位顺序：

```python
# 可读的语义定位：按钮角色与可访问名称。
page.get_by_role("button", name="创建项目")

# 表单标签，要求产品的 label 与 input 正确关联。
page.get_by_label("项目名称")

# 与研发约定的稳定测试属性：data-testid="item-name"。
page.get_by_test_id("item-name")
```

`expect(locator).to_be_visible()` 会等待元素满足条件；`time.sleep(5)` 无论页面是否完成都等 5 秒，环境慢时仍然可能失败。优先等具体状态，必要时等特定响应，不默认使用 `networkidle` 代表业务就绪。[Playwright 官方定位说明](https://playwright.dev/python/docs/locators)

## 7. iframe：先找到框架，再找里面的元素

iframe 内部是另一个文档，不能总用外层 `page.get_by_*` 直接定位。下面是原理示例，选择器和 URL 要以你实际页面为准：

```python
from playwright.sync_api import expect


def verify_embedded_form(page):
    # 页面上如果有 <iframe id="payment-frame">，先进入这个 frame。
    frame = page.frame_locator("#payment-frame")
    # 后续定位在 iframe 内部执行。
    frame.get_by_label("付款备注").fill("自动化练习")
    expect(frame.get_by_label("付款备注")).to_have_value("自动化练习")
```

`tests/web/` 中包含本地演示的 iframe 用例，先运行那个已实现的版本，再把定位替换为公司页面。不要把上面的付款表单原理示例当作仓库实际页面。

## 8. 快速创建骨架

### 使用 Playwright 录制初稿

第一次写 Web 用例时，也可以使用 Playwright 自带录制器。先在一个终端运行
`uv run python -m autotest demo --port 8765`，再在另一个终端运行：

```powershell
uv run python -m playwright codegen --target python-pytest http://127.0.0.1:8765
```

在打开的浏览器中手工操作，录制器会生成 Python 草稿。把稳定定位收进 Page Object，
补上业务断言、测试数据准备与清理，再保存进 `tests/web/`。录制步骤不等于完整测试。

### 创建项目用例模板

```powershell
uv run python -m autotest new --kind api --name order --output tests/api/test_order.py
uv run python -m autotest new --kind web --name checkout --output tests/web/test_checkout.py
uv run python -m autotest new --kind app --name profile --output tests/app/test_profile.py
```

模板用于减少重复输入，生成后必须补充真实准备、操作、断言和清理。占位失败提示应保留到业务已实现；不能改成 `assert True` 伪造完成。生成到正式 `tests/` 后它会被收集，未实现时会导致相应执行失败。

## 9. 给测试加分组

项目已注册 `api`、`web`、`app`、`unit`、`smoke`、`regression`，插件另注册 `demo` 标记。演示业务标记为 `demo`，公司用例不要加这个标记。关键链路加 `@pytest.mark.smoke` 后可用：

```powershell
uv run python -m autotest run --suite all -- -m smoke
```

新增标记也要在 `pyproject.toml` 的 `markers` 列表注册；严格模式会把拼错的标记当作错误，避免以为选到了测试却实际没有选到。

## 10. 新用例提交前检查

- 单独运行能成功，不依赖前一条测试。
- 断言验证真实结果；故意改错预期时确实失败。
- 失败信息能指出哪个业务条件不满足，且没有直接输出秘密数据。
- 创建的业务数据能清理，重复运行不会被第一次运行影响。
- Web 没有依靠固定睡眠；定位集中到页面对象。
- 用 `uv run ruff check .` 和 `uv run ruff format --check .` 检查格式与常见错误。

下一步：[App 接入](04-app.md) 或 [迁移到公司项目](06-new-project.md)。
