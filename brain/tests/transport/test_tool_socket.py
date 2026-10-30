"""ToolSocketServer against a real Unix socket under /tmp (macOS caps sun_path at 104 bytes)."""

import asyncio
import json
import shutil
import stat
import tempfile
from pathlib import Path

import pytest

from milo.transport.tool_socket import ToolSocketServer


@pytest.fixture
def sock_path():
    root = Path(tempfile.mkdtemp(dir="/tmp", prefix="milo-"))
    try:
        yield root / "run" / "tools.sock"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_requests_are_answered_with_their_id_concurrently(sock_path):
    release = asyncio.Event()

    async def handler(request: dict) -> dict:
        if request["op"] == "slow":
            await release.wait()
        return {"ok": True, "result": request["op"]}

    async def run():
        server = ToolSocketServer(sock_path, handler)
        await server.start()
        assert stat.S_IMODE(sock_path.stat().st_mode) == 0o600
        reader, writer = await asyncio.open_unix_connection(str(sock_path))
        writer.write(b'{"id": 1, "op": "slow"}\n{"id": 2, "op": "fast"}\nnot json\n')
        await writer.drain()
        first = json.loads(await asyncio.wait_for(reader.readline(), 2))
        release.set()
        second = json.loads(await asyncio.wait_for(reader.readline(), 2))
        writer.close()
        await server.close()
        return first, second

    first, second = asyncio.run(run())
    assert first == {"id": 2, "ok": True, "result": "fast"}, "a slow question doesn't hold up the next request"
    assert second == {"id": 1, "ok": True, "result": "slow"}
    assert not sock_path.exists()


def test_one_connection_can_have_only_a_few_requests_waiting(sock_path):
    # L5: each question queues behind the one before, so a helper in a loop could line them up without end.
    from milo.transport.tool_socket import BUSY, MAX_IN_FLIGHT

    release = asyncio.Event()
    handled = []

    async def handler(request: dict) -> dict:
        handled.append(request["id"])
        await release.wait()
        return {"ok": True, "result": request["id"]}

    async def run():
        server = ToolSocketServer(sock_path, handler)
        await server.start()
        reader, writer = await asyncio.open_unix_connection(str(sock_path))
        other_reader, other = await asyncio.open_unix_connection(str(sock_path))
        writer.write(b"".join(b'{"id": %d, "op": "confirm"}\n' % i for i in range(MAX_IN_FLIGHT + 2)))
        await writer.drain()
        refused = [json.loads(await asyncio.wait_for(reader.readline(), 2)) for _ in range(2)]
        other.write(b'{"id": 99, "op": "confirm"}\n')
        await other.drain()
        await asyncio.sleep(0.05)
        release.set()
        answered = sorted([json.loads(await asyncio.wait_for(reader.readline(), 2))["id"]
                           for _ in range(MAX_IN_FLIGHT)])
        writer.close()
        other.close()
        await server.close()
        return refused, answered

    refused, answered = asyncio.run(run())
    assert refused == [{"id": i, "ok": False, "error": BUSY} for i in (MAX_IN_FLIGHT, MAX_IN_FLIGHT + 1)]
    assert answered == list(range(MAX_IN_FLIGHT)) and 99 in handled, "another connection has its own room"
