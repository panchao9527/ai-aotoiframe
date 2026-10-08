"""确保一个端通过不会掩盖其他端未执行；原始失败和收集模式保持正确。"""

import json
from types import SimpleNamespace

import pytest

from autotest.execution import ExecutionTracker

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "suite,run_app,results,collectonly,initial,expected",
    [
        ("all", False, {"api": "passed", "web": "skipped"}, False, 0, 1),
        ("all", False, {"api": "passed", "web": "passed", "app": "skipped"}, False, 0, 0),
        ("all", True, {"api": "passed", "web": "passed", "app": "skipped"}, False, 0, 1),
        ("all", True, {"api": "passed", "web": "passed", "app": "passed"}, False, 0, 0),
        ("web", False, {"api": "passed", "web": "skipped"}, False, 0, 1),
        ("all", False, {}, True, 0, 0),
        ("all", False, {}, False, 2, 2),
    ],
)
def test_business_gate_per_suite(tmp_path, suite, run_app, results, collectonly, initial, expected):
    options = {"business_kind": suite, "require_business": True, "run_app": run_app}
    config = SimpleNamespace(
        getoption=lambda name, default=None: options.get(name, default),
        option=SimpleNamespace(collectonly=collectonly),
        pluginmanager=SimpleNamespace(getplugin=lambda name: None),
    )
    tracker = ExecutionTracker(config, tmp_path)
    tracker.results = {
        f"tests/{kind}/test_sample.py::test_one": result for kind, result in results.items()
    }
    session = SimpleNamespace(exitstatus=initial)
    tracker.pytest_sessionfinish(session, initial)
    assert session.exitstatus == expected
    record = json.loads((tmp_path / "execution.json").read_text(encoding="utf-8"))
    assert record["exit_code"] == expected
    if suite == "all":
        assert record["required_kinds"] == (["api", "web", "app"] if run_app else ["api", "web"])
