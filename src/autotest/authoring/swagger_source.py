"""只读发现 Swagger UI 背后的同源 OpenAPI 文档。

只访问用户指定页面及有限个已知的文档配置地址。页面、配置和 JS 均视为不可信输入：
不跟随重定向，不把认证头发往其他 origin，不执行脚本，也不探测业务接口。
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import httpx
import yaml

from autotest.ai import AIError
from autotest.redaction import redact_text

MAX_SPEC_BYTES = 2 * 1024 * 1024
MAX_UI_BYTES = 256 * 1024
MAX_CONFIG_BYTES = 128 * 1024
MAX_REQUESTS = 8
_QUERY_KEYS = {"group", "url", "configUrl", "urls.primaryName"}
_DOC_PATH = re.compile(
    r"(?:^|/)(?:v[23]/api-docs(?:/[^/]*)?|swagger-resources(?:/[^/]*)?|"
    r"swagger-initializer\.js|[^/]+\.(?:json|ya?ml))$",
    re.I,
)
_SCRIPT_URL = re.compile(r"\b(?P<key>configUrl|url)\s*:\s*['\"](?P<value>[^'\"<>]{1,1024})['\"]")
_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*['\"](?P<value>[^'\"<>]+)['\"]", re.I)


def _origin(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise AIError("Swagger 文档地址必须是完整 HTTP(S) URL。")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise AIError("Swagger 文档地址端口无效。") from None
    if parts.username or parts.password:
        raise AIError("Swagger 文档地址不能内嵌账号密码；认证使用 --spec-auth-env。")
    return parts.scheme, parts.hostname.lower(), port


def _safe_query(url: str, *, ui: bool) -> str:
    parts = urlsplit(url)
    # Swagger UI 的 #/Tag/operation 是浏览器内导航，HTTP 请求不发送 fragment。
    if parts.fragment and not ui:
        raise AIError("原始 OpenAPI 文档地址不能带 #fragment。")
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key not in (_QUERY_KEYS if ui else {"group"}):
            raise AIError("文档 URL 仅支持 group 分组参数；UI 页面另支持 url/configUrl。")
        if not value or len(value) > 1024:
            raise AIError("Swagger URL 查询参数不能为空或超过长度限制。")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _same_origin(ui_url: str, candidate: str) -> str:
    resolved = urljoin(ui_url, candidate)
    if _origin(resolved) != _origin(ui_url):
        raise AIError("Swagger UI 引用的文档不在同一 origin；请直接提供获授权的原始文档地址。")
    if urlsplit(resolved).path.startswith("//"):
        raise AIError("Swagger 文档路径无效。")
    if not _DOC_PATH.search(urlsplit(resolved).path):
        raise AIError("Swagger UI 引用了非文档路径；请直接提供原始 OpenAPI 地址。")
    return _safe_query(resolved, ui=False)


def _context_base(ui_url: str) -> str:
    parts = urlsplit(ui_url)
    path_parts = parts.path.split("/")
    index = next(
        (i for i, item in enumerate(path_parts) if item.lower().startswith("swagger-ui")),
        len(path_parts) - 1,
    )
    prefix = "/".join(path_parts[:index]).rstrip("/") + "/"
    return urlunsplit((parts.scheme, parts.netloc, prefix, "", ""))


def _parse_yaml(text: str):
    try:
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text)):
            raise AIError("OpenAPI YAML 不接受别名引用，请导出 JSON。")
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def _is_spec(value) -> bool:
    return isinstance(value, dict) and bool(value.get("openapi") or value.get("swagger"))


def _select_group(resources, group: str | None, *, primary: str | None = None) -> str:
    if not resources:
        raise AIError("Swagger 配置中没有可用文档地址。")
    if group:
        matching = [item for item in resources if item[0] == group]
        if len(matching) != 1:
            names = ", ".join(redact_text(item[0]) for item in resources[:20])
            raise AIError(f"未找到文档分组 {redact_text(group)}；可选：{names}")
        return matching[0][1]
    if len(resources) == 1:
        return resources[0][1]
    if primary:
        matching = [item for item in resources if item[0] == primary]
        if len(matching) == 1:
            return matching[0][1]
    names = ", ".join(redact_text(item[0]) for item in resources[:20])
    raise AIError(f"Swagger UI 有多个文档分组：{names}；请用 --spec-group 指定。")


def _resource_url(value, group: str | None) -> str | None:
    if isinstance(value, list):
        resources = [
            (item.get("name"), item.get("location") or item.get("url"))
            for item in value
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("location") or item.get("url"), str)
        ]
        return _select_group(resources, group) if resources else None
    if isinstance(value, dict):
        urls = value.get("urls")
        if isinstance(urls, list) and urls:
            resources = [
                (item.get("name"), item.get("url"))
                for item in urls
                if isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and isinstance(item.get("url"), str)
            ]
            return _select_group(
                resources,
                group,
                primary=value.get("urls.primaryName") or value.get("urlsPrimaryName"),
            )
        if isinstance(value.get("url"), str):
            return value["url"]
    return None


def _hints(text: str) -> tuple[str | None, str | None]:
    if "SwaggerUIBundle" not in text and "SwaggerUI(" not in text:
        return None, None
    matches = {m.group("key"): m.group("value") for m in _SCRIPT_URL.finditer(text)}
    return matches.get("configUrl"), matches.get("url")


def read_remote_spec(
    source: str,
    *,
    header: str | None = None,
    group: str | None = None,
    client_factory=httpx.Client,
) -> str:
    """返回原始规范文本；最多 8 个 GET，全部同源且只读取文档相关路径。"""
    ui_like = "swagger-ui" in urlsplit(source).path.lower()
    initial = _safe_query(source, ui=ui_like)
    _origin(initial)
    headers = {"Authorization": header} if header else {}
    request_count = 0
    visited: set[str] = set()

    with client_factory(timeout=30, follow_redirects=False) as client:

        def fetch(url: str, limit: int, *, optional: bool = False) -> str | None:
            nonlocal request_count
            if url in visited:
                return None
            if request_count >= MAX_REQUESTS:
                raise AIError("Swagger UI 文档发现超过 8 个只读请求；请直接提供原始文档地址。")
            visited.add(url)
            request_count += 1
            try:
                with client.stream("GET", url, headers=headers) as response:
                    if optional and response.status_code in {404, 405}:
                        return None
                    if response.status_code != 200:
                        raise AIError(
                            f"Swagger 文档读取返回 HTTP {response.status_code}；请检查地址和认证。"
                        )
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > limit:
                            raise AIError("Swagger 文档或配置超过大小限制；请导出相关分组文档。")
                return content.decode("utf-8-sig")
            except (httpx.HTTPError, UnicodeDecodeError) as exc:
                if optional:
                    return None
                raise AIError("Swagger 文档下载失败，请检查网络、编码和文档认证。") from exc

        text = fetch(initial, MAX_SPEC_BYTES)
        assert text is not None
        if _is_spec(_parse_yaml(text)):
            return text
        if not ui_like or "swagger" not in text.lower() or "<html" not in text.lower():
            raise AIError("输入不是 OpenAPI/Swagger 文档，也不是可识别的 Swagger UI 页面。")
        if len(text.encode()) > MAX_UI_BYTES:
            raise AIError("Swagger UI 页面超过 256 KiB，请提供原始文档地址。")

        ui_parts = urlsplit(initial)
        ui_query = dict(parse_qsl(ui_parts.query, keep_blank_values=True))
        selected_group = group or ui_query.get("group") or ui_query.get("urls.primaryName")
        config_hint, url_hint = _hints(text)
        config_hint = ui_query.get("configUrl") or config_hint
        url_hint = ui_query.get("url") or url_hint
        base = _context_base(initial)

        # 官方初始化脚本可能承载 url/configUrl；只读取页面明示的同源固定文件名。
        for match in _SCRIPT_SRC.finditer(text):
            asset = match.group("value")
            if urlsplit(asset).path.rsplit("/", 1)[-1] != "swagger-initializer.js":
                continue
            asset_url = _same_origin(initial, asset)
            script = fetch(asset_url, MAX_UI_BYTES, optional=True)
            if script:
                script_config, script_url = _hints(script)
                config_hint = config_hint or script_config
                url_hint = url_hint or script_url
            break

        config_urls = [config_hint] if config_hint else []
        config_urls += [
            urljoin(base, "v3/api-docs/swagger-config"),
            urljoin(base, "swagger-resources"),
        ]
        if url_hint and not config_hint:
            config_urls.insert(0, url_hint)

        for hint in config_urls:
            if not hint:
                continue
            candidate = _same_origin(initial, hint)
            content = fetch(candidate, MAX_SPEC_BYTES, optional=True)
            if content is None:
                continue
            parsed = _parse_yaml(content)
            if _is_spec(parsed):
                return content
            resource = _resource_url(parsed, selected_group)
            if not resource:
                continue
            # Swagger resources 可能给出不带 context-path 的绝对路径，先按服务根解析，
            # 再尝试 UI 所在 context-path；两者始终同源、同认证头且只限文档路径。
            targets = [resource]
            if resource.startswith("/") and base != urljoin(initial, "/"):
                targets.append(urljoin(base, resource.lstrip("/")))
            for target in targets:
                resolved = _same_origin(initial, target)
                document = fetch(resolved, MAX_SPEC_BYTES, optional=True)
                if document and _is_spec(_parse_yaml(document)):
                    return document

        raise AIError(
            "Swagger UI 未找到同源 OpenAPI 文档；可用 --spec-group 选择分组，"
            "或提供 UI 实际加载的 JSON/YAML 地址。"
        )
