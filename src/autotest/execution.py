"""按业务类型统计真实执行，防止框架单测通过或全部跳过掩盖业务未运行。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest


def business_kind(nodeid: str) -> str | None:
    pieces = nodeid.replace("\\", "/").split("::", 1)[0].split("/")
    for index, piece in enumerate(pieces[:-1]):
        if piece == "tests" and pieces[index + 1] in {"api", "web", "app", "unit"}:
            return pieces[index + 1]
    return None


class ExecutionTracker:
    def __init__(self, config: pytest.Config, directory: Path):
        self.config = config
        self.directory = directory
        self.results: dict[str, str] = {}

    def pytest_runtest_logreport(self, report):
        # xdist 会把 worker 报告发送给控制进程；只在控制进程汇总，避免重复计数。
        if hasattr(self.config, "workerinput"):
            return
        if report.when == "call":
            self.results[report.nodeid] = "skipped" if report.skipped else report.outcome
        elif report.skipped:
            self.results[report.nodeid] = "skipped"
        elif report.failed:
            self.results[report.nodeid] = "error"

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        if hasattr(self.config, "workerinput"):
            return
        groups = {}
        for kind in ("api", "web", "app", "unit", "other"):
            counts = Counter(
                outcome
                for nodeid, outcome in self.results.items()
                if (business_kind(nodeid) or "other") == kind
            )
            groups[kind] = {
                "passed": counts["passed"],
                "failed": counts["failed"],
                "skipped": counts["skipped"],
                "errors": counts["error"],
                "executed": counts["passed"] + counts["failed"],
            }
        expected = self.config.getoption("business_kind")
        kinds = ("api", "web", "app") if expected == "all" else (expected,)
        missing = self.config.getoption("require_business") and not any(
            groups[k]["executed"] for k in kinds
        )
        if missing and not self.config.option.collectonly and exitstatus == 0:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
            reporter = self.config.pluginmanager.getplugin("terminalreporter")
            if reporter:
                reporter.write_sep(
                    "!", f"目标业务套件 {expected} 没有实际执行；全部跳过不算通过", red=True
                )
        payload = {
            "groups": groups,
            "required_kind": expected,
            "collection_only": bool(self.config.option.collectonly),
            "exit_code": int(session.exitstatus),
        }
        (self.directory / "execution.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
