"""静态 import 影响范围包括传递依赖、相对导入、包和 fixture；不会执行源码。"""

import pytest

from autotest.authoring.impact import analyze_impact

pytestmark = pytest.mark.unit


@pytest.fixture
def project(tmp_path):
    files = {
        "src/project_business/__init__.py": "",
        "src/project_business/api/__init__.py": "",
        "src/project_business/api/client.py": "raise RuntimeError('must not execute')",
        "src/project_business/api/service.py": "from . import client",
        "tests/api/test_orders.py": "from project_business.api.service import Orders",
        "tests/web/test_page.py": "import project_business.api.service",
        "tests/api/test_other.py": "import pytest",
        "tests/api/conftest.py": "",
    }
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_transitive_import_and_deleted_module_still_find_consumers(project):
    path = "src/project_business/api/client.py"
    expected = ["tests/api/test_orders.py", "tests/web/test_page.py"]
    assert analyze_impact(project, [path])["tests"] == expected
    (project / path).unlink()
    assert analyze_impact(project, [path])["tests"] == expected
    assert analyze_impact(project, ["src/project_business/api/__init__.py"])["tests"] == expected


def test_fixture_scope_and_public_changes(project):
    assert analyze_impact(project, ["tests/api/conftest.py"])["tests"] == [
        "tests/api/test_orders.py",
        "tests/api/test_other.py",
    ]
    assert len(analyze_impact(project, ["src/autotest/config.py"])["tests"]) == 3
    assert analyze_impact(project, ["tests/web/test_page.py"])["tests"] == [
        "tests/web/test_page.py"
    ]
    assert analyze_impact(project, ["docs/guide.md"])["tests"] == []


def test_service_change_propagates_through_fixture_scope(project):
    (project / "tests/api/conftest.py").write_text(
        "from project_business.api.service import Orders", encoding="utf-8"
    )
    result = analyze_impact(project, ["src/project_business/api/client.py"])
    assert "tests/api/test_other.py" in result["tests"]
    assert any(
        "fixture 间接依赖" in reason for reason in result["reasons"]["tests/api/test_other.py"]
    )


def test_unknown_imports_do_not_prove_absence_of_impact(project):
    report = analyze_impact(project, ["requirements/new.md"])
    assert not report["tests"]
    assert "动态 import" in report["limitations"]
    with pytest.raises(ValueError):
        analyze_impact(project, ["../secret.py"])
