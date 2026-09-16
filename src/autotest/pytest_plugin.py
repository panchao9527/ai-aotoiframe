"""pytest 扩展：环境、可复用 fixture、失败证据与并行隔离。

fixture 的 yield 前负责准备，yield 后负责清理；测试失败也会执行清理。
浏览器生命周期交给官方 pytest-playwright 插件管理。
"""

import base64
import hashlib
import json
import logging
import re
import uuid
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pytest
from playwright.sync_api import expect

from autotest.api.client import ApiClient
from autotest.config import Settings, load_settings
from autotest.demo import DemoServer
from autotest.evidence import BrowserEvidence
from autotest.execution import ExecutionTracker
from autotest.redaction import redact

SETTINGS_KEY = pytest.StashKey[Settings]()
ARTIFACTS_KEY = pytest.StashKey[Path]()
BROWSER_EVIDENCE_KEY = pytest.StashKey[BrowserEvidence]()


def pytest_addoption(parser):
    group = parser.getgroup("automation", "自动化框架设置")
    group.addoption("--env", default=None, help="configs/environments 下的环境名")
    group.addoption("--config-dir", default="configs/environments", help="环境 YAML 目录")
    group.addoption("--artifact-dir", default=None, help="本次失败证据目录")
    group.addoption("--require-business", action="store_true", help="目标业务无实际执行时失败")
    group.addoption("--business-kind", choices=("all", "api", "web", "app"), default="all")


def pytest_configure(config):
    try:
        config.stash[SETTINGS_KEY] = load_settings(
            config.getoption("env"), config.getoption("config_dir")
        )
    except (ValueError, OSError) as exc:
        raise pytest.UsageError(f"配置错误：{redact(str(exc))}") from None
    worker = getattr(config, "workerinput", {})
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    path = worker.get("qa_artifacts") or config.getoption("artifact_dir") or f"artifacts/{stamp}"
    config.stash[ARTIFACTS_KEY] = Path(path).resolve()
    config.stash[ARTIFACTS_KEY].mkdir(parents=True, exist_ok=True)
    config.pluginmanager.register(
        ExecutionTracker(config, config.stash[ARTIFACTS_KEY]), "execution-tracker"
    )
    config.addinivalue_line("markers", "demo: 仅适用于自带练习系统的业务示例")
    # HTTPX 默认 INFO 包含 URL；公司项目 URL 可能携带敏感查询参数。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node):
    """控制进程把同一个报告根目录传给 xdist worker，文件名仍按用例隔离。"""
    node.workerinput["qa_artifacts"] = str(node.config.stash[ARTIFACTS_KEY])


def pytest_collection_modifyitems(config, items):
    if config.stash[SETTINGS_KEY].env != "demo":
        marker = pytest.mark.skip(reason="本地练习示例只在 --env demo 运行；请编写项目业务用例")
        for item in items:
            if item.get_closest_marker("demo"):
                item.add_marker(marker)


@pytest.hookimpl(optionalhook=True)
def pytest_html_report_title(report):
    report.title = "自动化测试报告 · API / Web / App"


@pytest.fixture(scope="session")
def settings(pytestconfig) -> Settings:
    return pytestconfig.stash[SETTINGS_KEY]


@pytest.fixture(scope="session")
def demo_server():
    """只有请求 demo 的用例才会启动服务，不需要用户预先开一个终端。"""
    with DemoServer() as server:
        yield server


def _base_url(settings, request, field):
    configured = getattr(settings, field)
    if configured:
        return configured
    if settings.env == "demo":
        return request.getfixturevalue("demo_server").base_url
    raise pytest.UsageError(f"请在 .env 设置 {field.upper()} 或在环境 YAML 填写 {field}")


@pytest.fixture(scope="session")
def api_base_url(settings, request):
    return _base_url(settings, request, "api_base_url")


@pytest.fixture(scope="session")
def base_url(settings, request):
    """覆盖 pytest-base-url 的 fixture；也可直接传给 page.goto。"""
    return _base_url(settings, request, "web_base_url")


