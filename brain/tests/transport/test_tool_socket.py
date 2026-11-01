from tests.local_transport import connect as local_connect
"""ToolSocketServer against a real Unix socket under /tmp (macOS caps sun_path at 104 bytes)."""

import asyncio
import json
import stat


from milo import system
from milo.transport.tool_socket import ToolSocketServer


def test_requests_are_answered_with_their_id_concurrently(sock_path):
    release = asyncio.Event()

    async def handler(request: dict) -> dict:
        if request["op"] == "slow":
            await release.wait()
        return {"ok": True, "result": request["op"]}

    async def run():
        server = ToolSocketServer(sock_path, handler)
        await server.start()
        assert system.owned_by_me(sock_path) and not system.open_to_others(sock_path)
        reader, writer = await local_connect(sock_path)
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
        reader, writer = await local_connect(sock_path)
        other_reader, other = await local_connect(sock_path)
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


def test_hanging_up_ends_what_the_connection_waited_for_so_dialling_again_makes_no_room(sock_path):
    from milo.transport import tool_socket

    cancelled = []

    async def handler(request: dict) -> dict:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(request["id"])
            raise
        return {"ok": True}

    async def run():
        server = ToolSocketServer(sock_path, handler)
        await server.start()
        _, writer = await local_connect(sock_path)
        writer.write(b"".join(b'{"id": %d, "op": "confirm"}\n' % i for i in range(3)))
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()
        await asyncio.sleep(0.05)
        left = len(server._running)
        # Many connections, each under its own cap: the total is capped too.
        conns = [await local_connect(sock_path) for _ in range(6)]
        for i, (_, w) in enumerate(conns):
            w.write(b"".join(b'{"id": %d, "op": "confirm"}\n' % (100 + 10 * i + j) for j in range(3)))
            await w.drain()
        refused = 0
        for r, _ in conns:
            try:
                while json.loads(await asyncio.wait_for(r.readline(), 0.2))["error"] == tool_socket.BUSY:
                    refused += 1
            except TimeoutError:
                pass
        for _, w in conns:
            w.close()
        await server.close()
        return left, refused

    left, refused = asyncio.run(run())
    assert sorted(cancelled[:3]) == [0, 1, 2] and left == 0, "the hung-up connection's requests ended with it"
    assert refused == 6 * 3 - tool_socket.MAX_IN_FLIGHT_ALL
