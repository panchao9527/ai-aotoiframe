"""Inspector 风格的教学素材，定位需要在实际 App 中确认。"""

from appium.webdriver.common.appiumby import AppiumBy


def recorded_flow(driver):
    driver.find_element(AppiumBy.ACCESSIBILITY_ID, "profile.tab").click()
    return driver.find_element(AppiumBy.ACCESSIBILITY_ID, "profile.display_name").text
