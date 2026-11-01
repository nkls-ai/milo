"""A tiny OpenAI-style server on a thread, for tests of Setup's model probe: /v1/models, Ollama's /api/tags, and
/v1/chat/completions streaming server-sent events."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOpenAI:
    def __init__(self, *, models=("llama3.2:3b", "qwen2.5:7b"), key: str = "", reply: str = "OK",
                 refuse_extras: bool = False, tags: bool = False):
        self.models = list(models)
        self.key = key
        self.reply = reply
        self.refuse_extras = refuse_extras
        self.tags = tags
        self.bodies: list[dict] = []
        self.headers: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, payload, kind="application/json"):
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _allowed(self):
                fake.headers.append(dict(self.headers))
                if fake.key and self.headers.get("Authorization") != f"Bearer {fake.key}":
                    self._send(401, {"error": {"message": "Invalid API Key"}})
                    return False
                return True

            def do_GET(self):
                if self.path == "/api/tags" and fake.tags:
                    return self._send(200, {"models": [{"name": m} for m in fake.models]})
                if self.path == "/v1/models" and not fake.tags:
                    if self._allowed():
                        self._send(200, {"data": [{"id": m} for m in fake.models]})
                    return
                self._send(404, {"error": "not found"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.bodies.append(body)
                if not self._allowed():
                    return
                if fake.refuse_extras and "stream_options" in body:
                    return self._send(400, {"error": {"message": "Unrecognized request argument: stream_options"}})
                if body["model"] not in fake.models:
                    return self._send(404, {"error": {"message": f"model '{body['model']}' not found"}})
                chunks = [{"choices": [{"delta": {"content": part}}]} for part in (fake.reply[:1], fake.reply[1:])]
                events = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
                self._send(200, events.encode(), "text/event-stream")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def dead_url() -> str:
    """An address where nothing listens."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = server.server_address[1]
    server.server_close()
    return f"http://127.0.0.1:{port}/v1"
