---
name: autoiframe-test-maintenance
description: 根据 autoiframe 失败摘要、Trace 和最新需求定位测试失败，维护已有 API、POM 或 Screen 用例。
---

# 基于证据维护测试

用户提供失败或要求维护时阅读 docs/11-tool-integration.md。选择实际运行目录，
qa evidence --run-dir ... --output artifacts/ai/triage.json。
仅阅读有关用例、对象、fixture 和必要附件；截图/Trace 分享前检查业务敏感信息。

区分事实、推测、缺口，归类为产品缺陷、用例问题、环境/数据问题、证据不足。
定位变更需要新页面/设备证据，预期变更需要需求/契约依据。
保留原始失败，不将 skip/xfail、删断言、扩大成功范围当作修复。

按授权范围修改已有对象，检查 diff，先复跑失败用例，再跑受影响集合。
新增对象前查已有签名；深入浏览器诊断时用 DevTools 网络/控制台。
产品缺陷或证据不足时保留可复现结论，不无限自动修复。
