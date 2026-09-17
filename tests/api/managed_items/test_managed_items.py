"""数据工厂、角色隔离和业务断言的真实本地 HTTP 样板；不代表公司接口验收。"""

import pytest

from autotest.api.services import ItemsService

pytestmark = [pytest.mark.api, pytest.mark.demo]


@pytest.mark.case(
    id="ITEMS-LIFECYCLE",
    purpose="验证创建查询删除场景",
    expected="查询内容一致，删除后 404",
    basis="requirement",
    source="examples/authoring/api-requirement.md",
)
def test_lifecycle(item_factory, role_clients):
    item = item_factory.create()
    service = ItemsService(role_clients("member"))
    response = service.get(item["id"])
    assert response.status_code == 200
    assert response.json() == item
    assert service.delete(item["id"]).status_code == 204
    assert service.get(item["id"]).status_code == 404
    # 用例已删除资源，fixture 再清理也可接受 404。


@pytest.mark.case(
    id="ITEMS-INDEPENDENT",
    purpose="一次场景准备多条独立数据",
    expected="名称和 ID 均不重复",
    basis="source",
    source="src/autotest/demo.py",
)
def test_factory_creates_independent_resources(item_factory):
    first, second = item_factory.create(), item_factory.create()
    assert first["id"] != second["id"]
    assert first["name"] != second["name"]


@pytest.mark.case(
    id="ITEMS-ANONYMOUS",
    purpose="匿名角色不能操作已创建数据",
    expected="读写删除均返回 401",
    basis="source",
    source="src/autotest/demo.py",
)
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_anonymous_has_no_member_session(item_factory, role_clients, method):
    item = item_factory.create()
    anonymous = role_clients("anonymous")
    path = "/api/items" if method == "POST" else f"/api/items/{item['id']}"
    response = anonymous.request(method, path, json={"name": "forbidden"})
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert ItemsService(role_clients("member")).get(item["id"]).json() == item


@pytest.mark.case(
    id="ITEMS-BOUNDARY",
    purpose="校验项目名称输入边界",
    expected="不合法名称返回 422/invalid_name",
    basis="source",
    source="src/autotest/demo.py",
)
@pytest.mark.parametrize("name", ["", "   ", "x" * 81, None])
def test_invalid_name(role_clients, name):
    response = ItemsService(role_clients()).create(name)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_name"}
