"""编写流程命令。默认只整理本地材料；在线模型、录制和测试执行均有独立入口。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from autotest.ai import AIError
from autotest.authoring.models import project_root, workspace_path
from autotest.authoring.validation import promote, validate
from autotest.authoring.workflow import generate, prepare
from autotest.evidence import export_evidence
from autotest.redaction import redact_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="API / Web / App 用例编写工作流")
    roots = parser.add_subparsers(dest="group", required=True)
    author = roots.add_parser("author", help="生成与验证")
    actions = author.add_subparsers(dest="action", required=True)
    prep = actions.add_parser("prepare", help="提取契约、源码、录制及现有对象，生成提示词")
    prep.add_argument("name")
    prep.add_argument("--kind", choices=("api", "web", "app"), required=True)
    prep.add_argument("--mode", choices=("single", "scenario"), default="single")
    prep.add_argument("--requirement", required=True)
    prep.add_argument("--source", action="append", default=[], help="源码文件/目录，可重复")
    prep.add_argument("--match", help="源码目录内容筛选关键字，不是正则")
    prep.add_argument("--openapi", help="原始 JSON/YAML 或 Swagger UI 的 HTTP(S) URL")
    prep.add_argument("--operation", action="append", default=[], help="例如 'GET /api/items'")
    prep.add_argument("--spec-auth-env", help="保存文档 Authorization 头值的环境变量名")
    prep.add_argument("--spec-group", help="Swagger UI 展示多个文档分组时指定组名")
    prep.add_argument("--recording", help="Playwright/Appium 录制的 Python")
    prep.add_argument("--observation", help="Agent 的页面观察、定位器与预期记录")
    gen = actions.add_parser("generate", help="导入 Agent 回复或显式调用模型，输出多文件草稿")
    gen.add_argument("name")
    source = gen.add_mutually_exclusive_group(required=True)
    source.add_argument("--response", help="外部 Agent 输出的 JSON 文件")
    source.add_argument("--send", action="store_true", help="调用 AI_BASE_URL 配置的模型")
    check = actions.add_parser("validate", help="静态检查，或在隔离副本执行草稿")
    check.add_argument("name")
    check.add_argument("--execute", action="store_true")
    check.add_argument("--env")
    check.add_argument("--run-app", action="store_true")
    check.add_argument("--timeout", type=int, default=180)
    adopt = actions.add_parser("promote", help="将已审查且当前内容验证通过的新增文件放入项目")
    adopt.add_argument("name")
    adopt.add_argument("--reviewed", action="store_true")
    record = roots.add_parser("record", help="人工录制入口")
    record.add_argument("kind", choices=("web", "app"))
    record.add_argument("--name", default="recording")
    record.add_argument("--url")
    record.add_argument("--storage-state", help="本地登录态文件，不会加入 AI 上下文")
    record.add_argument("--print-command", action="store_true", help="仅打印 Web 录制命令")
    evidence = roots.add_parser("evidence", help="导出某次运行的脱敏文本摘要和附件清单")
    evidence.add_argument("--run-dir", required=True)
    evidence.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.group == "evidence":
            output = Path(args.output).resolve()
            allowed = project_root() / "artifacts"
            if not output.is_relative_to(allowed) or output.suffix != ".json":
                raise AIError("证据摘要输出需位于 artifacts/ 内，扩展名为 .json。")
            print(export_evidence(Path(args.run_dir), output))
        elif args.group == "record":
            if args.kind == "app":
                print(
                    "在 Appium Inspector 建立应用会话，开启 Recorder 并通过 Inspector 操作；"
                    "选择 Python，导出代码。使用 author prepare --kind app --recording 文件.py，"
                    "同时提供需求、平台、定位证据。详见 docs/10-mobile-authoring.md。"
                    "本命令没有连接设备，也不会录制手机上的任意手动触摸。"
                )
                return 0
            if not args.url:
                raise AIError("Web 录制需要 --url。")
            url = urlsplit(args.url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
            ):
                raise AIError("录制 URL 必须是没有内嵌凭据的 HTTP(S) 页面。")
            root = project_root()
            workspace_path(args.name, root)  # 复用名称校验，但录制原始素材单独保管。
            output = root / "artifacts" / "recordings" / f"{args.name}.py"
            if output.resolve() != output or output.exists():
                raise AIError("录制输出已存在或目录含符号链接，请换一个 --name。")
            command = [
                sys.executable,
                "-m",
                "playwright",
                "codegen",
                "--target",
                "python-pytest",
                "--output",
                str(output),
            ]
            if args.storage_state:
                state = Path(args.storage_state).resolve()
                if not state.is_file():
                    raise AIError("--storage-state 文件不存在。")
                command.extend(["--load-storage", str(state)])
            command.append(args.url)
            if args.print_command:
                print(json.dumps(command, ensure_ascii=False))
                return 0
            output.parent.mkdir(parents=True, exist_ok=True)
            print("录制文件可能包含输入的账号和数据；导入前检查。输出：", output, flush=True)
            return subprocess.run(command, check=False).returncode
        elif args.action == "prepare":
            print(
                prepare(
                    args.name,
                    args.kind,
                    args.mode,
                    requirement=args.requirement,
                    sources=args.source,
                    match=args.match,
                    recording=args.recording,
                    observation=args.observation,
                    spec=args.openapi,
                    operations=args.operation,
                    spec_auth_env=args.spec_auth_env,
                    spec_group=args.spec_group,
                )
            )
        elif args.action == "generate":
            print(generate(args.name, response=args.response, send=args.send))
        elif args.action == "validate":
            if not 1 <= args.timeout <= 3600:
                raise AIError("--timeout 应为 1 到 3600 秒。")
            report = validate(
                args.name,
                execute=args.execute,
                environment=args.env,
                run_app=args.run_app,
                timeout=args.timeout,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1 if report["static_errors"] or (args.execute and not report["passed"]) else 0
        else:
            print("已新增：\n" + "\n".join(promote(args.name, reviewed=args.reviewed)))
        return 0
    except (AIError, OSError, ValueError) as exc:
        print("编写流程失败：" + redact_text(str(exc)), file=sys.stderr)
        return 1
