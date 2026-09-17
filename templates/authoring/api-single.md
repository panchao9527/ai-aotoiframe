# 单接口生成契约

先从 OpenAPI 找到操作，从后端代码确认校验与权限分支，从需求确定预期。
为每个场景记录：依据、前置数据、请求变化、HTTP/业务码、关键字段、清理方式。
文档、源码、需求冲突进入 unresolved；未提供的枚举值、账号权限不能猜测。

- Service 复用 ApiClient，只封装业务请求，不隐藏响应、不自动重试写操作。
- 参数化正常、必填、类型、边界和明确的权限场景，避免生成同义重复用例。
- 断言包括契约指定状态码和业务字段；HTTP 200 不是通用成功标准。
- 新 fixture 放 tests/api/<name>/conftest.py，账号从配置/环境取，数据动态创建。
- 用 yield/finally 清理本条用例创建的数据，保留主失败和清理失败各自证据。
- 测试使用 pytest.mark.api；本地练习才加 demo。
- 优先复用 role_clients("角色") 与业务工厂。用 data_factory.defer 登记清理，
  必须在拿到资源 ID 后立即登记，再做业务断言；只清理本用例创建的资源。
- 每个测试函数加 pytest.mark.case 的 id/purpose/expected/basis/source。
  source 使用 context.materials 的键；仅依据源码时 basis="source"，不能写成需求验收。

参考 tests/api/test_login.py、tests/api/test_items.py、autotest.api.services.ItemsService。
对象已存在时 import 复用；确需新对象放 src/autotest/api/<业务名>.py。
