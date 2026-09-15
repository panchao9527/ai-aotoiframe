"""项目级插件入口：pytest 自动发现；业务 fixture 可继续放 tests/*/conftest.py。"""

pytest_plugins = ["autotest.pytest_plugin", "autotest.mobile.plugin"]
