"""UnixSocketServer against a real Unix socket. Paths live under /tmp: macOS caps sun_path at 104 bytes."""

import asyncio
import json
import os
import shutil
import socket
import stat
import tempfile
from pathlib import Path

import pytest

from milo.core.events import Bubble, Command, StateChanged, TextInput, UiConfig
from milo.core.types import MiloState
from milo.transport.unix_socket import UnixSocketServer, peer_uid

TIMEOUT_S = 2
GREETING = [StateChanged(MiloState.IDLE), UiConfig("fn", "right_option")]


@pytest.fixture
def sock_path():
    root = Path(tempfile.mkdtemp(dir="/tmp", prefix="milo-"))
    try:
        yield root / "run" / "brain.sock"
    finally:
        shutil.rmtree(root, ignore_errors=True)


class Client:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader, self.writer = reader, writer

    @classmethod
    async def connect(cls, path: Path) -> "Client":
        return cls(*await asyncio.open_unix_connection(str(path)))

    async def read(self) -> dict:
        line = await asyncio.wait_for(self.reader.readline(), TIMEOUT_S)
        assert line, "server closed the connection"
        return json.loads(line)

    async def read_greeting(self) -> list[dict]:
        return [await self.read() for _ in GREETING]

    async def send(self, message: dict | bytes) -> None:
        self.writer.write(message if isinstance(message, bytes) else json.dumps(message).encode() + b"\n")
        await self.writer.drain()

    async def close(self) -> None:
        self.writer.close()
        await self.writer.wait_closed()


def serve(path: Path, scenario, *, fail_on: str | None = None) -> list[Command]:
    """Start a server, run `scenario(server, next_command)`, close it. Returns every command handled."""
    handled: list[Command] = []

    async def run():
        queue: asyncio.Queue[Command] = asyncio.Queue()

        async def on_command(command: Command) -> None:
            handled.append(command)
            queue.put_nowait(command)
            if isinstance(command, TextInput) and command.text == fail_on:
                raise RuntimeError("handler broke")

        async def next_command() -> Command:
            return await asyncio.wait_for(queue.get(), TIMEOUT_S)

        server = UnixSocketServer(path, on_command, lambda: list(GREETING))
        await server.start()
        try:
            await scenario(server, next_command)
        finally:
            await server.close()

    asyncio.run(run())
    return handled


def test_client_gets_the_greeting_first_then_broadcasts(sock_path):
    async def scenario(server, _):
        client = await Client.connect(sock_path)
        assert await client.read_greeting() == [e.to_wire() for e in GREETING]
        server.emit(Bubble("Hi Niklas!"))
        assert await client.read() == {"type": "bubble", "text": "Hi Niklas!"}
        await client.close()

    serve(sock_path, scenario)


def test_a_valid_command_reaches_the_handler(sock_path):
    async def scenario(server, next_command):
        client = await Client.connect(sock_path)
        await client.send({"type": "text", "text": "hello Milo"})
        assert await next_command() == TextInput("hello Milo")
        await client.close()

    serve(sock_path, scenario)


def test_bad_lines_are_dropped_and_the_connection_stays_open(sock_path):
    async def scenario(server, next_command):
        client = await Client.connect(sock_path)
        await client.read_greeting()
        await client.send(b"this is not json\n")
        await client.send({"type": "teleport"})
        await client.send({"type": "text", "text": "   "})
        await client.send(b"[1, 2, 3]\n")
        await client.send(b"\n")
        await client.send(b"\xff\xfe\n")
        await client.send(b"[" * 50_000 + b"\n")  # deep nesting: json raises RecursionError
        await client.send({"type": "text", "text": "still here"})
        assert await next_command() == TextInput("still here")
        server.emit(Bubble("and listening"))
        assert await client.read() == {"type": "bubble", "text": "and listening"}
        await client.close()

    assert serve(sock_path, scenario) == [TextInput("still here")]


