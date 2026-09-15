"""完整增查删流程、JSON Schema 契约和失败路径。每个用例可独立运行。"""

import uuid

import pytest
from jsonschema import validate

from autotest.api.services import ItemsService

pytestmark = [pytest.mark.api, pytest.mark.demo]
ITEM_SCHEMA = {
    "type": "object",
    "required": ["id", "name"],
    "properties": {"id": {"type": "string", "minLength": 1}, "name": {"type": "string"}},
    "additionalProperties": False,
}


@pytest.mark.smoke
def test_create_read_delete_item(authenticated_client):
    service = ItemsService(authenticated_client)
    name = f"接口项目-{uuid.uuid4().hex[:8]}"
    response = service.create(name)
    assert response.status_code == 201
    item = response.json()
    # 得到 ID 后马上进入 finally，后续断言失败也能清理。
    try:
        validate(item, ITEM_SCHEMA)
        assert item["name"] == name
        fetched = service.get(item["id"])
        assert fetched.status_code == 200
        assert fetched.json() == item
        assert service.delete(item["id"]).status_code == 204
        assert service.get(item["id"]).status_code == 404
    finally:
        # 允许重复清理时 404；网络故障或权限错误不能默默吞掉。
        assert service.delete(item["id"]).status_code in {204, 404}


@pytest.mark.parametrize("name", ["", "   ", "x" * 81, None])
def test_invalid_name_is_rejected(authenticated_client, name):
    response = authenticated_client.post("/api/items", json={"name": name})
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_name"


def test_unauthenticated_request(api_client):
    assert api_client.get("/api/items").status_code == 401


def test_unknown_item(authenticated_client):
    response = authenticated_client.get("/api/items/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
