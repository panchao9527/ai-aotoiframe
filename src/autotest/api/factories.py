"""本地项目管理示例的数据工厂；真实项目按同样方式封装自己的业务 Service。"""

from autotest.api.services import ItemsService
from autotest.data import DataFactory


class ItemsFactory:
    def __init__(self, service: ItemsService, data: DataFactory):
        self.service = service
        self.data = data

    def create(self, name: str | None = None) -> dict:
        name = name if name is not None else self.data.unique("item")
        response = self.service.create(name)
        response.raise_for_status()
        item = response.json()
        item_id = item["id"]

        def remove():
            # 场景可能已删除该对象，所以 404 也是清理完成；权限/网络错误仍失败。
            deleted = self.service.delete(item_id)
            if deleted.status_code not in {204, 404}:
                raise RuntimeError(f"项目清理返回 HTTP {deleted.status_code}")

        self.data.defer("item", remove)
        # 一拿到 ID 就登记清理，后续业务断言失败仍能释放本用例资源。
        assert response.status_code == 201
        assert item["name"] == name.strip()
        return item
