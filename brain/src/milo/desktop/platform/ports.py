"""What the desktop UI may ask of the operating system, and nothing else.

The controller and the views depend on these Protocols, never on `sys.platform`, Win32, AT-SPI or X11.
`milo.desktop.platform.create(home)` returns one `DesktopPlatform` with every part filled in for the OS it
runs on; an operation the OS can't do raises `NativeError` (safe to show) or reports itself unavailable in
`capabilities()`, so callers never need `hasattr` checks.

Threading: every method here is called on the Qt GUI thread and returns quickly. Native hooks and audio
callbacks run on their own threads and reach Qt only through signals.

## The ear signal (instant key feedback)

`HotkeySource.ear` is a Qt `Signal(str, str)`: `(kind, mode)`, with `mode` "talk" or "dictate". It fires in
the same frame as the key, before the brain can answer, mirroring the Mac's `Ear` (VoicePhase.swift):

- "armed": a bound key went down. It may still be a tap or a shortcut: show only a small light.
- "open": the hold is real (after ~80 ms), or a double tap locked recording on: Milo is listening.
- "caught": the key came up after a real hold (or a locked recording was stopped): the short "got it"
  beat before the words come back.
- "cancelled": a tap that didn't become a double tap, Esc, another key joining (a shortcut), or the
  key being rebound. Clear the light.

Every "armed" is followed by exactly one "caught" or "cancelled". "open" may come between them once.

`HotkeySource.hands_free` is a Qt `Signal(str)`: the mode a double tap locked on ("talk" or "dictate"), sent just
before its "open", and "" when that locked recording ends (before its "caught" or "cancelled"). It mirrors the
Mac's `model.handsFree = pushToTalk.locked`, for the capsule's hands-free look.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from .._native_types import BorrowRequired, Focus, NativeError

__all__ = ["BorrowRequired", "Corrections", "DesktopHands", "DesktopPlatform", "EAR_KINDS", "Focus",
           "FocusTracker", "HotkeySource", "MeetingAudio", "NativeError", "ScreenCapture", "TextInserter"]

EAR_KINDS = ("armed", "open", "caught", "cancelled")


@runtime_checkable
class HotkeySource(Protocol):
    """Global push-to-talk and shortcut keys. A QObject; its signals are delivered on the GUI thread.

    Signals:
    - `command(dict)`: a wire command to send to the brain as is (`listen_start`, `listen_confirm`,
      `listen_stop`, `listen_cancel`, `stop_all`, `whats_this`, `meeting_toggle`, `hands_stop`).
    - `ear(str, str)`: instant key feedback, see the module docstring.
    - `hands_free(str)`: the mode a double tap locked on, "" when it ends (module docstring).
    - `focus_requested()`: a bound key went down; remember the focused field now, before anything moves.
    - `status(str)`: a notice for the user, e.g. that global keys aren't available in this session.
    """

    command: Any
    ear: Any
    hands_free: Any
    focus_requested: Any
    status: Any

    def configure(self, event: dict) -> None:
        """Applies a `ui_config` event (dictate_key, talk_key, hands_free_max_s, whats_this_key, meeting_key)."""

    def start(self) -> None:
        """Installs the OS listener. Idempotent; reports failure through `status`, never raises."""

    def stop(self) -> None:
        """Removes the listener and cancels any recording in progress."""

    def set_session(self, on: bool) -> None:
        """While a hands session is on, the user's own key or mouse input means "take over" (`hands_stop`)."""

    def set_meeting(self, on: bool) -> None:
        """Keeps the meeting shortcut's toggle in step with the brain's meeting state."""

    def set_synthetic(self, busy: Callable[[], bool]) -> None:
        """`busy()` is True while Milo itself injects input; such events are ignored, never seen as the user's."""


@runtime_checkable
class FocusTracker(Protocol):
    """Which app and field the user is in, so dictation lands where they were when the key went down."""

    def remember_focus(self) -> None:
        """Captures the focused field now (called on key down, before Milo's overlay can take focus)."""

    def poll_focus(self) -> None:
        """Called about once a second; cheap metadata only, unless a corrections watch is active."""

    def arm_return_to_dictation_target(self) -> None:
        """The user finished a dictation from Milo's own window: allow one return to the captured field."""

    def context(self) -> dict:
        """`{"app": str | None, "idle_s": float}` for the brain's `context` command."""


@runtime_checkable
class TextInserter(Protocol):
    """Puts text into the remembered field: paste with the clipboard restored afterwards."""

    @property
    def input_busy(self) -> bool:
        """True while Milo is injecting keys, so the hotkey listener ignores them."""

    def paste_dictation(self, text: str, *, learn: bool = True) -> dict:
        """`{"pasted": True, "field": id, "app": name}` or `{"pasted": False, "why": "moved" | "no_field" |
        "secure" | "empty" | "keys_held", "error"?: str, "copied"?: True}`. Never raises for an ordinary refusal.
        A terminal gets the words typed (`"typed": True`) where the platform can. Dictation that couldn't be pasted
        is left on the clipboard (`"copied"`), except a password field's."""


@runtime_checkable
class Corrections(Protocol):
    """Learning from the user's own edits right after a dictation (ADR 21). Only short word pairs leave."""

    def set_learning(self, on: bool) -> None: ...

    def take_corrections(self) -> list[tuple[str, str]]:
        """Pending `(heard, meant)` pairs, emptied by the call; sent as `dictation_fixed`."""


@runtime_checkable
class ScreenCapture(Protocol):
    def capture(self, mode: str = "window") -> dict:
        """A look for the brain: `{"app", "window", "focused", "text", "selection"?, "image"?, "error"?}`.
        `mode` is "window" or "selection". Password fields and managers are never read."""


@runtime_checkable
class DesktopHands(Protocol):
    """The worker's hands (`hands_request`) and the app's own services (`app_request`)."""

    def hands_request(self, tool: str, args: dict) -> dict:
        """Runs one worker tool; raises `NativeError` (or `BorrowRequired`) with a sentence for the user."""

    def app_request(self, op: str, args: dict) -> dict:
        """`text.copy`, `text.write`, `text.unwrite`, `access.*`, `platform.capabilities`."""

    def session_event(self, event: dict) -> None:
        """`hands_session`, `hands_borrow` and `meeting_status` events, as they arrive."""


@runtime_checkable
class MeetingAudio(Protocol):
    def meeting_record(self, event: dict, send: Callable[[dict], Any]) -> None:
        """Starts or stops capture for a `meeting_record` event; chunks and status go out through `send`."""

    def pause_meeting(self, on: bool) -> None: ...


@runtime_checkable
class DesktopPlatform(FocusTracker, TextInserter, Corrections, ScreenCapture, DesktopHands, MeetingAudio,
                      Protocol):
    """Everything the desktop needs from the OS but the keys, which are a separate `HotkeySource`."""

    def capabilities(self) -> dict:
        """`{"accessibility", "global_input", "screen_capture", "clipboard", "meeting_loopback",
        "calendar", "contacts": bool, "detail": str}`."""

    def close(self) -> None: ...
