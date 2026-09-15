"""失败证据和 AI 输入共用的脱敏工具（标准库实现）。

这是一层“减少意外泄露”的保护，不是识别所有公司机密的 DLP 系统。
它不能识别图片里的密码、业务隐私字段或没有标签的一串密钥。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

# 去掉大小写和分隔符后匹配：api_key、api-key、apiKey 都能识别。
_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "token",
    "accesstoken",
    "refreshtoken",
    "idtoken",
    "authtoken",
    "authorization",
    "proxyauthorization",
    "cookie",
    "setcookie",
    "apikey",
    "secret",
    "clientsecret",
    "privatekey",
    "secretkey",
    "xapikey",
    "sessionid",
    "sessiontoken",
}
_KEY_WORDS = (
    r"(?:[A-Za-z0-9_-]*password|passwd|pwd|[A-Za-z0-9_-]*token|"
    r"(?:proxy[-_]?)?authorization|(?:set[-_]?)?cookie|"
    r"(?:[A-Za-z0-9_-]*[-_])?api[-_]?key|apiKey|"
    r"[A-Za-z0-9_-]*secret|private[-_]?key|secret[-_]?key|session[-_]?id)"
)
_QUOTED_ASSIGNMENT = re.compile(
    rf"(?P<prefix>[\"']?\b{_KEY_WORDS}[\"']?\s*[:=]\s*)"
    r"(?P<quote>[\"'])(?P<value>(?:\\.|(?!(?P=quote)).)*)(?P=quote)",
    re.IGNORECASE,
)
_PLAIN_ASSIGNMENT = re.compile(
    rf"(?P<prefix>\b{_KEY_WORDS}\s*[:=]\s*)(?![\"']|\[REDACTED\])(?P<value>[^\s,;&}}\]\"']+)",
    re.IGNORECASE,
)
_HEADER_LINE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:authorization|proxy-authorization|cookie|set-cookie)\s*[:=]\s*)[^\r\n]+"
)
_AUTH_SCHEME = re.compile(r"(?i)\b(?P<scheme>Bearer|Basic)\s+[^\s\"',;<>]+")
_URL_CREDENTIALS = re.compile(r"(?P<scheme>\b[A-Za-z][A-Za-z0-9+.-]*://)[^\s/@]+(?::[^\s/@]*)?@")


def _is_sensitive_key(key: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return normalized in _SENSITIVE_KEYS or normalized.endswith(
        ("password", "token", "secret", "apikey")
    )


def redact_text(text: str) -> str:
    """隐藏文本里的常见认证头、密码赋值、Bearer 凭据和 URL 用户信息。

    输入输出都是字符串，不会修改调用者的文件，也不会访问环境变量。
    自定义业务字段应在采集证据前自行删去，尤其是身份证、手机号和客户数据。
    """
    text = _URL_CREDENTIALS.sub(lambda m: m["scheme"] + REDACTED + "@", text)
    # 先隐藏方案后的真正凭据，避免后续赋值规则只隐藏 Bearer 而留下令牌。
    text = _AUTH_SCHEME.sub(lambda m: m["scheme"] + " " + REDACTED, text)
    text = _HEADER_LINE.sub(lambda m: m["prefix"] + REDACTED, text)
    text = _QUOTED_ASSIGNMENT.sub(lambda m: m["prefix"] + m["quote"] + REDACTED + m["quote"], text)
    text = _PLAIN_ASSIGNMENT.sub(lambda m: m["prefix"] + REDACTED, text)
    return text


def redact(value: Any) -> Any:
    """递归复制并脱敏 dict/list/tuple；原始对象保持不变。

    例如 ``redact({"headers": {"Authorization": "Bearer abc"}})`` 会隐藏整项。
    非字符串标量（数字、布尔、None）原样返回。循环引用替换成标记，避免递归崩溃。
    """
    return _redact(value, set())


def _redact(value: Any, active: set[int]) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if not isinstance(value, (Mapping, list, tuple)):
        return value
    identity = id(value)
    if identity in active:
        return "[CIRCULAR]"
    active.add(identity)
    try:
        if isinstance(value, Mapping):
            return {
                key: REDACTED if _is_sensitive_key(key) else _redact(item, active)
                for key, item in value.items()
            }
        result = [_redact(item, active) for item in value]
        return tuple(result) if isinstance(value, tuple) else result
    finally:
        active.remove(identity)
