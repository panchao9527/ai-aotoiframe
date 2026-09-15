"""UI 创建后用 API 核对和清理，演示接口与 Web 联动。"""

import uuid

import pytest
from playwright.sync_api import expect

from autotest.web.pages import ItemsPage, LoginPage

pytestmark = [pytest.mark.web, pytest.mark.demo]


def test_create_item_in_browser(page, base_url):
    login = LoginPage(page)
    login.open(base_url)
    login.login("demo", "demo123")
    items = ItemsPage(page)
    expect(items.heading).to_be_visible()
    name = "Web项目-" + uuid.uuid4().hex[:10]
    try:
        # 先等待创建请求完成，再开始断言；finally 能清理刚创建的数据。
        with page.expect_response(
            lambda response: (
                response.url.endswith("/api/items") and response.request.method == "POST"
            )
        ) as created:
            items.create(name)
        assert created.value.status == 201
        expect(items.item(name)).to_be_visible()
        # context.request 共享浏览器 Cookie，可以直接调用同一用户的接口。
        response = page.context.request.get(base_url + "/api/items")
        assert response.status == 200
        assert any(item["name"] == name for item in response.json()["items"])
    finally:
        response = page.context.request.get(base_url + "/api/items")
        assert response.status == 200
        for item in response.json()["items"]:
            if item["name"] == name:
                cleaned = page.context.request.delete(base_url + "/api/items/" + item["id"])
                assert cleaned.status in {204, 404}
