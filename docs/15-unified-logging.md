# 15 · 统一运行日志与排查

框架每次 pytest 运行都会记录成功和失败事件。日志用于快速定位，HTML/JUnit/Allure 用于报告，
Playwright Trace、截图、视频和 App XML 用于还原现场；三者职责不同。

## 1. 日志目录

使用 `qa run` 时，每次运行创建独立目录：

```text
artifacts/<UTC时间-随机后缀>/
├── console.log             # pytest 终端输出的脱敏副本
├── run.log                 # 合并后的人类可读事件日志
├── events.jsonl            # 供 AI、脚本和日志平台处理的结构化事件
├── log-summary.json        # 事件、警告和错误数量
├── logs/
│   ├── events-main.jsonl   # pytest 控制进程原始分片
│   ├── events-gw0.jsonl    # xdist worker 原始分片
│   └── events-gw1.jsonl
├── run.json
├── execution.json
├── report.html
├── junit.xml
├── allure-results/
├── failures/
└── web/
```

直接运行 pytest 也会生成 `run.log` 和 `events.jsonl`，但只有 `qa run` 会把实时终端输出同时
写入 `console.log`。worker 分片保留用于合并异常时排查；正常阅读优先看根目录文件。

## 2. 事件包含什么

每条 JSONL 事件包含：

```json
{
  "timestamp": "2026-09-21T10:22:59.952+00:00",
  "level": "INFO",
  "event": "api.request",
  "message": "POST -> 201",
  "run_id": "20260921-102255-8ee63e",
  "environment": "demo",
  "worker": "gw1",
  "nodeid": "tests/api/test_order.py::test_create",
  "case_id": "ORDER-001",
  "data": {
    "method": "POST",
    "url": "https://test.example.com/api/orders",
    "status": 201,
    "duration_ms": 32.5
  }
}
```

当前自动事件包括：

| 范围 | 事件 |
|---|---|
| pytest | session.start/session.finish、test.start、setup/call/teardown 结果与耗时 |
| Python logger | INFO 以上的业务 logger，带 logger 名称 |
| API | 方法、去查询参数 URL、状态码、耗时、网络异常类型 |
| Web | page fixture、XHR/fetch/document 状态、Console 警告错误、pageerror、requestfailed |
| Appium | 配置错误、连接、会话建立、异常和关闭 |
| 测试数据 | 工厂建立、各资源清理状态和清理失败 |
| 业务步骤 | 测试通过 `log_step` 主动记录的关键阶段与耗时 |

### 实际 run.log 示例

以下来自本地双 worker 真实执行，字段顺序为：时间、级别、worker、用例、事件、消息和数据。

```text
2026-09-21T10:33:43.152+00:00 INFO main - session.start pytest session configured {"suite":"all","worker":"main"}
2026-09-21T10:33:44.755+00:00 INFO gw0 tests/api/managed_items/test_managed_items.py::test_lifecycle api.request POST -> 200 {"method":"POST","url":"http://127.0.0.1:57327/api/login","status":200,"duration_ms":19.42}
2026-09-21T10:33:44.769+00:00 INFO gw0 tests/api/managed_items/test_managed_items.py::test_lifecycle data.cleanup test data cleanup completed {"resources":[{"resource":"item","status":"cleaned"}]}
2026-09-21T10:33:57.875+00:00 INFO gw0 - web.response GET -> 200 {"type":"response","method":"GET","url":"http://127.0.0.1:57327/","status":200}
```

使用 `log_step` 后会增加业务阶段事件：

```text
2026-09-21T11:00:01.120+00:00 INFO gw0 tests/api/test_order.py::test_submit step.start 提交审核 {"order_type":"normal"}
2026-09-21T11:00:01.286+00:00 INFO gw0 tests/api/test_order.py::test_submit step.finish 提交审核 {"outcome":"passed","duration_ms":166.04}
```

故意失败时，密码等值先被替换：

```text
2026-09-21T11:02:10.015+00:00 ERROR gw1 tests/api/test_login.py::test_login test.phase call: failed {"phase":"call","outcome":"failed","duration_ms":35.7,"error":"AssertionError: password='[REDACTED]'"}
2026-09-21T11:02:10.020+00:00 ERROR gw1 tests/api/test_login.py::test_login step.finish 登录并核对首页 {"outcome":"failed","duration_ms":42.3,"error_type":"AssertionError"}
```

### 实际 events.jsonl 示例

每行是一个独立 JSON 对象，适合按 run_id、case_id、nodeid、event 或 status 导入 ELK/脚本分析：

```json
{"timestamp":"2026-09-21T10:33:44.755+00:00","level":"INFO","event":"api.request","message":"POST -> 200","run_id":"20260921-103342-c214f9","environment":"demo","worker":"gw0","nodeid":"tests/api/managed_items/test_managed_items.py::test_lifecycle","case_id":"ITEMS-LIFECYCLE","data":{"method":"POST","url":"http://127.0.0.1:57327/api/login","status":200,"duration_ms":19.42}}
```

