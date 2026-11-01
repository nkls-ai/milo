"""Commands for the brain and its tools, in source checkouts and self-contained distributions."""
from __future__ import annotations

import sys
from pathlib import Path


def runtime_executable() -> str:
    if getattr(sys, "frozen", False):
        suffix = Path(sys.executable).suffix
        runtime = Path(sys.executable).with_name("Milo-runtime" + suffix)
        if runtime.is_file():
            return str(runtime)
    return sys.executable


def module_command(module: str, *arguments: str) -> tuple[str, ...]:
    flag = "--module" if getattr(sys, "frozen", False) else "-m"
    return (runtime_executable(), flag, module, *arguments)
