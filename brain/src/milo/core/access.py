"""What Milo may do on this computer, in words that fit any operating system (ADR 0025).

The brain only knows three needs and four answers. Which system switch a need is, how to ask for it, what a
refusal looks like and where to fix it belong to the app, which answers `access.*` requests (core/ports.py
`AppAccess`). A Windows or Linux app answers the same requests in its own way.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .types import AppRef


class Need(StrEnum):
    CONTROL = "control"
    """Control one app with scripts (Excel, Mail, Notes)."""
    UI = "ui"
    """Read and work other apps' windows: press buttons, fill in fields, click and type."""
    SCREEN = "screen"
    """See the screen's pixels: screenshots."""


class Access(StrEnum):
    YES = "yes"
    NO = "no"
    ASK = "ask"
    """Not decided yet: the system will ask the user once, the first time Milo tries."""
    UNKNOWN = "unknown"
    """The app can't tell (an older app, an app that isn't installed). Milo goes ahead as before."""


@dataclass(frozen=True)
class AccessAnswer:
    access: Access
    app: AppRef | None = None
    """For CONTROL: the app, with its bundle id once the app found it."""
    system: str = ""
    """The name of the system that asks, for Milo's words. "" says "your computer"."""
    label: str = ""
    """What the system calls the switch for this need, in its own words. "" for none."""
    button: str = ""
    """The button in the system's question that says yes. "" for none."""

    @classmethod
    def from_wire(cls, result: object, app: AppRef | None = None) -> AccessAnswer:
        """The app's answer to an `access.*` request. Anything it can't read is UNKNOWN."""
        if not isinstance(result, dict):
            return cls(Access.UNKNOWN, app)
        try:
            access = Access(str(result.get("access") or "unknown"))
        except ValueError:
            access = Access.UNKNOWN
        if app is not None:
            app = AppRef(str(result.get("app") or app.name), str(result.get("bundle") or app.bundle))
        return cls(access, app, str(result.get("system") or ""), str(result.get("label") or ""),
                   str(result.get("button") or ""))
