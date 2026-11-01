"""Native Windows boundaries: real DACLs, byte locks and authenticated transport."""
import asyncio
import json
import os
import socket
from pathlib import Path

import pytest

from milo import system

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows kernel integration")


def test_lock_excludes_another_open_handle_and_releases(tmp_path):
    path = tmp_path / "brain.lock"
    first = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    second = os.open(path, os.O_RDWR)
    try:
        assert system.try_lock(first)
        assert not system.try_lock(second)
        os.close(first)
        first = None
        assert system.try_lock(second)
    finally:
        if first is not None:
            os.close(first)
        os.close(second)


def test_secrets_are_owned_and_dacl_private(tmp_path):
    from milo.core.secrets import read_secret

    folder = tmp_path / "secrets"
    folder.mkdir()
    path = folder / "key"
    path.write_text("a-test-value", encoding="utf-8")
    assert read_secret(path, "Test key") == "a-test-value"
    assert system.owned_by_me(folder)
    assert not system.open_to_others(folder)
    fd = system.open_no_follow(path)
    try:
        assert system.owned_by_me(fd)
        assert not system.open_to_others(fd)
    finally:
        os.close(fd)


def test_instance_lock_writes_pid_and_rejects_another_brain(tmp_path):
    from milo.transport.instance_lock import acquire, AlreadyRunning

    path = tmp_path / "lock"
    fd = acquire(path)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        assert os.read(fd, 32).decode().strip() == str(os.getpid())
        with pytest.raises(AlreadyRunning):
            acquire(path)
    finally:
        os.close(fd)


def test_authenticated_stream_rejects_wrong_token_and_speaks_jsonl(tmp_path):
    path = tmp_path / "run" / "brain.sock"
    accepted = []

    async def run():
        async def client(reader, writer):
            assert system.peer_is_me(writer.get_extra_info("socket"))
            accepted.append(True)
            writer.write(await reader.readline())
            await writer.drain()

        server = await system.start_local_server(client, path)
        try:
            endpoint = json.loads(path.read_text(encoding="utf-8"))
            assert not system.open_to_others(path)
            reader, writer = await asyncio.open_connection("127.0.0.1", endpoint["port"])
            writer.write(b"wrong\n")
            await writer.drain()
            assert await asyncio.wait_for(reader.read(), 2) == b""
            writer.close()
            await writer.wait_closed()
            assert not accepted

            def exchange():
                with system.connect_local(path, 2) as sock:
                    sock.sendall(b'{"type":"text","text":"hello"}\n')
                    return sock.makefile("rb").readline()

            assert await asyncio.to_thread(exchange) == b'{"type":"text","text":"hello"}\n'
            assert accepted == [True]
        finally:
            server.close()
            await server.wait_closed()
    asyncio.run(run())


def test_undo_restores_unicode_bytes_and_routine_reads(tmp_path):
    source, target = tmp_path / "saved", tmp_path / "target"
    source.write_bytes("Grüße\r\nline\x00".encode())
    target.write_bytes(b"changed")
    system.restore_file(source, target, 0o600)
    assert target.read_bytes() == source.read_bytes()
    fd = system.open_child_no_follow(tmp_path, target.name)
    with os.fdopen(fd, "rb") as stream:
        assert stream.read() == source.read_bytes()
    system.unlink_child_no_follow(tmp_path, target.name)
    assert not target.exists()


def test_worker_cleanup_does_not_touch_unrelated_files(tmp_path):
    from milo.core.control import clear_steering

    work = tmp_path / "work"
    (work / "deep" / ".codex").mkdir(parents=True)
    (work / "deep" / ".codex" / "config.toml").write_text("foreign", encoding="utf-8")
    (work / "deep" / "CLAUDE.md").write_text("foreign", encoding="utf-8")
    (work / "keep.md").write_text("mine", encoding="utf-8")
    clear_steering(work)
    assert (work / "keep.md").read_text(encoding="utf-8") == "mine"
    assert list((work / "deep").iterdir()) == []
