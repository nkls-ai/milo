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
