"""公司登录态在浏览器上下文创建前校验，不把 Cookie/Token 放入错误信息。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from autotest.config import Settings, load_web_storage_state
from autotest.pytest_plugin import browser_context_args

pytestmark = pytest.mark.unit


@pytest.fixture
def state():
    return {
        "cookies": [
            {
                "name": "session",
                "value": "private-session-value",
                "domain": "web.internal",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }
        ],
        "origins": [
            {
                "origin": "https://web.internal",
                "localStorage": [{"name": "access", "value": "private-access-value"}],
                "indexedDB": [],
            }
        ],
    }


def test_storage_state_is_applied_as_path_without_disabling_tls(tmp_path, state):
    path = tmp_path / "storage-state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    args = browser_context_args.__wrapped__(
        {"viewport": {"width": 1280, "height": 720}},
        Settings(web_storage_state=str(path), api_ca_bundle="company.pem"),
    )
    assert args["storage_state"] == str(path)
    assert args["viewport"] == {"width": 1280, "height": 720}
    assert not args.get("ignore_https_errors", False)
    assert "private-session-value" not in repr(args)
    assert "private-access-value" not in repr(args)
    assert load_web_storage_state(str(path)) == state


def test_storage_state_unset_keeps_project_fixture_options():
    args = browser_context_args.__wrapped__({"storage_state": "project-login.json"}, Settings())
    assert args["storage_state"] == "project-login.json"


@pytest.mark.parametrize(
    "content",
    [
        None,
        "private-invalid-json",
        "[]",
        '{"cookies": "private-value", "origins": []}',
        '{"cookies": [{"value": "private-value"}], "origins": []}',
        '{"cookies": [], "origins": [{"origin": "https://web.internal"}]}',
    ],
)
def test_invalid_state_fails_before_context_with_no_secret_in_error(tmp_path, content):
    path = tmp_path / "storage-state.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="WEB_STORAGE_STATE") as error:
        browser_context_args.__wrapped__({}, Settings(web_storage_state=str(path)))
    assert "private" not in str(error.value)


def test_invalid_cookie_schema_is_a_sanitized_configuration_error(tmp_path, state):
    state["cookies"][0]["sameSite"] = ["private-value"]
    path = tmp_path / "storage-state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError, match="WEB_STORAGE_STATE") as error:
        load_web_storage_state(str(path))
    assert "private" not in str(error.value)


def test_empty_exported_state_is_supported(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"cookies": [], "origins": []}', encoding="utf-8-sig")
    assert load_web_storage_state(str(path)) == {"cookies": [], "origins": []}


def test_company_browser_context_requires_web_address():
    with pytest.raises(pytest.UsageError, match="WEB_BASE_URL"):
        browser_context_args.__wrapped__({}, Settings(env="company"))
    assert (
        browser_context_args.__wrapped__(
            {"base_url": "https://project.internal"}, Settings(env="company")
        )["base_url"]
        == "https://project.internal"
    )


def test_api_runs_without_web_address_but_explicit_web_tests_fail_early(tmp_path):
    (tmp_path / "company.yaml").write_text("api_base_url: https://api.internal\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers = web: Web test\n", encoding="utf-8")
    test_file = tmp_path / "test_company.py"
    test_file.write_text(
        """import pytest

def test_api_only(api_client):
    assert str(api_client.raw_client.base_url) == "https://api.internal/"

def test_only_base_url(base_url):
    pytest.fail("Web test body must not execute without configuration")

@pytest.mark.web
def test_marked_web():
    pytest.fail("Web test body must not execute without configuration")

@pytest.mark.skip(reason="not enabled")
@pytest.mark.web
def test_skipped_web(base_url):
    pytest.fail("Skipped Web test must not execute")

@pytest.mark.skipif(True, reason="not enabled")
@pytest.mark.web
def test_conditionally_skipped_web(base_url):
    pytest.fail("Skipped Web test must not execute")
""",
        encoding="utf-8",
    )
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "conftest.py").write_text(
        "import pytest\n@pytest.fixture(scope='session')\n"
        "def base_url():\n    return 'https://custom.internal'\n",
        encoding="utf-8",
    )
    (custom / "test_custom.py").write_text(
        "import pytest\n@pytest.mark.web\ndef test_custom_url(base_url):\n"
        "    assert base_url == 'https://custom.internal'\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    for key in (*[field.upper() for field in Settings.model_fields], "TEST_ENV", "PYTEST_ADDOPTS"):
        environment.pop(key, None)
    environment.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
        PYTHONUTF8="1",
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            str(custom),
            "-p",
            "autotest.pytest_plugin",
            "-p",
            "pytest_base_url.plugin",
            "--env",
            "company",
            "--config-dir",
            str(tmp_path),
            "-q",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    output = process.stdout + process.stderr
    assert process.returncode == 1, output
    assert "2 passed" in output and "2 errors" in output and "2 skipped" in output, output
    assert "WEB_BASE_URL" in output
    assert "Web test body must not execute" not in output
