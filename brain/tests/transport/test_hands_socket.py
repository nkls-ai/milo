"""The hands socket: JSON lines between the milo-mac MCP server and the brain, end to end through a real socket."""

import asyncio
import json
import os
import stat
from pathlib import Path


from milo.core.types import HandsError
from milo.mcp_server import HandsClient
from milo.services.hands import ToolOutput
from milo.transport.hands_socket import HandsSocketServer


async def fake_call(tool: str, args: object) -> ToolOutput:
    if tool == "boom":
        raise RuntimeError("bug")
    if tool == "click":
        raise HandsError("The user stopped you.")
    return ToolOutput(f"{tool} {json.dumps(args)}", "/x/shot.png" if tool == "screenshot" else "")


def with_server(path: Path, client_work):
    async def go():
        server = HandsSocketServer(path, fake_call)
        await server.start()
        try:
            return await asyncio.get_running_loop().run_in_executor(None, client_work)
        finally:
            await server.close()

    return asyncio.run(go())


def test_requests_and_answers_round_trip(sock_path):
    client = HandsClient(sock_path, timeout_s=5)
    answers = with_server(sock_path, lambda: [client.call("list_apps", {}), client.call("screenshot", {}),
                                              client.call("click", {"x": 1, "y": 2}), client.call("boom", {})])
    assert answers[0] == {"id": 1, "ok": True, "text": "list_apps {}", "image": ""}
    assert answers[1]["image"] == "/x/shot.png"
    assert answers[2] == {"id": 3, "ok": False, "error": "The user stopped you."}
    assert answers[3]["ok"] is False and "internal error" in answers[3]["error"]


def test_the_socket_is_private(sock_path):
    def check():
        return stat.S_IMODE(os.stat(sock_path).st_mode), stat.S_IMODE(os.stat(sock_path.parent).st_mode)

    assert with_server(sock_path, check) == (0o600, 0o700)
    assert not sock_path.exists(), "removed on close"


def test_garbage_gets_an_error_and_the_connection_stays_usable(sock_path):
    import socket

    def talk():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(str(sock_path))
            s.sendall(b"not json\n{\"id\": 2, \"tool\": \"list_apps\"}\n")
            stream = s.makefile("rb")
            return json.loads(stream.readline()), json.loads(stream.readline())

    bad, good = with_server(sock_path, talk)
    assert bad["ok"] is False and bad["error"].startswith("bad request")
    assert good == {"id": 2, "ok": True, "text": "list_apps {}", "image": ""}


def test_no_brain_is_a_plain_error(sock_path):
    assert HandsClient(sock_path).call("list_apps", {}) == {
        "ok": False, "error": "Milo's brain isn't reachable, so the Mac tools are off."}
