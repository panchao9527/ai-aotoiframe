"""独立工程安装验收：API/Web 访问本机 demo；App 只预检/收集，不连接设备。"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from autotest.config import Settings
from autotest.demo import DemoServer
from autotest.scaffold import init_project


def verify(project_type: str) -> None:
    environment = dict(os.environ)
    for key in (
        *[name.upper() for name in Settings.model_fields],
        "TEST_ENV",
        "PYTEST_ADDOPTS",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "UV_PROJECT_ENVIRONMENT",
    ):
        environment.pop(key, None)
    environment["PYTHONUTF8"] = "1"
    with tempfile.TemporaryDirectory(prefix="qa-project-acceptance-") as temporary:
        project = init_project(
            "acceptance", Path(temporary) / project_type, project_type=project_type
        )

        def run(*arguments):
            subprocess.run(list(arguments), cwd=project, env=environment, check=True)

        run("uv", "sync", "--frozen", "--python", sys.executable)
        python = project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        # 直接检查新虚拟环境的模块，避免继承开发环境造成缺依赖仍通过的假象。
        web = project_type in {"web", "all"}
        app = project_type in {"app", "all"}
        run(
            str(python),
            "-c",
            f"import importlib.util; assert bool(importlib.util.find_spec('playwright')) == {web}; assert bool(importlib.util.find_spec('appium')) == {app}",
        )
        run(str(python), "-m", "autotest", "doctor")
        if project_type == "app":
            (project / "configs/devices/android.yaml").write_text(
                yaml.safe_dump(
                    {
                        "platformName": "Android",
                        "appium:automationName": "UiAutomator2",
                        "appium:udid": "qa-offline-check",
                        "appium:appPackage": "com.example.qa",
                        "appium:appActivity": ".MainActivity",
                    }
                ),
                encoding="utf-8",
            )
            run(
                str(python),
                "-m",
                "autotest",
                "project",
                "check",
                "--env",
                "company_test",
                "--suite",
                "app",
            )
            run(str(python), "-m", "pytest", "--collect-only", "--run-app", "-q")
            print("独立 App 工程验收通过：安装、离线配置与用例收集；未连接设备，未执行 App 业务。")
            return
        with DemoServer() as server:
            (project / "configs/environments/company_test.yaml").write_text(
                yaml.safe_dump(
                    {
                        "api_base_url": server.base_url,
                        "web_base_url": server.base_url,
                        "api_auth_file": "configs/auth/company.yaml",
                    }
                ),
                encoding="utf-8",
            )
            (project / "configs/business/smoke.yaml").write_text(
                yaml.safe_dump(
                    {
                        "api": {
                            "path": "/health",
                            "expected_status": 200,
                            "expected_field": "status",
                            "expected_value": "ok",
                        },
                        "web": {"path": "/", "expected_heading": "自动化练习系统"},
                    }
                ),
                encoding="utf-8",
            )
            for suite in ("api", "web") if project_type == "all" else (project_type,):
                run(
                    str(python),
                    "-m",
                    "autotest",
                    "project",
                    "check",
                    "--env",
                    "company_test",
                    "--suite",
                    suite,
                )
            # 不指定 suite，验证工程默认选择；all 工程未启用 App 时要求 API/Web 实际执行。
            run(str(python), "-m", "autotest", "run", "--", "--env", "company_test", "-q")
        print(f"独立 {project_type} 工程验收通过：按端安装、预检、默认业务执行和报告。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", choices=("api", "web", "app", "all"), default="api")
    parser.add_argument("--all-types", action="store_true", help="分别验证三类独立工程和三端组合")
    args = parser.parse_args()
    for kind in ("api", "web", "app", "all") if args.all_types else (args.type,):
        verify(kind)


if __name__ == "__main__":
    main()