### log-summary.json 示例

```json
{
  "events": 1030,
  "warnings": 3,
  "errors": 0
}
```

## 3. 记录业务步骤

复杂场景可以注入 `log_step` fixture：

```python
def test_order_flow(log_step, order_factory, role_clients):
    with log_step("准备订单", order_type="normal"):
        order = order_factory.create()

    with log_step("提交审核"):
        response = role_clients("operator").post(f"/api/orders/{order['id']}/submit")
        assert response.status_code == 200

    with log_step("核对最终状态"):
        result = role_clients("reader").get(f"/api/orders/{order['id']}")
        assert result.json()["status"] == "SUBMITTED"
```

步骤名称描述业务阶段，不包装每一行代码。参数只放枚举、类型、数量等非敏感值；密码、Token、
完整请求/响应正文、身份证、手机号和页面完整文本不能写入步骤参数。

## 4. 调整日志级别

默认写 INFO 以上事件：

```powershell
uv run qa run --suite api -- --env test --event-log-level INFO
```

只保留警告和错误：

```powershell
uv run qa run --suite all -- --env test --event-log-level WARNING
```

DEBUG 会增加业务 logger 输出，但框架仍不会记录认证头、Cookie、URL 查询串和 HTTP 正文。

## 5. 常用查询

PowerShell：

```powershell
# 查看所有错误。
Select-String -Path artifacts/<运行目录>/run.log -Pattern " ERROR "

# 查一条用例的完整事件链。
Select-String -Path artifacts/<运行目录>/run.log -Pattern "test_create_order"

# 查 API 5xx。
Select-String -Path artifacts/<运行目录>/events.jsonl -Pattern '"status":5'
```

有 ripgrep 时：

```text
rg ' ERROR |requestfailed|pageerror' artifacts/<运行目录>/run.log
rg '"nodeid":"tests/api/test_order.py::test_create"' artifacts/<运行目录>/events.jsonl
```

## 6. 失败时先看什么

1. `log-summary.json`：确认错误/警告数量；
2. `run.log`：按 nodeid 查看准备、请求、断言和清理时间线；
3. `failures/<用例>/call.json`：读取失败摘要与最近 API/Web 事件；
4. `report.html` 或 Allure：查看用例层级和附件；
5. Web 用 Trace，App 用截图/XML/Appium 日志，ARTEMIS 用自己的 trace ID 深挖。

环境、数据、用例和产品问题应分别处理，不能只增加重试或放宽断言。

## 7. 脱敏和边界

- 结构化数据和日志消息经过基础脱敏；单条事件超过 32 KiB 时只保留 SHA-256；
- API 默认只记录方法、无查询参数 URL、状态码和耗时；
- Allure 参数中的 password/token 等字段会改为 `[REDACTED]`；复杂对象和非白名单字符串参数
  默认显示为 `[HIDDEN]`，只保留 method/status/platform/profile 等简单枚举；
- `console.log` 是终端输出的脱敏副本；终端本身仍可能显示测试代码主动打印的敏感值；
- 截图、视频、Trace、App XML 和第三方 Appium/ARTEMIS 原始日志不是 DLP，分享前人工检查；
- URL 路径可能含业务 ID，当前不会自动判断它是否属于个人隐私；
- `artifacts/` 被 Git 忽略，框架不会自动上传日志。

不要使用 `print(response.json())` 或记录完整请求对象。需要业务响应证据时，提取明确白名单字段，
通过业务断言和 `log_step` 记录非敏感状态。

## 8. 并行和保留策略

xdist worker 不共享文件，各自写分片，控制进程结束后按 UTC 时间合并，避免并发写坏日志。
原始分片不会删除，便于合并失败时恢复。

框架当前不自动删除历史 `artifacts`，避免误删人工保留的失败证据。团队接入 CI 后应在 CI
Artifact 策略中设置保留天数；本地确认报告不再需要后，再按具体运行目录清理。

## 9. 本轮验证

本地 API 双 worker 实跑生成 151 条事件，`run.log`、`events.jsonl`、`console.log`、worker 分片
和摘要均存在，20 条 API 用例通过。检查确认日志、Allure JSON、JUnit 和 HTML 中没有出现
演示密码；故意失败的 setup/call/teardown 仍分别保存错误事件和失败证据。

最终完整双 worker 回归为 **231 passed, 1 skipped**，生成 1030 条事件、3 条警告、0 条错误；
跳过项仍是没有真实设备的 App 示例。已扫描日志、Allure、JUnit、HTML 和 JSONL，未发现本地
演示密码及单测使用的已知敏感假值。报告目录为 `artifacts/20260921-103342-c214f9/`。
