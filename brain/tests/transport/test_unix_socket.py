from tests.local_transport import connect as local_connect
"""UnixSocketServer against a real Unix socket. Paths live under /tmp: macOS caps sun_path at 104 bytes."""

import asyncio
import json
import os
import socket
import stat
from pathlib import Path

import pytest

from milo.core.events import Bubble, Command, Level, StateChanged, TextInput, UiConfig
from milo.core.types import MiloState
from milo.system.posix import peer_uid
from milo.transport.unix_socket import UnixSocketServer

TIMEOUT_S = 2
GREETING = [StateChanged(MiloState.IDLE), UiConfig("fn", "right_option")]


class Client:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader, self.writer = reader, writer

    @classmethod
    async def connect(cls, path: Path) -> "Client":
        return cls(*await local_connect(path))

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
    if os.name == "nt":
        sock_path.write_text("{}", encoding="utf-8")  # an endpoint left by a stopped Windows brain
    else:
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX peer credentials and modes; Windows tests authenticated IPC")
def test_socket_is_0600_and_its_directory_0700(sock_path):
    sock_path.parent.mkdir(mode=0o755, parents=True)
    os.chmod(sock_path.parent, 0o755)

    async def scenario(server, _):
        st = os.stat(sock_path)
        assert stat.S_ISSOCK(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o600
        assert stat.S_IMODE(os.stat(sock_path.parent).st_mode) == 0o700

    serve(sock_path, scenario)


@pytest.mark.skipif(os.name == "nt", reason="POSIX peer credentials and modes; Windows tests authenticated IPC")
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


def test_stopping_serve_forever_does_not_wait_for_connected_clients(sock_path):
    """The app stops the brain with SIGTERM while still connected; the brain must not wait for it to hang up."""
    async def run():
        server = UnixSocketServer(sock_path, lambda c: asyncio.sleep(0), lambda: list(GREETING))
        serving = asyncio.create_task(server.serve_forever())
        while not sock_path.exists():
            await asyncio.sleep(0.01)
        client = await Client.connect(sock_path)
        await client.read_greeting()
        serving.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(serving, TIMEOUT_S)
        assert not sock_path.exists()
        assert await asyncio.wait_for(client.reader.read(), TIMEOUT_S) == b""

    asyncio.run(run())


@pytest.mark.skipif(os.name == "nt", reason="POSIX peer credentials and modes; Windows tests authenticated IPC")
def test_peer_uid_is_our_own_uid():
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        assert peer_uid(a) == os.getuid()
    finally:
        a.close()
        b.close()
    assert peer_uid(None) is None


def test_the_last_client_hanging_up_is_reported_once_the_others_are_gone(sock_path):
    gone: list[int] = []

    async def run():
        server = UnixSocketServer(sock_path, lambda c: asyncio.sleep(0), lambda: list(GREETING),
                                  on_disconnect=lambda: gone.append(1))
        await server.start()
        try:
            first, second = await Client.connect(sock_path), await Client.connect(sock_path)
            await first.read_greeting()
            await second.read_greeting()
            await first.close()
            await asyncio.sleep(0.05)
            assert gone == [], "another app is still connected"
            await second.close()
            await asyncio.sleep(0.05)
            assert gone == [1]
        finally:
            await server.close()
        assert gone == [1], "closing the server isn't an app going away"

    asyncio.run(run())


def test_an_app_that_stops_reading_gets_no_more_levels_and_is_cut_off_when_it_hangs(sock_path):
    # M1 in docs/review/2026-10-30.md: emit() queued without limit, 20,000 levels left 630 KB waiting.
    gone: list[int] = []

    async def run():
        server = UnixSocketServer(sock_path, lambda c: asyncio.sleep(0), lambda: list(GREETING),
                                  on_disconnect=lambda: gone.append(1), soft_limit=64 * 1024,
                                  hard_limit=1024 * 1024)
        await server.start()
        try:
            client = await Client.connect(sock_path)  # never reads, like an app whose main thread hangs
            await asyncio.sleep(0.05)
            writer = next(iter(server._clients))
            for _ in range(50_000):
                server.emit(Level(0.5))
            assert writer.transport.get_write_buffer_size() < 64 * 1024 + 100, "levels stop at the soft limit"
            server.emit(Bubble("still here"))
            assert writer.transport.get_write_buffer_size() > 64 * 1024, "real events still go out"
            for _ in range(200):
                server.emit(Bubble("x" * 10_000))
            await asyncio.sleep(0.05)
            assert not server.connected() and gone == [1], "a hung app is cut off and may reconnect"
            await client.close()
        finally:
            await server.close()

    asyncio.run(run())


def test_a_request_goes_to_the_newest_app_only_and_its_hanging_up_is_reported(sock_path):
    # M2 in docs/review/2026-10-30.md: requests were broadcast, so two apps would both click, type and add
    # the reminder.
    gone: list[int] = []

    async def run():
        server = UnixSocketServer(sock_path, lambda c: asyncio.sleep(0), lambda: list(GREETING))
        server.on_client_gone.append(gone.append)
        await server.start()
        try:
            old, new = await Client.connect(sock_path), await Client.connect(sock_path)
            await old.read_greeting()
            await new.read_greeting()
            assert server.request(Bubble("only one of you")) == 2
            assert await new.read() == {"type": "bubble", "text": "only one of you"}
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(old.reader.readline(), 0.1)
            await new.close()
            await asyncio.sleep(0.05)
            assert gone == [2]
            assert server.request(Bubble("now you")) == 1, "the app still here answers from now on"
            assert await old.read() == {"type": "bubble", "text": "now you"}
            await old.close()
            await asyncio.sleep(0.05)
            assert server.request(Bubble("nobody")) is None
        finally:
            await server.close()

    asyncio.run(run())


@pytest.mark.parametrize("hello", [b'{"type": "observe"}', b'{"type":"observe"}', b' { "type" : "observe" } '])
def test_an_observer_sends_commands_but_never_gets_the_apps_requests(sock_path, hello):
    """A test driver (scripts/drive-milo) talks to the running brain while the real app keeps doing the work."""
    seen: list = []

    async def handle(command):
        seen.append(command)

    async def run():
        server = UnixSocketServer(sock_path, handle, lambda: list(GREETING))
        await server.start()
        try:
            app = await Client.connect(sock_path)
            await app.read_greeting()
            driver = await Client.connect(sock_path)
            await driver.read_greeting()
            driver.writer.write(hello + b'\n{"type": "text", "text": "open YouTube"}\n')
            await driver.writer.drain()
            await asyncio.sleep(0.05)
            assert [c.type for c in seen] == ["text"], "observe is the transport's own, the text goes on"
            assert server.request(Bubble("for the app")) == 1, "the app, though the driver is newer"
            assert await app.read() == {"type": "bubble", "text": "for the app"}
            await app.close()
            await asyncio.sleep(0.05)
            assert not server.connected() and server.request(Bubble("nobody")) is None, "an observer isn't an app"
            await driver.close()
        finally:
            await server.close()

    asyncio.run(run())


@pytest.mark.skipif(os.name == "nt", reason="POSIX peer credentials and modes; Windows tests authenticated IPC")
def test_a_peer_whose_user_the_mac_cant_tell_is_refused(monkeypatch):
    # L3: macOS always answers LOCAL_PEERCRED, so no answer there means something is off: refuse.
    import sys

    from milo.system import posix
    from milo.transport import unix_socket

    monkeypatch.setattr(posix, "peer_uid", lambda sock: None)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert not unix_socket.same_user(None)
    monkeypatch.setattr(sys, "platform", "linux")
    assert unix_socket.same_user(None), "elsewhere the 0700 run/ folder is the check"
    monkeypatch.setattr(posix, "peer_uid", lambda sock: os.getuid() + 1)
    assert not unix_socket.same_user(None)
