from tests.local_transport import short_tempdir
"""milo.system: one module per OS family with the same functions, so a Windows port fills in one file."""

import asyncio
import inspect
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from milo import system
from milo.system import posix, windows


@pytest.mark.parametrize("name", system.FUNCTIONS)
def test_each_os_family_has_every_function_with_the_same_signature(name):
    assert inspect.signature(getattr(posix, name)) == inspect.signature(getattr(windows, name))
    assert getattr(system, name) is getattr(windows if os.name == "nt" else posix, name)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode and Unix-socket behavior; Windows has native tests")
def test_the_lock_is_exclusive_between_open_files(tmp_path):
    path = tmp_path / "lock"
    first, second = os.open(path, os.O_RDWR | os.O_CREAT), os.open(path, os.O_RDWR)
    try:
        assert posix.try_lock(first)
        assert not posix.try_lock(second), "flock locks per open file, so a second open of it is turned away"
    finally:
        os.close(first)
        os.close(second)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode and Unix-socket behavior; Windows has native tests")
def test_private_and_owned(tmp_path):
    folder = tmp_path / "secrets"
    folder.mkdir(mode=0o755)
    assert posix.owned_by_me(folder.lstat()) and posix.open_to_others(folder.lstat())
    posix.make_private(folder, 0o700)
    assert not posix.open_to_others(folder.lstat())


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode and Unix-socket behavior; Windows has native tests")
def test_a_local_server_is_private_and_reachable():
    root = Path(tempfile.mkdtemp(dir=short_tempdir, prefix="milo-"))  # AF_UNIX paths must stay short
    path = root / "run" / "x.sock"

    async def run():
        async def client(reader, writer):
            writer.write(b"hi\n")
            await writer.drain()
            writer.close()

        server = await posix.start_local_server(client, path)
        try:
            assert path.stat().st_mode & 0o777 == 0o600 and path.parent.stat().st_mode & 0o777 == 0o700
            sock = await asyncio.to_thread(posix.connect_local, path, 2.0)
            with sock:
                assert posix.peer_is_me(sock)
                assert await asyncio.to_thread(sock.makefile("rb").readline) == b"hi\n"
        finally:
            server.close()
            await server.wait_closed()

    try:
        asyncio.run(run())
        with pytest.raises(OSError):
            posix.connect_local(root / "nobody.sock")
    finally:
        shutil.rmtree(root, ignore_errors=True)
