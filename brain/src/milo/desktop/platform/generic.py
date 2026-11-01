"""Fallback for other systems (the Qt desktop on macOS, for development): no global key reading or idle time."""
from __future__ import annotations

from .linux import LinuxKeys


class GenericKeys(LinuxKeys):
    def idle_s(self) -> float:
        return 0.0
