"""Use the same local transport as the application, including authentication on Windows."""
import asyncio
import os
from pathlib import Path

from milo import system

short_tempdir = "/tmp" if os.name != "nt" else str(Path(__file__).resolve().parents[2] / ".tools" / "test-local")
if os.name == "nt":
    Path(short_tempdir).mkdir(parents=True, exist_ok=True)


async def connect(path):
    sock = await asyncio.to_thread(system.connect_local, path, 3.0)
    sock.setblocking(False)
    return await asyncio.open_connection(sock=sock)
