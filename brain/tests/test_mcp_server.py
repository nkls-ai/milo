"""milo-mac speaks MCP over stdio and maps each tool call to one hands socket request."""

import io
import json
import subprocess
import sys

from milo.core.hands import BY_NAME, INSTRUCTIONS, TOOLS
from milo.mcp_server import handle, serve, tool_result

ORDER = ["list_apps", "open_app", "sheet_write", "sheet_read", "write_document", "window_text", "ax_tree", "ax_find", "ax_press",
         "ax_set_value", "run_applescript", "screenshot", "click", "type", "key", "scroll"]


class FakeClient:
    def __init__(self, answer: dict):
        self.answer = answer
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, args: dict) -> dict:
        self.calls.append((tool, args))
        return self.answer


def rpc(method: str, params: dict | None = None, id: int | None = 1) -> dict:
    message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    return message if id is None else {**message, "id": id}


def test_initialize_announces_tools_and_the_route_order():
    result = handle(rpc("initialize", {"protocolVersion": "2025-03-26"}), FakeClient({}))["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "milo-mac"
    assert result["instructions"] == INSTRUCTIONS


def test_tools_list_has_every_tool_in_preference_order_with_strict_schemas():
    tools = handle(rpc("tools/list"), FakeClient({}))["result"]["tools"]
    assert [t["name"] for t in tools] == ORDER == [t.name for t in TOOLS]
    for tool in tools:
        assert tool["inputSchema"]["additionalProperties"] is False
        assert set(tool["inputSchema"]["required"]) <= set(tool["inputSchema"]["properties"])
    assert "prefer ax_press" in BY_NAME["click"].description


def test_a_call_is_forwarded_as_is_and_its_text_comes_back():
    client = FakeClient({"ok": True, "text": "Clicked “Save” in Excel.", "image": ""})
    response = handle(rpc("tools/call", {"name": "click", "arguments": {"x": 3, "y": 4}}, id=7), client)
    assert client.calls == [("click", {"x": 3, "y": 4})]
    assert response == {"jsonrpc": "2.0", "id": 7, "result": {
        "content": [{"type": "text", "text": "Clicked “Save” in Excel."}], "isError": False}}


def test_errors_become_tool_errors_the_model_can_read():
    result = tool_result({"ok": False, "error": "The user stopped you."})
    assert result == {"content": [{"type": "text", "text": "The user stopped you."}], "isError": True}


def test_a_screenshot_becomes_an_image_block(tmp_path):
    png = tmp_path / "shot.png"
    png.write_bytes(b"\x89PNG fake")
    result = tool_result({"ok": True, "text": "Screenshot, 2x2 pixels.", "image": str(png)})
    assert result["content"][1] == {"type": "image", "data": "iVBORyBmYWtl", "mimeType": "image/png"}
    missing = tool_result({"ok": True, "text": "x", "image": str(tmp_path / "gone.png")})
    assert missing["content"][1]["text"] == "(The screenshot file could not be read.)"


def test_notifications_get_no_answer_and_unknown_methods_an_error():
    client = FakeClient({})
    assert handle(rpc("notifications/initialized", id=None), client) is None
    assert handle(rpc("resources/list"), client)["error"]["code"] == -32601
    assert handle(rpc("ping"), client)["result"] == {}
    assert handle(rpc("tools/call", {"name": 3}), client)["error"]["code"] == -32602


def test_serve_reads_and_writes_one_message_per_line():
    stdin = io.StringIO("\n".join([json.dumps(rpc("initialize")), json.dumps(rpc("notifications/initialized", id=None)),
                                   "{broken", json.dumps(rpc("tools/list", id=2))]) + "\n")
    stdout = io.StringIO()
    serve(FakeClient({}), stdin, stdout)
    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [m.get("id") for m in lines] == [1, None, 2]
    assert lines[1]["error"]["code"] == -32700


def test_it_runs_as_a_module_without_a_brain(tmp_path):
    """What the worker CLI does: start it with the brain's interpreter and call a tool."""
    messages = [rpc("initialize"), rpc("tools/call", {"name": "list_apps", "arguments": {}}, id=2)]
    done = subprocess.run([sys.executable, "-m", "milo.mcp_server", "--socket", str(tmp_path / "none.sock")],
                          input="".join(json.dumps(m) + "\n" for m in messages), capture_output=True, text=True,
                          timeout=20)
    assert done.returncode == 0, done.stderr
    answers = [json.loads(line) for line in done.stdout.splitlines()]
    assert answers[1]["result"]["isError"] is True
    assert "isn't reachable" in answers[1]["result"]["content"][0]["text"]
