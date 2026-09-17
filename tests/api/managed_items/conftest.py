"""演示项目接入：复用框架角色客户端和数据登记，不共享固定业务 ID。"""

from pathlib import Path

import pytest

from autotest.api.auth import load_profile
from autotest.api.factories import ItemsFactory
from autotest.api.services import ItemsService


@pytest.fixture
def auth_profile(monkeypatch):
    # 这两个值属于仓库自带练习服务。真实项目只从 .env / CI Secret 读取。
    monkeypatch.setenv("QA_DEMO_USERNAME", "demo")
    monkeypatch.setenv("QA_DEMO_PASSWORD", "demo123")
    return load_profile(Path(__file__).resolve().parents[3] / "configs/auth/demo.yaml")


@pytest.fixture
def item_factory(role_clients, data_factory):
    service = ItemsService(role_clients("member"))
    return ItemsFactory(service, data_factory)
