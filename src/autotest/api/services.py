"""业务接口集中在 Service，接口路径变化时只需修改这里。"""

import httpx

from autotest.api.client import ApiClient


class ItemsService:
    def __init__(self, client: ApiClient):
        self.client = client

    def create(self, name: str) -> httpx.Response:
        return self.client.post("/api/items", json={"name": name})

    def get(self, item_id: str) -> httpx.Response:
        return self.client.get(f"/api/items/{item_id}")

    def delete(self, item_id: str) -> httpx.Response:
        return self.client.delete(f"/api/items/{item_id}")
