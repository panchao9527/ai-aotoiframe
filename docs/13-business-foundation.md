# 13 · 业务接入、数据工厂与用例依据

本轮扩展已有 pytest 工作流，重点让 AI 复用可靠的业务准备步骤，并保留断言来源。
未增加新依赖，也没有连接公司服务。以下演示使用本地 DemoServer。

## 1. 先运行完整样板

```powershell
uv run python -m pytest tests/api/managed_items --env demo -n 2
```

样板覆盖创建→查询→删除、同场景多条独立数据、匿名 GET/POST/DELETE 权限和名称边界。
`tests/api/managed_items/conftest.py` 接入角色与 ItemsFactory；测试函数保留业务断言。
已知的公开 demo 凭据只由该目录 fixture 注入，其他环境不会运行这些 demo 用例。

## 2. 项目接入与角色鉴权

沿用 `configs/environments/<环境>.yaml` 管理 API 地址与超时，增加可选配置：

```yaml
api_base_url: https://your-test-host.example.com/service
api_auth_file: configs/auth/example.yaml
```

鉴权配置只引用环境变量名称，实际值来自 `.env` 或 CI Secret。
复制 `configs/auth/example.yaml` 后，按真实接口设置角色、登录路径、凭据字段、响应字段：

```yaml
default_role: operator
roles:
  operator:
    mode: login
    login_path: /api/login
    credentials_env:
      username: TEST_OPERATOR_USERNAME
      password: TEST_OPERATOR_PASSWORD
    token_field: data.accessToken
    success_fields:
      code: 0
  reader:
    mode: bearer
    token_env: TEST_READER_TOKEN
  anonymous:
    mode: none
```

`token_field` 和 `success_fields` 支持以点分隔的 JSON 对象路径，不支持数组索引或字段名
本身含点的协议。若服务没有业务码就不配置 `success_fields`，不能为了通过而猜一个成功码。
`headers_env` 支持租户等额外请求头，值仍引用环境变量；鉴权头、Cookie、Host 等不可覆盖。

```powershell
# 检查全部角色；只测试部分角色时可以重复指定 --role。
uv run qa project check --env test
uv run qa project check --env test --role operator --role anonymous
```

预检只检查地址、配置结构和非空环境变量，不代表服务可访问或账号权限有效。
配置路径相对项目根目录。`api_auth_file` 也可由 `API_AUTH_FILE` 覆盖，优先级沿用现有配置。

```python
def test_permission(role_clients):
    operator = role_clients("operator")
    guest = role_clients("anonymous")
    response = guest.get("/api/items")
    assert response.status_code == 401
```

同一用例、同一角色复用客户端；不同角色和用例独立 Cookie/Token。JSON 登录只执行一次，
登录失败不运行后续步骤，401 不触发自动刷新或写请求重放。初始化登录消除跨测试 Token
缓存失效问题，但超长场景内的 Token 刷新、SSO、签名鉴权、Cookie 登录仍需项目 fixture 实现。
未配置新能力的旧用例继续使用 `api_client` / `API_TOKEN`。

## 3. 数据工厂负责创建和登记，框架负责清理

`ItemsFactory` 是业务工厂示例。真实项目可以实现自己的订单、账单等工厂，复用同一个
`data_factory` fixture。不要把公司领域逻辑写进 DataFactory 底层类。

```python
def test_item(item_factory, role_clients):
    item = item_factory.create()  # 唯一名称、API 创建、立即登记清理
    response = role_clients("member").get(f"/api/items/{item['id']}")
    assert response.status_code == 200
    assert response.json() == item
```

自定义工厂在拿到资源 ID 后立即调用 `data_factory.defer("资源类型", 清理回调)`，随后再
进行业务断言。先登记主记录、再登记明细，清理时按相反顺序执行。回调必须检查响应，
不能把返回 HTTP 500 当作清理成功；仅在业务允许重复删除时接受 404。

