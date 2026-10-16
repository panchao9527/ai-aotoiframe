"""从新目录安装 API 最小依赖并执行实际本地业务检查；不访问公司系统。"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from autotest.config import Settings
from autotest.demo import DemoServer
from autotest.scaffold import init_project


def main() -> None:
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
        project = init_project("acceptance", Path(temporary) / "company")

        def run(*arguments):
            subprocess.run(list(arguments), cwd=project, env=environment, check=True)

        run("uv", "sync", "--frozen", "--no-dev", "--python", sys.executable)
        python = project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        # 新虚拟环境只拥有 API 依赖；实际加载公共插件、App 插件，验证延迟导入边界。
        run(
            str(python),
            "-c",
            "import importlib.util; assert importlib.util.find_spec('playwright') is None; assert importlib.util.find_spec('appium') is None",
        )
        with DemoServer() as server:
            (project / "configs/environments/company_test.yaml").write_text(
                yaml.safe_dump(
                    {"api_base_url": server.base_url, "api_auth_file": "configs/auth/company.yaml"}
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
                        }
                    }
                ),
                encoding="utf-8",
            )
            run(str(python), "-m", "autotest", "doctor", "--suite", "api")
            run(
                str(python),
                "-m",
                "autotest",
                "project",
                "check",
                "--env",
                "company_test",
                "--suite",
                "api",
            )
            run(
                str(python),
                "-m",
                "autotest",
                "run",
                "--suite",
                "api",
                "--path",
                "tests/api/test_company_smoke.py",
                "--",
                "-q",
            )
        print("独立项目验收通过：最小 API 安装、配置预检、单文件执行和报告。")


if __name__ == "__main__":
    main()
