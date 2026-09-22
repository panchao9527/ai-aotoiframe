---
name: autoiframe-api-authoring
description: 根据前后端源码、OpenAPI 和需求，在 autoiframe 中生成单接口或业务场景 pytest 用例，复用 Service 与 fixture 并验证草稿。
---

# 接口用例编写

从项目根目录执行命令。阅读 docs/09-authoring-workflows.md，按任务选择
templates/authoring/api-single.md 或 api-scenario.md。

1. 明确需求、目标环境、接口范围。源码和 OpenAPI 冲突时记录差异，不能以实现代替预期。
2. 使用 author prepare，传入需求、原始 OpenAPI 或 Swagger UI 页面地址，以及明确源码文件/模块。
   多文档组使用 --spec-group；目录源码需要 --match。不要把网页片段或临时参数当业务预期。
3. 读取 context.json 与 prompt.md，从签名索引找已有对象，再按需读取有关源码/fixture。
   一条独立场景中传递动态 ID，不依赖其他 test 的运行顺序。
4. 生成 files/unresolved/notes JSON，保存 response.json，通过 author generate --response 导入。
   既有授权涵盖模型调用时也可使用 --send。
5. 静态检查后，在已授权环境 author validate NAME --execute --env ENV，读取结果和证据。
6. 业务预期、清理和执行结果符合要求后 author promote NAME --reviewed。
   用户授权已涵盖编写、验证和入库时继续完成，不重复要求批准。

缺少信息仅阻止依赖它的场景；写入 unresolved，不用固定 ID、demo、skip 或宽松断言掩盖。
已有代码修复使用正常 Git diff 与目标回归，promote 仅新增。按范围取材，不上传整个源码库。
