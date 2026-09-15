# API 用例需求：本仓库练习服务

请使用 `api_client` fixture 生成两个独立的 pytest 用例。
这些是本仓库 demo 服务的约定；只用于 demo 环境，增加 `pytest.mark.demo` 和 `pytest.mark.api`。

1. GET `/health` 返回 HTTP 200，JSON 为 `{"status": "ok"}`。
2. 全新、没有登录过的 `api_client` 请求 GET `/api/items`，返回 HTTP 401，JSON 为 `{"error": "unauthorized"}`。

每个用例单独获取函数级 fixture，断言状态码、JSON 类型和关键业务字段。
这两个查询不会创建数据，不需要清理。
不要自行登录，不需要真实账号，不要设置公司接口地址。