@pytest.fixture
def api_client(settings, api_base_url):
    with ApiClient(
        api_base_url, token=settings.api_token, timeout=settings.timeout_seconds
    ) as client:
        yield client


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, settings):
    return {**browser_context_args, "locale": "zh-CN", "timezone_id": "Asia/Shanghai"}


@pytest.fixture
def page(page, settings, request):
    """沿用官方隔离 page fixture，仅统一动作/断言超时。"""
    page.set_default_timeout(settings.web_timeout_ms)
    page.set_default_navigation_timeout(settings.web_timeout_ms)
    expect.set_options(timeout=settings.web_timeout_ms)
    request.node.stash[BROWSER_EVIDENCE_KEY] = BrowserEvidence(page)
    return page


def _evidence_dir(item) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", item.name)[:60]
    digest = hashlib.sha256(item.nodeid.encode()).hexdigest()[:12]
    worker = getattr(item.config, "workerinput", {}).get("workerid", "main")
    path = item.config.stash[ARTIFACTS_KEY] / "failures" / f"{safe}-{digest}-{worker}"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """在驱动清理前保留证据；附件出错也不能覆盖真正的测试失败。"""
    outcome = yield
    report = outcome.get_result()
    if not report.failed:
        return
    try:
        path = _evidence_dir(item)
        evidence = {
            "nodeid": item.nodeid,
            "phase": report.when,
            "environment": item.config.stash[SETTINGS_KEY].env,
            "error": report.longreprtext,
            "artifacts": [],
            "capture_errors": [],
        }
        browser_evidence = item.stash.get(BROWSER_EVIDENCE_KEY, None)
        if browser_evidence is not None:
            evidence["browser_events"] = list(browser_evidence.events)
        client = item.funcargs.get("api_client")
        if client is not None:
            evidence["api_events"] = list(client.events)
        page_instance = item.funcargs.get("page")
        driver = item.funcargs.get("app_driver")
        if report.when != "teardown" and page_instance and not page_instance.is_closed():
            try:
                page_instance.screenshot(path=str(path / "web.png"), full_page=True, timeout=5000)
                evidence["artifacts"].append("web.png")
            except Exception as exc:
                evidence["capture_errors"].append(f"Web 截图失败：{exc}")
        if report.when != "teardown" and driver is not None:
            try:
                if driver.get_screenshot_as_file(str(path / "app.png")):
                    evidence["artifacts"].append("app.png")
            except Exception as exc:
                evidence["capture_errors"].append(f"App 截图失败：{exc}")
            try:
                # XML 可能包含界面敏感数据，报告仅本地保存，不会自动发送给 AI。
                (path / "app.xml").write_text(driver.page_source, encoding="utf-8")
                evidence["artifacts"].append("app.xml")
            except Exception as exc:
                evidence["capture_errors"].append(f"App 页面结构获取失败：{exc}")
        target = path / f"{report.when}.json"
        summary = json.dumps(redact(evidence), ensure_ascii=False, indent=2)
        target.write_text(summary, encoding="utf-8")
        # JSON 脱敏后才作为附件；图片可能含业务数据，分享报告前需检查。
        import allure
        from pytest_html import extras

        allure.attach.file(
            str(target), name=f"失败证据-{report.when}", attachment_type=allure.attachment_type.JSON
        )
        report.extras = [*getattr(report, "extras", []), extras.text(summary, name="失败摘要")]
        for filename in evidence["artifacts"]:
            if filename.endswith(".png"):
                image_file = path / filename
                # 内嵌 base64：复制单个自包含 HTML 到另一台电脑仍能查看截图。
                encoded = base64.b64encode(image_file.read_bytes()).decode("ascii")
                report.extras.append(extras.png(encoded, name=filename))
                allure.attach.file(
                    str(image_file), name=filename, attachment_type=allure.attachment_type.PNG
                )
    except Exception as exc:
        warnings.warn(f"失败证据保存失败（原始测试结果保留）：{redact(str(exc))}", stacklevel=1)
