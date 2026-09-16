"""草稿静态检查和隔离执行。隔离用于不污染仓库，不是恶意代码安全沙箱。"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from dotenv import dotenv_values

from autotest.ai import AIError
from autotest.authoring.models import (
    dependency_fingerprint,
    destination,
    draft_files,
    fingerprint,
    project_root,
    read_manifest,
    workspace_path,
    write_json,
)
from autotest.redaction import redact, redact_text


def static_check(workspace: Path, manifest: dict) -> tuple[list[str], list[str]]:
    errors = [f"业务条件待确认：{value}" for value in manifest.get("unresolved", [])]
    tests = []
    for name, path in draft_files(workspace, manifest):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{name}: Python 语法或编码错误：{exc}")
            continue
        is_test_file = name.startswith("tests/") and Path(name).name.startswith("test_")
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        if is_test_file and functions:
            tests.append(name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call = ast.unparse(node.func)
                if (
                    call.endswith((".sleep", ".wait_for_timeout", ".skip", ".xfail", ".skipif"))
                    or call == "sleep"
                ):
                    errors.append(f"{name}:{node.lineno}: 不允许固定等待或跳过测试：{call}")
                if call.endswith((".launch", ".launch_persistent_context", ".Remote")):
                    errors.append(
                        f"{name}:{node.lineno}: 请复用 page/app_driver fixture 管理会话。"
                    )
            if isinstance(node, ast.Attribute) and node.attr in {"skip", "skipif", "xfail"}:
                errors.append(f"{name}:{node.lineno}: 草稿不能通过 skip/xfail 绕过验证。")
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant):
                errors.append(f"{name}:{node.lineno}: 不能使用常量断言。")
            if isinstance(node, ast.ExceptHandler) and all(
                isinstance(n, (ast.Pass, ast.Continue)) for n in node.body
            ):
                errors.append(f"{name}:{node.lineno}: 不允许吞掉异常。")
        for function in functions:
            has_assert = any(
                isinstance(n, ast.Assert)
                or (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr.startswith(("to_", "not_to_", "assert_"))
                )
                for n in ast.walk(function)
            )
            if not has_assert:
                errors.append(f"{name}:{function.lineno}: 用例缺少可识别业务断言。")
    if not tests:
        errors.append("草稿中没有 tests/<kind>/test_*.py 下的 test_* 函数。")
    return sorted(set(errors)), tests


def _copy_workspace(root: Path, target: Path) -> None:
    # 只复制测试执行所需内容；不复制 .git、已有报告、虚拟环境和本地录制。
    for name in ("src", "tests", "configs"):
        shutil.copytree(
            root / name,
            target / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
    for name in ("pyproject.toml", "conftest.py"):
        shutil.copy2(root / name, target / name)


def validate(
    name: str,
    *,
    execute: bool = False,
    environment: str | None = None,
    run_app: bool = False,
    timeout: int = 180,
) -> dict:
    root = project_root()
    workspace = workspace_path(name, root)
    manifest = read_manifest(workspace)
    errors, tests = static_check(workspace, manifest)
    if execute and not environment:
        raise AIError("执行草稿必须明确 --env demo/test/staging 等环境。")
    if execute and manifest["kind"] == "app" and not run_app:
        raise AIError("App 草稿执行需要 --run-app，并预先配置具体设备和应用。")
    report = {
        "fingerprint": fingerprint(workspace, manifest),
        "dependency_fingerprint": dependency_fingerprint(root),
        "static_errors": errors,
        "executed": False,
        "passed": False,
        "environment": environment,
        "tests": tests,
        "scope": "静态检查不能证明业务正确，执行目录隔离不是安全沙箱。",
    }
    if execute and not errors:
        # 在临时项目中覆盖候选业务文件，PYTHONPATH 指向完整副本，避免只测试到旧包。
        with tempfile.TemporaryDirectory(prefix="autoiframe-validate-") as temp:
            overlay = Path(temp)
            _copy_workspace(root, overlay)
            for relative, source in draft_files(workspace, manifest):
                target = overlay / destination(relative, manifest["kind"])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            # 每次验证使用新目录，不能把上次通过的 execution.json 当成本次证据。
            evidence = workspace / "validation-artifacts" / uuid.uuid4().hex[:12]
            evidence.mkdir(parents=True)
            report["artifacts"] = str(evidence.relative_to(workspace))
            command = [
                sys.executable,
                "-m",
                "pytest",
                *tests,
                "--env",
                environment,
                "--require-business",
                "--business-kind",
                manifest["kind"],
                "--artifact-dir",
                str(evidence),
                "--junitxml",
                str(evidence / "junit.xml"),
                "--output",
                str(evidence / "web"),
                "--tracing=retain-on-failure",
                "--screenshot=only-on-failure",
                "-q",
            ]
            if run_app:
                command.append("--run-app")
            env = {
                **{k: v for k, v in dotenv_values(root / ".env").items() if v is not None},
                **os.environ,
                "PYTHONPATH": str(overlay / "src"),
                "PYTHONUTF8": "1",
            }
            # 调用者终端的 PYTEST_ADDOPTS 可能加入 -m/--collect-only，影响实际验证范围。
            env.pop("PYTEST_ADDOPTS", None)
            try:
                result = subprocess.run(
                    command,
                    cwd=overlay,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    check=False,
                )
                report.update(executed=True, exit_code=result.returncode)
                try:
                    summary = json.loads((evidence / "execution.json").read_text(encoding="utf-8"))
                    counts = summary["groups"][manifest["kind"]]
                    # 退出码成功仍不足够：只收集、全跳过、部分跳过都不是完整草稿验收。
                    report["passed"] = (
                        result.returncode == 0
                        and not summary["collection_only"]
                        and counts["passed"] > 0
                        and counts["skipped"] == 0
                        and counts["failed"] == 0
                        and counts["errors"] == 0
                    )
                    report["counts"] = counts
                except (OSError, ValueError, KeyError, TypeError):
                    report["passed"] = False
                    report["evidence_error"] = "没有有效的本次业务执行统计，不能判定通过。"
                (workspace / "validation.log").write_text(
                    redact_text(result.stdout + result.stderr), encoding="utf-8"
                )
            except subprocess.TimeoutExpired:
                report.update(executed=True, exit_code=124, passed=False)
                (workspace / "validation.log").write_text(
                    "验证超时，请检查应用或缩小用例。", encoding="utf-8"
                )
    write_json(workspace / "validation.json", redact(report))
    return report


def promote(name: str, *, reviewed: bool = False) -> list[str]:
    """只接收当前内容已执行通过且业务预期已审查的新增文件；绝不覆盖已有文件。"""
    root = project_root()
    workspace = workspace_path(name, root)
    manifest = read_manifest(workspace)
    if not reviewed:
        raise AIError("请先检查业务预期与清理逻辑，再使用 --reviewed 标记已审查。")
    try:
        report = json.loads((workspace / "validation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AIError("请先执行 author validate --execute。") from exc
    if (
        not report.get("passed")
        or not report.get("executed")
        or report.get("fingerprint") != fingerprint(workspace, manifest)
    ):
        raise AIError("当前草稿没有有效的执行通过记录；修改后需重新验证。")
    items = draft_files(workspace, manifest)
    for name, _ in items:
        target = root / destination(name, manifest["kind"])
        if target.exists() or target.resolve() != target:
            raise AIError(f"目标已存在或路径含符号链接，未写入任何文件：{name}")
    if report.get("dependency_fingerprint") != dependency_fingerprint(root):
        raise AIError("项目源码、fixture 或配置已变化，请重新验证草稿。")
    written = []
    try:
        for name, source in items:
            target = root / destination(name, manifest["kind"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as stream:
                written.append(target)
                stream.write(source.read_text(encoding="utf-8"))
    except OSError:
        # 仅撤回本次 x 模式新建的文件，保留所有原有文件和目录。
        for path in written:
            path.unlink(missing_ok=True)
        raise
    write_json(
        workspace / "promotion.json",
        {
            "files": [name for name, _ in items],
            "environment": report["environment"],
            "fingerprint": report["fingerprint"],
        },
    )
    return [name for name, _ in items]
