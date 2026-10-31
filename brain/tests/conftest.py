import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def sock_path():
    """A Unix socket path in a fresh folder under /tmp that doesn't exist yet: macOS caps socket paths at 104
    bytes, too short for pytest's tmp_path."""
    root = Path(tempfile.mkdtemp(dir="/tmp", prefix="milo-"))
    try:
        yield root / "run" / "milo.sock"
    finally:
        shutil.rmtree(root, ignore_errors=True)
