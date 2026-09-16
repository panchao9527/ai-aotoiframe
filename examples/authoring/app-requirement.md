# App 登录后查看用户资料（需要真实应用接入）
平台：Android。输入资料来自 Appium Inspector，下面定位仅为教学契约。
假定已登录，点击 profile.tab，读取 profile.display_name，预期为测试账号显示名。
测试账号来源 APP_EXPECTED_NAME；API 数据准备方式尚未提供。
把操作整理成 ProfileScreen，复用 app_driver、BaseScreen。
未知项：真实应用是否使用这些 accessibility id、登录 fixture、测试账号和环境。
在确认这些条件前保留 unresolved，不能标记已验证。
