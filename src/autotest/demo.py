"""无需公司环境即可练习的 HTTP API + Web 页面，仅绑定本机回环地址。

使用 Python 标准库，pytest 自动分配空闲端口；每个并行 worker 各自一个实例。
这是测试用的内存服务，关闭即清空数据，不用于真实业务部署。
"""

import json
import threading
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LOGIN_HTML = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>自动化练习系统</title><style>
body{font-family:system-ui;max-width:720px;margin:60px auto;padding:20px;background:#f7f8fc}
input,button{font:inherit;padding:10px;margin:8px}label{display:block}
button{cursor:pointer}li{margin:12px}main{background:white;padding:32px;border-radius:16px}
</style><main><h1>自动化练习系统</h1><p>练习账号 demo / demo123</p>
<form id="login"><label>用户名<input name="username" autocomplete="username" required></label>
<label>密码<input name="password" type="password" autocomplete="current-password" required></label>
<button type="submit">登录</button></form><p role="alert"></p>
<a href="/iframe">iframe 练习</a></main><script>
document.querySelector('form').onsubmit=async e=>{e.preventDefault();
const data=Object.fromEntries(new FormData(e.target));
const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify(data)});if(r.ok)location.href='/items';
else document.querySelector('[role=alert]').textContent='用户名或密码错误';};
</script></html>"""

ITEMS_HTML = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>我的项目</title><main><h1>我的项目</h1>
<form><label>项目名称<input name="name" required maxlength="80"></label>
<button type="submit">创建项目</button></form><p role="alert"></p><ul id="items"></ul></main>
<script>
async function refresh(){const r=await fetch('/api/items');if(r.status===401){location.href='/';return;}
const data=await r.json();document.querySelector('#items').replaceChildren();
for(const item of data.items){const li=document.createElement('li');li.dataset.itemId=item.id;
const label=document.createElement('span');label.dataset.testid='item-name';label.textContent=item.name;
const button=document.createElement('button');button.textContent='删除 '+item.name;
button.onclick=async()=>{await fetch('/api/items/'+item.id,{method:'DELETE'});await refresh();};
li.append(label,button);document.querySelector('#items').append(li);}}
document.querySelector('form').onsubmit=async e=>{e.preventDefault();
const data=Object.fromEntries(new FormData(e.target));
const r=await fetch('/api/items',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify(data)});if(r.ok){e.target.reset();await refresh();}
else document.querySelector('[role=alert]').textContent='创建失败';};refresh();
</script></html>"""

IFRAME_HTML = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>iframe 练习</title>
<h1>嵌入式页面</h1><iframe title="联系表单" src="/contact"></iframe></html>"""

CONTACT_HTML = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>联系表单</title>
<form><label>留言<input name="message" required></label><button>提交留言</button></form>
<p role="status"></p><script>document.querySelector('form').onsubmit=e=>{e.preventDefault();
document.querySelector('[role=status]').textContent='已收到：'+e.target.message.value;};</script></html>"""


class DemoServer:
    """with DemoServer() as server 自动启动和清理，不占用固定端口。"""

    def __init__(self, port: int = 0):
        self._lock = threading.Lock()
        self._sessions: set[str] = set()
        self._items: dict[str, dict] = {}
        state = self

        class Handler(BaseHTTPRequestHandler):
            # 关闭标准库的逐请求日志，避免在控制台泄露 URL 查询信息。
            def log_message(self, format, *args):
                pass

            def reply(self, status: int, payload=None, *, html=None, cookie=None):
                body = (
                    html.encode("utf-8")
                    if html is not None
                    else json.dumps(payload, ensure_ascii=False).encode("utf-8")
                )
                if status == 204:
                    body = b""
                self.send_response(status)
                self.send_header(
                    "Content-Type",
                    "text/html; charset=utf-8" if html is not None else "application/json",
                )
                self.send_header("Content-Length", str(len(body)))
                if cookie:
                    self.send_header("Set-Cookie", cookie)
                self.end_headers()
                self.wfile.write(body)

            def read_json(self):
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 65536:
                        raise ValueError("请求体大小错误")
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError("必须是 JSON 对象")
                    return payload
                except (ValueError, UnicodeDecodeError):
                    self.reply(400, {"error": "invalid_json"})
                    return None

            def authenticated(self):
                authorization = self.headers.get("Authorization", "")
                token = authorization.removeprefix("Bearer ")
                cookies = SimpleCookie()
                cookies.load(self.headers.get("Cookie", ""))
                if not token and "session" in cookies:
                    token = cookies["session"].value
                with state._lock:
                    return token in state._sessions

            def do_GET(self):
                path = urlsplit(self.path).path
                pages = {
                    "/": LOGIN_HTML,
                    "/items": ITEMS_HTML,
                    "/iframe": IFRAME_HTML,
                    "/contact": CONTACT_HTML,
                }
                if path in pages:
                    return self.reply(200, html=pages[path])
                if path == "/health":
                    return self.reply(200, {"status": "ok"})
                if path == "/api/items" or path.startswith("/api/items/"):
                    if not self.authenticated():
                        return self.reply(401, {"error": "unauthorized"})
                    with state._lock:
                        if path == "/api/items":
                            data = {"items": list(state._items.values())}
                        else:
                            data = state._items.get(path.rsplit("/", 1)[-1])
                    return self.reply(
                        200 if data is not None else 404, data or {"error": "not_found"}
                    )
                return self.reply(404, {"error": "not_found"})

            def do_POST(self):
                path = urlsplit(self.path).path
                payload = self.read_json()
                if payload is None:
                    return
                if path == "/api/login":
                    if payload.get("username") != "demo" or payload.get("password") != "demo123":
                        return self.reply(401, {"error": "invalid_credentials"})
                    token = uuid.uuid4().hex
                    with state._lock:
                        state._sessions.add(token)
                    return self.reply(
                        200,
                        {"token": token, "user": {"name": "demo"}},
                        cookie=f"session={token}; HttpOnly; SameSite=Strict; Path=/",
                    )
                if path == "/api/items":
                    if not self.authenticated():
                        return self.reply(401, {"error": "unauthorized"})
                    name = payload.get("name")
                    if not isinstance(name, str) or not name.strip() or len(name) > 80:
                        return self.reply(422, {"error": "invalid_name"})
                    item = {"id": uuid.uuid4().hex, "name": name.strip()}
                    with state._lock:
                        state._items[item["id"]] = item
                    return self.reply(201, item)
                return self.reply(404, {"error": "not_found"})

            def do_DELETE(self):
                path = urlsplit(self.path).path
                if not path.startswith("/api/items/"):
                    return self.reply(404, {"error": "not_found"})
                if not self.authenticated():
                    return self.reply(401, {"error": "unauthorized"})
                with state._lock:
                    item = state._items.pop(path.rsplit("/", 1)[-1], None)
                return self.reply(204 if item else 404, {"error": "not_found"})

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"

    def start(self) -> "DemoServer":
        self._thread.start()
        return self

    def close(self) -> None:
        if self._thread.is_alive():
            self._server.shutdown()
            self._thread.join(timeout=5)
        self._server.server_close()

    def __enter__(self) -> "DemoServer":
        return self.start()

    def __exit__(self, *args) -> None:
        self.close()
