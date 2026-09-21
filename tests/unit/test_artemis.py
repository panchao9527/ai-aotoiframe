"""ARTEMIS 仅测试远程客户端边界，不连接设备、不调用模型。"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from autotest.config import Settings
from autotest.mobile import artemis

pytestmark = pytest.mark.unit


class FakeResult:
    task_id = "task-1"
    status = "completed"
    succeeded = True
    profile = "pro"
    device_serial = "emulator-5554"
    turns = 4
    output = {"summary": "done", "password": "private-result"}
    error = None


class FakeClient:
    def __init__(self):
        self.calls = []

    async def health(self):
        return {"status": "ok", "token": "private-health"}

    async def readiness(self):
        return {"verdict": "ready"}

    async def list_devices(self):
        return (
            SimpleNamespace(
                serial="emulator-5554", state="device", model="Pixel", product="sdk", busy=False
            ),
        )

    async def run(self, goal, **kwargs):
        self.calls.append((goal, kwargs))
        return FakeResult()


def args(action, **overrides):
    defaults = {
        "action": action,
        "deep": False,
        "profile": None,
        "device": None,
        "allow_auto_device": False,
        "package": None,
        "allow_cross_app": False,
        "verification_level": None,
        "explorer_mode": None,
        "expected_output": None,
        "timeout": None,
        "goal_file": "goal.md",
        "dry_run": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def settings(**overrides):
    values = {
        "env": "test",
        "artemis_base_url": "http://127.0.0.1:8000",
        "artemis_device_serial": "emulator-5554",
        "artemis_profile": "flash",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    "url",
    [
        "http://device-host:8000",
        "ftp://127.0.0.1:8000",
        "https://user:pass@device-host",
        "https://device-host?token=x",
    ],
)
def test_artemis_url_rejects_insecure_or_embedded_credentials(url):
    with pytest.raises(ValidationError):
        Settings(artemis_base_url=url)


def test_client_requires_optional_extra(monkeypatch):
    import builtins

    original = builtins.__import__

    def missing(name, *values, **kwargs):
        if name == "artemis_client":
            raise ImportError("missing")
        return original(name, *values, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(RuntimeError, match="--extra artemis"):
        artemis.client_class()


def test_health_and_device_listing_are_read_only(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(artemis, "make_client", lambda current: client)
    code, health = asyncio.run(artemis.execute(args("check"), settings()))
    assert code == 0 and health["result"]["token"] == "[REDACTED]"
    code, devices = asyncio.run(artemis.execute(args("devices"), settings()))
    assert code == 0 and devices["devices"][0]["serial"] == "emulator-5554"
    assert not client.calls


def test_run_requires_explicit_device_and_app_scope(monkeypatch):
    monkeypatch.setattr(artemis, "make_client", lambda current: FakeClient())
    no_device = settings(artemis_device_serial=None)
    with pytest.raises(ValueError, match="指定测试设备"):
        asyncio.run(artemis.execute(args("run", package="com.example"), no_device))
    with pytest.raises(ValueError, match="限定被测 App"):
        asyncio.run(artemis.execute(args("run"), settings()))


def test_flash_rejects_pro_only_options(monkeypatch):
    monkeypatch.setattr(artemis, "make_client", lambda current: FakeClient())
    with pytest.raises(ValueError, match="仅适用于 pro"):
        asyncio.run(
            artemis.execute(
                args("run", package="com.example", verification_level="strict"), settings()
            )
        )


def test_run_saves_redacted_authoring_material(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    goal = tmp_path / "goal.md"
    goal.write_text("打开测试应用并确认首页标题", encoding="utf-8")
    client = FakeClient()
    monkeypatch.setattr(artemis, "make_client", lambda current: client)
    command = args(
        "run",
        goal_file=str(goal),
        package="com.example.test",
        profile="pro",
        verification_level="strict",
        explorer_mode="pro",
        expected_output="首页证据",
        timeout=30,
    )
    code, payload = asyncio.run(artemis.execute(command, settings()))
    assert code == 0 and payload["succeeded"]
    assert client.calls == [
        (
            "打开测试应用并确认首页标题",
            {
                "profile": "pro",
                "device_serial": "emulator-5554",
                "expected_output": "首页证据",
                "locked_app_package": "com.example.test",
                "verification_level": "strict",
                "explorer_mode": "pro",
                "timeout": 30,
            },
        )
    ]
    saved = Path(payload["artifact"])
    content = saved.read_text(encoding="utf-8")
    assert "private-result" not in content
    assert json.loads(content)["output"]["password"] == "[REDACTED]"


def test_dry_run_does_not_load_optional_client_or_send_goal(tmp_path, monkeypatch):
    goal = tmp_path / "goal.md"
    goal.write_text("检查首页", encoding="utf-8")
    monkeypatch.setattr(
        artemis, "make_client", lambda current: pytest.fail("dry-run 不应创建远程客户端")
    )
    code, payload = asyncio.run(
        artemis.execute(
            args(
                "run",
                goal_file=str(goal),
                package="com.example.test",
                dry_run=True,
                allow_auto_device=True,
            ),
            settings(artemis_device_serial="configured-device"),
        )
    )
    assert code == 0 and payload["dry_run"]
    assert payload["auto_device"] and payload["device_serial"] is None
    assert len(payload["goal_sha256"]) == 64
    assert "检查首页" not in json.dumps(payload, ensure_ascii=False)


@pytest.mark.parametrize("package", ["example", "com..app", "1com.example", "com.exa-mple"])
def test_invalid_android_package_is_rejected(tmp_path, monkeypatch, package):
    goal = tmp_path / "goal.md"
    goal.write_text("检查首页", encoding="utf-8")
    monkeypatch.setattr(artemis, "make_client", lambda current: FakeClient())
    with pytest.raises(ValueError, match="applicationId"):
        asyncio.run(artemis.execute(args("run", goal_file=str(goal), package=package), settings()))


def test_goal_file_boundaries(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="不能为空"):
        artemis.read_goal(str(empty))
    large = tmp_path / "large.md"
    large.write_bytes(b"x" * (artemis.MAX_GOAL_BYTES + 1))
    with pytest.raises(ValueError, match="64 KiB"):
        artemis.read_goal(str(large))
