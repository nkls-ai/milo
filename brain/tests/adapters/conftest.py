from pathlib import Path

import pytest

from milo.adapters import load_builtin
from milo.core.registry import AdapterContext
from tests.fakes import FakeClock

load_builtin()


@pytest.fixture
def ctx(tmp_path: Path) -> AdapterContext:
    return AdapterContext(home=tmp_path / "home", state_dir=tmp_path / "home" / "state", clock=FakeClock())
