"""Screen Object：业务步骤与元素定位分开，让一个定位改动只改一处。

例：用例调用 screen.login(username, password)，无需重复查找三个元素。
定位失败时保留原始异常，便于报告定位问题；不要用吞异常或改断言来“自愈”。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as conditions
from selenium.webdriver.support.ui import WebDriverWait

Locator = tuple[str, str]


class BaseScreen:
    """App 页面的公共操作；所有元素操作都等待到条件成立，不使用固定 sleep。"""

    def __init__(self, driver: WebDriver, timeout: float = 15) -> None:
        if timeout <= 0:
            raise ValueError("页面等待 timeout 必须大于 0 秒")
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)

    def visible(self, locator: Locator) -> WebElement:
        """元素存在且可见后返回；超时产生原始 TimeoutException。"""
        return self.wait.until(conditions.visibility_of_element_located(locator))

    def tap(self, locator: Locator) -> None:
        """等待元素可点击（可见且 enabled），然后只执行一次点击。"""
        self.wait.until(conditions.element_to_be_clickable(locator)).click()

    def fill(self, locator: Locator, value: str) -> None:
        """清空旧文本再输入；不在日志记录 value，避免测试密码进入日志。"""
        element = self.visible(locator)
        element.clear()
        element.send_keys(value)

    def text(self, locator: Locator) -> str:
        return self.visible(locator).text

    @contextmanager
    def webview(self, name: str | None = None) -> Iterator[BaseScreen]:
        """临时进入 App 内嵌网页；即使网页断言失败，也恢复 NATIVE_APP。

        使用方式：with screen.webview("WEBVIEW_com.company.app"):
        多 WebView 时必须传确切 name，避免误操作第三方或后台页面。
        """

        def find_context(driver: WebDriver) -> str | bool:
            contexts = [item for item in driver.contexts if item.startswith("WEBVIEW")]
            if name is not None:
                return name if name in contexts else False
            if len(contexts) > 1:
                raise ValueError("存在多个 WebView，请传入确切的 context name")
            return contexts[0] if contexts else False

        context_name = self.wait.until(find_context)
        try:
            self.driver.switch_to.context(context_name)
            yield self
        finally:
            self.driver.switch_to.context("NATIVE_APP")


class LoginScreen(BaseScreen):
    """自有 App 的登录契约示例，不是某个随附 App 的已验证定位。

    请让开发同事在 Android content-desc / iOS accessibilityIdentifier 上提供
    下列稳定标识，或按 Inspector 实际结果替换这里的四个定位。
    """

    USERNAME: Locator = (AppiumBy.ACCESSIBILITY_ID, "login.username")
    PASSWORD: Locator = (AppiumBy.ACCESSIBILITY_ID, "login.password")
    SUBMIT: Locator = (AppiumBy.ACCESSIBILITY_ID, "login.submit")
    HOME: Locator = (AppiumBy.ACCESSIBILITY_ID, "home.screen")

    def login(self, username: str, password: str) -> None:
        self.fill(self.USERNAME, username)
        self.fill(self.PASSWORD, password)
        self.tap(self.SUBMIT)

    def wait_until_logged_in(self) -> WebElement:
        """等待首页的唯一标识；用例应继续断言账号或业务数据等实际结果。"""
        return self.visible(self.HOME)
