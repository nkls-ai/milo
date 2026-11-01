"""The desktop's OS boundary. Widgets and policy depend on these values, never OS handles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class NativeError(RuntimeError):
    """An operation could not be performed; safe to show to the user."""


class BorrowRequired(NativeError):
    def __init__(self, device: str):
        super().__init__(f"This needs the real {device}. May Milo borrow it for this step?")
        self.borrow = device


@dataclass(frozen=True)
class Focus:
    identity: str
    pid: int
    app: str
    window: str = ""
    title: str = ""
    role: str = ""
    secure: bool = False
    editable: bool = False
    text: str = ""
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    handle: Any = None
    window_title: str = ""
    window_rect: tuple[int, int, int, int] | None = None


class Accessibility(Protocol):
    def foreground_pid(self) -> int | None: ...
    def focus(self) -> Focus | None: ...
    def windows(self) -> list[Focus]: ...
    def activate(self, app: str) -> Focus: ...
    def elements(self, app: str = "") -> list[Focus]: ...
    def at_point(self, x: int, y: int) -> Focus | None: ...
    def press(self, target: Focus) -> None: ...
    def set_value(self, target: Focus, text: str) -> None: ...
    def selected_text(self, target: Focus) -> str: ...
    def selection_span(self, target: Focus) -> tuple[int, int] | None: ...
    def refresh(self, target: Focus) -> Focus | None: ...
    def focus_field(self, target: Focus) -> Focus: ...


class UnavailableAccessibility:
    def __init__(self, reason: str):
        self.reason = reason

    def focus(self) -> Focus | None:
        return None

    def windows(self) -> list[Focus]:
        raise NativeError(self.reason)

    def activate(self, app: str) -> Focus:
        raise NativeError(self.reason)

    def elements(self, app: str = "") -> list[Focus]:
        raise NativeError(self.reason)

    def at_point(self, x: int, y: int) -> Focus | None:
        raise NativeError(self.reason)

    def press(self, target: Focus) -> None:
        raise NativeError(self.reason)

    def set_value(self, target: Focus, text: str) -> None:
        raise NativeError(self.reason)

    def selected_text(self, target: Focus) -> str:
        return ""

    def focus_field(self, target: Focus) -> Focus:
        raise NativeError(self.reason)