每次运行在 `artifacts/<运行>/data-cleanup/*.json` 留下用例与清理结果。清理失败继续处理
其他资源，并作为 teardown 错误单独报告，不覆盖原始断言失败。结果仅保存标签、状态和
异常类型；标签不要填写敏感业务数据。资源归属由工厂保证，不允许按模糊条件批量删除。

`data_factory` 明确依赖 `role_clients`，因此这些客户端会在资源清理后关闭。自定义数据库
或其他客户端也必须保证在清理回调运行时仍有效。框架不保证进程被终止后的清理，也不保证
服务创建了资源却没有返回可识别 ID 时能自动找回；这些需要业务可控的补偿机制。

## 4. AI 草稿记录预期来源

新建 author 任务生成的每个测试函数都需要以下字面量标记：

```python
@pytest.mark.case(
    id="ITEM-CREATE-001",
    purpose="验证创建后能查询到本条记录",
    expected="POST 返回 201，GET 返回 200 且名称与本次输入一致",
    basis="requirement",
    source="requirement",
)
def test_create_item(item_factory, role_clients):
    item = item_factory.create()
    response = role_clients("member").get(f"/api/items/{item['id']}")
    assert response.status_code == 200
    assert response.json() == item
```

示例复用本地样板的 fixture。`source` 必须是本次 `context.json`
中 `materials` 的键，`basis` 必须匹配来源类型：

| basis | source 示例 | 含义 |
| --- | --- | --- |
| requirement | requirement | 已提供的需求材料 |
| contract | openapi | 已选定的接口契约 |
| source | source-1/Controller.java | 本次提供的源码实现行为 |
| observation | observation / recording | 已提供的页面观察或录制事实 |

源码行为和录制事实不自动成为业务认可的预期。只有源码时如实标记为实现回归；缺失规则
仍写入 `unresolved`，可把依赖该规则的接口移出本次范围，继续处理其余接口。

静态验证检查遗漏、未知来源、来源类型不匹配、任务内重复 ID、材料快照被改动等问题。
这些检查不能证明自然语言预期与断言语义一致，仍需审查具体断言。

入库后 `tests/<kind>/case_records/<任务>.json` 保存测试路径、用例信息和材料 SHA-256。
散列对应本次脱敏输入快照，不是部署版本证明；框架不会自动监听外部 Java 仓库变化。
材料变化后重新 prepare。编号建议加业务模块前缀；当前只检查任务内重复，不是全库注册表。
历史 schema v1 草稿保持兼容，不会自动生成不存在的来源记录。

## 5. 后续建设边界

本轮没有实现 Swagger 变更影响分析、自动修改已有用例、跨运行 flaky 统计、视觉回归、
多设备调度或完整 DLP。公司项目的真实登录、数据工厂和预期仍需依据对应源码接入验证；
本地演示与框架单测通过不能替代这一步。

## 6. 本轮验证记录（2026-09-17）

在 Windows / Python 3.11 执行：

```powershell
uv run python -m autotest run --suite all -- --env demo -n 2
uv run ruff check .
uv run ruff format --check .
git diff --check
```

完整结果为 **188 passed, 1 skipped**：框架单测 163 条、API 本地业务 20 条、Web 真实
Chromium 5 条；App 1 条因未配置设备跳过。报告目录为
`artifacts/20260917-012027-11eabc/`。新样板产生 5 份清理报告，6 个创建资源全部清理完成。
Ruff、格式和差异检查通过。本轮没有修改依赖或锁文件。

另外用预期失败的子进程验证业务断言失败与清理失败同时保留，且其他资源继续清理；
鉴权测试覆盖缺少凭据、业务码错误、错误 Token 类型/字符、角色 Cookie 隔离与不重放请求；
AI 工作流验证新依据记录入库、材料变化失效和历史协议兼容。

这些是本地框架与演示系统证据。本轮未运行公司环境、真实 App 设备或远端 CI，
也没有向外部模型发送公司材料。
