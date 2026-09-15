"""接入你们公司 App 后运行的登录示例；仓库没有附带 APK/IPA。

先替换 LoginScreen 的定位，使其符合你们 App 的实际页面。测试账号应位于测试
环境，且能登录成功。每次用例开始时 App 必须位于未登录的登录页面。
"""

import os

import pytest

from autotest.mobile.screens import LoginScreen

pytestmark = [pytest.mark.app, pytest.mark.smoke]


@pytest.fixture
def app_login_credentials() -> tuple[str, str]:
    """只读取环境变量，不把账号密码直接写入 Git；缺失时明确失败。"""
    username = os.getenv("APP_TEST_USERNAME")
    password = os.getenv("APP_TEST_PASSWORD")
    if not username or not password:
        pytest.fail(
            "请设置 APP_TEST_USERNAME 和 APP_TEST_PASSWORD，并适配自有 App 登录页", pytrace=False
        )
    return username, password


def test_login_opens_home(app_login_credentials, app_driver, settings):
    """执行登录并断言首页可见；复杂项目请增加账号信息、权限等业务断言。"""
    username, password = app_login_credentials
    login = LoginScreen(app_driver, timeout=settings.app_wait_seconds)
    login.login(username, password)
    assert login.wait_until_logged_in().is_displayed(), "登录成功后应显示首页"
