"""按工程类型生成默认依赖、业务目录和 CI；公共底座仍使用同一份版本。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

PROJECT_TYPES = ("api", "web", "app", "all")


def validate_type(project_type: str | None) -> None:
    if project_type is not None and project_type not in PROJECT_TYPES:
        raise ValueError("工程类型必须是 api、web、app 或 all")


def read_project_type(root: Path) -> str | None:
    path = root / ".qa-framework.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("工程版本记录无效")
    project_type = data.get("project_type")
    validate_type(project_type)
    return project_type


def asset_bytes(source: Path, name: str, project_type: str | None) -> bytes:
    """升级和初始化必须使用相同渲染，避免升级覆盖单端工程的默认配置。"""
    content = (source / name).read_bytes()
    if name != "pyproject.toml" or project_type is None:
        return content
    validate_type(project_type)
    text = content.decode("utf-8")
    suites = ("api", "web", "app") if project_type == "all" else (project_type,)
    testpaths = json.dumps([f"tests/{suite}" for suite in suites])
    text = re.sub(r"(?m)^testpaths = .*?$", f"testpaths = {testpaths}", text)
    default = f'default-groups = ["{project_type}"]'
    if "[tool.uv]" in text:
        if re.search(r"(?m)^default-groups\s*=", text):
            text = re.sub(r"(?m)^default-groups\s*=.*$", default, text)
        else:
            text = text.replace("[tool.uv]", "[tool.uv]\n" + default, 1)
    else:
        text += "\n[tool.uv]\n" + default + "\n"
    return text.encode("utf-8")


def include_template(relative: Path, project_type: str) -> bool:
    name = relative.as_posix()
    if name in {"README.single.md.tmpl"}:
        return False
    if project_type == "all":
        return True
    for kind, layer in (("api", "api"), ("web", "web"), ("app", "mobile")):
        if name.startswith((f"tests/{kind}/", f"src/project_business/{layer}/")):
            return kind == project_type
    if name.startswith("configs/devices/"):
        return project_type == "app"
    return True


def template_text(source: Path, relative: Path, name: str, project_type: str) -> str:
    text = (source / "templates/company" / relative).read_text(encoding="utf-8")
    path = relative.as_posix()
    if project_type != "all":
        if path == "README.md":
            text = (source / "templates/company/README.single.md.tmpl").read_text(encoding="utf-8")
            run = f"uv run --frozen qa run --suite {project_type} -- --env company_test"
            if project_type == "app":
                run += (
                    " --run-app --app-platform android --app-caps configs/devices/android.yaml -n 0"
                )
            install = (
                "uv run --frozen python -m playwright install chromium"
                if project_type == "web"
                else ""
            )
            layer = "mobile" if project_type == "app" else project_type
            text = text.replace("__RUN_COMMAND__", run).replace("__INSTALL_BROWSER__", install)
            text = text.replace("__BUSINESS_LAYER__", layer)
        elif path == "configs/business/smoke.yaml":
            values = yaml.safe_load(text)
            text = "# 按需求填写本端预期；留空会明确失败。\n" + yaml.safe_dump(
                {project_type: values[project_type]}, allow_unicode=True, sort_keys=False
            )
        elif path.startswith("configs/environments/"):
            values = yaml.safe_load(text)
            prefixes = (
                ("api_",)
                + (("web_",) if project_type == "web" else ())
                + (("app",) if project_type == "app" else ())
            )
            values = {
                key: value
                for key, value in values.items()
                if key in {"env", "timeout_seconds"} or key.startswith(prefixes)
            }
            text = "# API 配置也可用于 Web/App 的数据准备；按需填写。\n" + yaml.safe_dump(
                values, allow_unicode=True, sort_keys=False
            )
        elif path == ".env.example":
            lines = []
            for line in text.splitlines():
                match = re.match(r"#?\s*([A-Z][A-Z0-9_]*)=", line)
                key = match.group(1) if match else ""
                if key.startswith("WEB_") and project_type != "web":
                    continue
                if key.startswith(("APP", "ANDROID_", "IOS_")) and project_type != "app":
                    continue
                lines.append(line)
            text = "\n".join(lines) + "\n"
    return text.replace("__PROJECT_NAME__", name).replace("__PROJECT_TYPE__", project_type)


def github_workflow(source: Path, project_type: str) -> str:
    # 引号避免 PyYAML 的 YAML 1.1 将顶层 on 识别为布尔值。
    raw = (source / "templates/company-ci/github-actions.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw.replace("\non:", "\n'on':", 1))
    if project_type == "all":
        return raw
    inputs = data["on"]["workflow_dispatch"]["inputs"]
    inputs["suite"].update(options=[project_type], default=project_type)
    if project_type != "app":
        inputs.pop("app_platform")
        data["concurrency"]["group"] = "company-${{ inputs.environment }}-" + project_type
        data["jobs"] = {project_type: data["jobs"]["api-web"]}
        steps = data["jobs"][project_type]["steps"]
        if project_type == "api":
            steps[:] = [step for step in steps if step.get("name") != "Install browser"]
    else:
        data["jobs"].pop("api-web")
    for job in data["jobs"].values():
        for step in job["steps"]:
            if "env" not in step:
                continue
            step["env"] = {
                key: value
                for key, value in step["env"].items()
                if not (project_type != "app" and key.startswith(("APP_", "CI_APPIUM_")))
                and not (project_type != "web" and key == "CI_WEB_BASE_URL")
            }
    return "# 按工程类型生成；手工触发前配置公司 Environment、vars 和 Secrets。\n" + yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, width=110
    )


def jenkins_pipeline(source: Path, project_type: str) -> str:
    if project_type == "all":
        return (source / "templates/company-ci/Jenkinsfile").read_text(encoding="utf-8")
    text = (source / "templates/company-ci/Jenkinsfile.single.tmpl").read_text(encoding="utf-8")
    app = project_type == "app"
    parameters = (
        """choice(name: 'APP_PLATFORM', choices: ['android', 'ios'], description: 'App 平台')
        string(name: 'ANDROID_AGENT_LABEL', defaultValue: 'qa-android-device', description: 'Android 设备节点')
        string(name: 'IOS_AGENT_LABEL', defaultValue: 'qa-ios-device && macos', description: 'iOS 设备节点')
        string(name: 'DEVICE_RESOURCE', defaultValue: 'qa-primary-device', description: '跨 job 共用同一物理设备锁')"""
        if app
        else "string(name: 'LINUX_AGENT_LABEL', defaultValue: 'qa-linux', description: '公司网络执行节点')"
    )
    agent = (
        "${params.APP_PLATFORM == 'ios' ? params.IOS_AGENT_LABEL : params.ANDROID_AGENT_LABEL}"
        if app
        else "${params.LINUX_AGENT_LABEL}"
    )
    text = (
        text.replace("__PROJECT_TYPE__", project_type)
        .replace("__PARAMETERS__", parameters)
        .replace("__AGENT__", agent)
    )
    browser = (
        "sh 'uv run --frozen python -m playwright install chromium'"
        if project_type == "web"
        else ""
    )
    text = text.replace("__INSTALL_BROWSER__", browser)
    text = text.replace("__APP_ARGS__", ' --app-platform "$APP_PLATFORM"' if app else "")
    execute = (
        """if (!params.DEVICE_RESOURCE?.trim()) { error('App 必须指定设备锁') }
                    lock(resource: params.DEVICE_RESOURCE) { withTestEnvironment() }"""
        if app
        else "withTestEnvironment()"
    )
    return text.replace("__EXECUTE__", execute)
