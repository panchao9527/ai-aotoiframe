"""Web 用例直接表达业务期望；定位与点击封装在页面对象里。"""

import pytest
from playwright.sync_api import expect

from autotest.web.pages import ItemsPage, LoginPage

pytestmark = [pytest.mark.web, pytest.mark.demo]


@pytest.mark.smoke
def test_login_success(page, base_url):
    login = LoginPage(page)
    login.open(base_url)
    login.login("demo", "demo123")
    # expect 会等待页面变化，不需要 time.sleep(3)。
    expect(ItemsPage(page).heading).to_be_visible()
    expect(page).to_have_url(base_url + "/items")


def test_login_wrong_password(page, base_url):
    login = LoginPage(page)
    login.open(base_url)
    login.login("demo", "wrong")
    expect(login.error).to_have_text("用户名或密码错误")
    expect(login.submit).to_be_visible()
