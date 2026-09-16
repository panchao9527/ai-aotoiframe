# 本地练习：iframe 留言
环境为框架自带 demo。访问 /iframe，在 title=联系表单 的 iframe 内输入留言并提交。
准确验证 status 文本为“已收到：”加本次输入。重复执行数据不互相影响。
将 frame 定位和提交动作提取到 ContactPage，业务断言留在测试。
录制代码仅提供操作事实，base_url 与 page 由框架 fixture 提供。
