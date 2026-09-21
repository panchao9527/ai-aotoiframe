"""新手命令入口。复杂用例仍然是普通 pytest，不创造第二套测试语言。"""

import argparse
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from autotest.redaction import redact


def run_tests(suite: str, extra: list[str]) -> int:
    """一条命令生成 HTML、JUnit、Allure 原始数据与浏览器失败证据。"""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    destination = Path("artifacts") / stamp
    destination.mkdir(parents=True)
    target = "tests" if suite == "all" else f"tests/{suite}"
    allow_empty = "--allow-empty" in extra
    extra = [arg for arg in extra if arg != "--allow-empty"]
    gate = (
        [] if suite == "unit" or allow_empty else ["--require-business", "--business-kind", suite]
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        target,
        f"--artifact-dir={destination}",
        f"--html={destination / 'report.html'}",
        "--self-contained-html",
        f"--junitxml={destination / 'junit.xml'}",
        f"--alluredir={destination / 'allure-results'}",
        f"--output={destination / 'web'}",
        "--tracing=retain-on-failure",
        "--screenshot=only-on-failure",
        "--video=retain-on-failure",
        *gate,
        *extra,
    ]
    print(f"本次报告目录：{destination.resolve()}", flush=True)
    # 不用 shell=True；用户传入的是参数列表，不会作为系统命令执行。
    result = subprocess.run(command, check=False, env={**os.environ, "PYTHONUTF8": "1"})
    (destination / "run.json").write_text(
        json.dumps(
            redact({"suite": suite, "command": command, "exit_code": result.returncode}),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return result.returncode


def doctor() -> int:
    """只读检查：不安装 SDK、不启动 Appium、不连接真实手机。"""
    checks = {
        "pytest": "pytest",
        "httpx": "httpx",
        "playwright": "playwright",
        "Appium-Python-Client": "appium",
        "pytest-playwright": "pytest_playwright",
        "allure-pytest": "allure_pytest",
    }
    missing = []
    print(f"Python: {sys.version.split()[0]} / {sys.executable}")
    for distribution, module in checks.items():
        if importlib.util.find_spec(module) is None:
            missing.append(distribution)
            print(f"[缺少] {distribution}")
        else:
            print(f"[OK] {distribution} {importlib.metadata.version(distribution)}")
    if "playwright" not in missing:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            installed = Path(pw.chromium.executable_path).is_file()
            print(f"[{'OK' if installed else '未安装'}] Chromium")
            if not installed:
                print("  Web 测试前运行：python -m playwright install chromium")
    for name in ("node", "npm", "npx", "adb", "java", "appium", "allure"):
        print(f"[可选工具] {name}: {shutil.which(name) or '未发现（仅相关功能需要）'}")
    print("App 真机、Appium 驱动、Xcode/WDA 未在此检查中验证；见 docs/04-app.md。")
    print("基础 Python 依赖检查完成；网络连通性、业务账号和 AI 模型需接入项目后验证。")
    return 1 if missing else 0


def new_test(kind: str, name: str, output: str | None) -> Path:
    """生成带 TODO 的用例骨架；未完成前显式失败，防止空断言误报通过。"""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("name 用英文小写字母开头，仅包含小写字母、数字、下划线")
    path = Path(output or f"tests/{kind}/test_{name}.py").resolve()
    test_root = Path("tests").resolve()
    if not path.is_relative_to(test_root) or path.suffix != ".py":
        raise ValueError("输出必须在当前项目 tests/ 中，且以 .py 结尾")
    if path.exists():
        raise ValueError(f"文件已存在，不会覆盖：{path}")
    fixture = {"api": "api_client", "web": "page, base_url", "app": "app_driver"}[kind]
    examples = {
        "api": '# response = api_client.get("/your-endpoint")\n    # assert response.status_code == 200',
        "web": '# page.goto(base_url)\n    # expect(page.get_by_role("heading", name="首页")).to_be_visible()',
        "app": "# screen = LoginScreen(app_driver)\n    # screen.login(username, password)",
    }
    content = f'''"""{name} 的业务测试。按照 准备 → 操作 → 断言 → 清理 补全。"""

import pytest

pytestmark = pytest.mark.{kind}


def test_{name}({fixture}):
    # TODO：下面是写法提示，请替换为真实项目的路径、定位、数据和断言。
    {examples[kind]}
    # 创建数据的用例使用 yield fixture / try-finally 清理，避免污染后续执行。
    pytest.fail("TODO：请补全业务步骤和真实断言后删除此行")
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    # x 模式在并发场景下也不覆盖已有文件。
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)
    return path


def main(argv: list[str] | None = None) -> int:
    # Windows 下输出被 CI / 编辑器通过管道读取时，统一 UTF-8，避免中文报告路径乱码。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "ai":
        from autotest.ai import main as ai_main

        return ai_main(args[1:])
    if args and args[0] == "project":
        from autotest.project import main as project_main

        return project_main(args[1:])
    if args and args[0] == "browser":
        from autotest.browser_cli import main as browser_main

        return browser_main(args[1:])
    if args and args[0] == "artemis":
        from autotest.mobile.artemis import main as artemis_main

        return artemis_main(args[1:])
    if args and args[0] in {"author", "record", "evidence"}:
        from autotest.authoring.cli import main as author_main

        return author_main(args)
    parser = argparse.ArgumentParser(description="Python 接口 / Web / App 自动化框架")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="运行测试并生成报告，-- 后可接 pytest 参数")
    run.add_argument("--suite", choices=["all", "unit", "api", "web", "app"], default="all")
    sub.add_parser("doctor", help="只读检查 Python 依赖和可选工具")
    sub.add_parser("project", help="项目 API 地址和角色鉴权配置预检")
    sub.add_parser("browser", help="固定版本 Playwright CLI 页面探索入口")
    sub.add_parser("artemis", help="可选 ARTEMIS Android AI 探索入口")
    demo = sub.add_parser("demo", help="手动启动本地练习系统，Ctrl+C 关闭")
    demo.add_argument("--port", type=int, default=8765)
    new = sub.add_parser("new", help="创建带中文注释的用例模板")
    new.add_argument("--kind", choices=["api", "web", "app"], required=True)
    new.add_argument("--name", required=True)
    new.add_argument("--output")
    sub.add_parser("ai", help="AI 用例草稿与失败分析，默认离线")
    sub.add_parser("author", help="材料收集、多文件草稿、验证和入库")
    sub.add_parser("record", help="Playwright 录制入口与 App 录制说明")
    sub.add_parser("evidence", help="导出可供 AI 分析的失败证据摘要")
    options, extra = parser.parse_known_args(args)
    if extra and extra[0] == "--":
        extra = extra[1:]
    if options.command != "run" and extra:
        parser.error("未识别参数：" + " ".join(extra))
    try:
        if options.command == "run":
            return run_tests(options.suite, extra)
        if options.command == "doctor":
            return doctor()
        if options.command == "new":
            print(f"已创建：{new_test(options.kind, options.name, options.output)}")
            return 0
        if options.command == "demo":
            from autotest.demo import DemoServer

            with DemoServer(options.port) as server:
                print(f"练习系统：{server.base_url}（demo / demo123），Ctrl+C 关闭", flush=True)
                try:
                    threading.Event().wait()
                except KeyboardInterrupt:
                    print("\n练习系统已关闭")
            return 0
    except (ValueError, OSError) as exc:
        print(f"错误：{redact(str(exc))}", file=sys.stderr)
        return 2
    return 0