def test_an_over_long_line_is_dropped_and_the_connection_stays_open(sock_path):
    async def scenario(server, next_command):
        client = await Client.connect(sock_path)
        await client.send(b'{"type": "text", "text": "' + b"a" * 200_000 + b'"}\n')
        await client.send({"type": "text", "text": "short"})
        assert await next_command() == TextInput("short")
        await client.close()

    assert serve(sock_path, scenario) == [TextInput("short")]


def test_a_handler_exception_does_not_kill_the_connection(sock_path):
    async def scenario(server, next_command):
        client = await Client.connect(sock_path)
        await client.read_greeting()
        await client.send({"type": "text", "text": "boom"})
        assert await next_command() == TextInput("boom")
        await client.send({"type": "text", "text": "after"})
        assert await next_command() == TextInput("after")
        server.emit(Bubble("alive"))
        assert await client.read() == {"type": "bubble", "text": "alive"}
        await client.close()

    serve(sock_path, scenario, fail_on="boom")


def test_every_client_gets_broadcasts(sock_path):
    async def scenario(server, _):
        a, b = await Client.connect(sock_path), await Client.connect(sock_path)
        await a.read_greeting()
        await b.read_greeting()
        server.emit(StateChanged(MiloState.THINKING))
        assert await a.read() == await b.read() == {"type": "state", "state": "thinking"}
        await a.close()
        await asyncio.sleep(0.05)
        server.emit(Bubble("only b"))
        assert await b.read() == {"type": "bubble", "text": "only b"}
        await b.close()

    serve(sock_path, scenario)


def test_a_stale_socket_file_is_replaced(sock_path):
    sock_path.parent.mkdir(parents=True)
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(sock_path))
    stale.close()  # the file stays behind, nobody listens on it
    assert sock_path.exists()

    async def scenario(server, next_command):
        client = await Client.connect(sock_path)
        await client.send({"type": "listen_stop"})
        assert (await next_command()).type == "listen_stop"
        await client.close()

    serve(sock_path, scenario)


def test_a_live_socket_makes_a_second_server_exit(sock_path):
    async def scenario(server, next_command):
        second = UnixSocketServer(sock_path, lambda c: asyncio.sleep(0), lambda: [])
        with pytest.raises(SystemExit, match="already running"):
            await second.start()
        assert sock_path.exists(), "the running brain keeps its socket"
        client = await Client.connect(sock_path)
        await client.send({"type": "listen_cancel"})
        assert (await next_command()).type == "listen_cancel"
        await client.close()

    serve(sock_path, scenario)


def test_socket_is_0600_and_its_directory_0700(sock_path):
    sock_path.parent.mkdir(mode=0o755, parents=True)
    os.chmod(sock_path.parent, 0o755)

    async def scenario(server, _):
        st = os.stat(sock_path)
        assert stat.S_ISSOCK(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o600
        assert stat.S_IMODE(os.stat(sock_path.parent).st_mode) == 0o700

    serve(sock_path, scenario)


def test_start_restores_the_umask(sock_path):
    before = os.umask(0o022)
    try:
        serve(sock_path, lambda server, _: asyncio.sleep(0))
        assert os.umask(0o022) == 0o022
    finally:
        os.umask(before)


def test_close_unlinks_the_socket_and_disconnects_clients(sock_path):
    async def run():
        server = UnixSocketServer(sock_path, lambda c: asyncio.sleep(0), lambda: list(GREETING))
        await server.start()
        assert sock_path.exists()
        client = await Client.connect(sock_path)
        await client.read_greeting()
        await asyncio.wait_for(server.close(), TIMEOUT_S)
        assert not sock_path.exists()
        assert await asyncio.wait_for(client.reader.read(), TIMEOUT_S) == b""
        server.emit(Bubble("nobody hears this"))  # no clients left, must not raise
        await server.close()  # idempotent

    asyncio.run(run())


def test_peer_uid_is_our_own_uid():
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        assert peer_uid(a) == os.getuid()
    finally:
        a.close()
        b.close()
    assert peer_uid(None) is None
