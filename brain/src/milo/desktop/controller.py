"""Routes the brain's events to the view models and the OS's work to the platform layer (MiloController.swift).

No view and no OS call lives here: views are QML bound to the view models, OS work goes through
`platform.ports` (DesktopPlatform, HotkeySource) and the office actor.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from .platform.ports import DesktopPlatform, HotkeySource
from .viewmodels.conversations import ConversationsViewModel
from .viewmodels.navigation import RouteViewModel
from .viewmodels.presence import PresenceViewModel
from .viewmodels.store import StoreViewModel
from .viewmodels.window import RECONNECTING, WindowViewModel
from .viewmodels.working import WorkingViewModel

CONTEXT_MS = 15_000
FOCUS_MS = 1_000
REQUESTS = {"look_request": "look_result", "hands_request": "hands_result", "app_request": "app_response"}
QUIET_FAILURES = ("context", "meeting_recording", "dictation_fixed")
NO_DESKTOP = "Desktop integration is unavailable"


class ViewModels:
    """Everything QML binds to, made together so their links are in one place."""

    def __init__(self, scheduler=None, parent: QObject | None = None):
        self.route = RouteViewModel(parent=parent)
        self.presence = PresenceViewModel(scheduler, parent=parent)
        self.working = WorkingViewModel(parent)
        self.conversations = ConversationsViewModel(self.route, parent=parent)
        self.store = StoreViewModel(parent=parent)
        self.window = WindowViewModel(parent)
        rows = self.conversations.entries
        self.window.follow(lambda: rows.rows[-1] if rows.rows else None)

    def context(self) -> dict[str, QObject]:
        """The names QML knows them by."""
        return {"presence": self.presence, "working": self.working, "route": self.route,
                "conversations": self.conversations, "entries": self.conversations.entries, "store": self.store,
                "window": self.window}


class DesktopController(QObject):
    window_requested = Signal()
    native_command = Signal(dict)

    def __init__(self, home: Path, views: ViewModels, connection=None, native: DesktopPlatform | None = None,
                 hotkeys: HotkeySource | None = None, *, office=None, copy: Callable[[str], None] = lambda text: None,
                 parent=None):
        super().__init__(parent)
        self.home, self.views, self.connection = home, views, connection
        self.native, self.hotkeys, self.office, self._copy = native, hotkeys, office, copy
        self.native_command.connect(self.send)
        for source in (views.presence, views.conversations):
            source.command.connect(self.send)
        views.window.sender = self.send
        views.window.listenRequested.connect(self.listen)
        views.window.listenStopRequested.connect(self.stop_listening)
        views.window.copyRequested.connect(copy)
        views.presence.copyRequested.connect(copy)
        views.presence.openRequested.connect(self.open_window)
        views.presence.stopRequested.connect(lambda: self.send({"type": "stop_all"}))
        views.presence.cancelRequested.connect(lambda: self.send({"type": "listen_cancel"}))
        views.store.confirmationsChanged.connect(self._waiting)
        views.store.draftsChanged.connect(self._waiting)
        if connection is not None:
            connection.event.connect(self.on_event)
            connection.connection_changed.connect(self.on_connection)
        if hotkeys is not None:
            hotkeys.command.connect(self.from_hotkey)
            hotkeys.ear.connect(views.presence.ear)
            hotkeys.hands_free.connect(views.presence.set_hands_free)
            hotkeys.status.connect(lambda text: views.window.set(notice=text))
            if native is not None:
                hotkeys.focus_requested.connect(native.remember_focus)
                hotkeys.set_synthetic(lambda: native.input_busy)
        self._timers: list[QTimer] = []
        if native is not None:
            self._every(FOCUS_MS, self._poll_focus)
            self._every(CONTEXT_MS, self.context)

    def _every(self, ms: int, work: Callable[[], None]) -> None:
        timer = QTimer(self)
        timer.setInterval(ms)
        timer.timeout.connect(work)
        timer.start()
        self._timers.append(timer)

    # ---- out to the brain

    def send(self, command: dict) -> bool:
        if command.get("type") in ("stop_all", "hands_stop") and self.office is not None:
            self.office.cancel()
        if self.connection is None:
            return False
        sent = bool(self.connection.send(command))
        if not sent and command.get("type") not in QUIET_FAILURES:
            self.views.window.set(notice=RECONNECTING)
        return sent

    def from_hotkey(self, command: dict) -> None:
        if command.get("type") == "whats_this" and "capture" not in command and self.native is not None:
            command = {"type": "whats_this", "capture": self.native.capture("selection")}
        self.send(command)

    def listen(self, mode: str) -> None:
        """The window's hold-to-talk button: the same beat on Milo as a key."""
        self.views.presence.ear("armed", mode)
        self.views.presence.ear("open", mode)
        if self.native is not None:
            self.native.remember_focus()
        self.send({"type": "listen_start", "mode": mode})

    def stop_listening(self) -> None:
        mode = self.views.presence.model.last_mode
        if self.views.presence.model.state == "dictating" and self.native is not None:
            self.native.arm_return_to_dictation_target()
        self.views.presence.ear("caught", mode)
        self.send({"type": "listen_stop"})

    def context(self) -> None:
        app, idle = None, 0.0
        if self.native is not None:
            try:
                data = self.native.context()
                app, idle = data.get("app"), data.get("idle_s", 0.0)
            except Exception:
                pass
        self.views.presence.set_idle(float(idle or 0.0))
        self.send({"type": "context", "app": app, "idle_s": idle})

    def _poll_focus(self) -> None:
        self.native.poll_focus()
        fixes = self.native.take_corrections()
        if fixes:
            # The wire wants {heard, meant} objects; the platform hands (heard, meant) pairs.
            self.send({"type": "dictation_fixed", "fixes": [{"heard": h, "meant": m} for h, m in _pairs(fixes)]})

    def open_window(self) -> None:
        self.window_requested.emit()
        if self.views.window.connected:
            self.send({"type": "get_history"})
            self.send({"type": "get_conversations"})

    # ---- in from the brain

    def on_connection(self, connected: bool) -> None:
        views = self.views
        views.presence.set_connected(connected)
        views.window.set_connected(connected)
        if connected:
            for request in ("get_history", "get_conversations", "get_settings"):
                self.send({"type": request})
            self.context()
        else:
            views.store.lost()
            views.working.reset()

    def on_event(self, event: dict) -> None:
        kind = str(event.get("type", ""))
        if kind in REQUESTS:
            self._request(event)
            return
        if kind == "dictation":
            self._dictation(str(event.get("text", "")))
            return
        self._native(kind, event)
        views = self.views
        views.presence.apply(event)
        if kind == "level":
            return  # twenty a second: Milo's meter only
        views.working.apply(event)
        views.conversations.apply(event)
        views.store.apply(event)
        views.window.apply(event)

    def _native(self, kind: str, event: dict) -> None:
        """The parts of an event the OS layer acts on, before the views show it."""
        if kind == "ui_config" and self.hotkeys is not None:
            self.hotkeys.configure(event)
        elif kind == "settings" and self.native is not None:
            for setting in event.get("settings") or []:
                if setting.get("section") == "dictation" and setting.get("key") == "learn":
                    self.native.set_learning(bool(setting.get("value")))
        if kind == "meeting_status" and self.hotkeys is not None:
            self.hotkeys.set_meeting(event.get("phase") in ("recording", "paused"))
        if kind == "hands_session" and self.hotkeys is not None:
            self.hotkeys.set_session(bool(event.get("on")))
        if kind in ("hands_session", "hands_borrow", "meeting_status") and self.native is not None:
            self.native.session_event(event)
        if kind == "meeting_record":
            if self.native is not None:
                self.native.meeting_record(event, self.native_command.emit)
            else:
                self.send({"type": "meeting_recording", "id": str(event.get("id", "")), "on": False, "tracks": [],
                           "error": "Meeting audio capture isn't available in this desktop session."})

    def _dictation(self, text: str) -> None:
        try:
            if self.native is None:
                raise RuntimeError(NO_DESKTOP)
            result = self.native.paste_dictation(text)
        except Exception as error:
            result = {"pasted": False, "error": str(error)}
        if isinstance(result, dict) and result.get("pasted") is False:
            self.views.window.keep_dictation(text, str(result.get("error") or result.get("why") or ""),
                                             bool(result.get("copied")))
            self.open_window()
        else:
            self.views.presence.pasted(text)

    def _request(self, event: dict) -> None:
        kind, identity = event["type"], str(event["id"])
        if self.office is not None:
            from .office_client import is_office_request
            if is_office_request(event):
                self.office.request(event, lambda answer, request=event: self._office_done(request, answer))
                return
        answer = {"type": REQUESTS[kind], "id": identity}
        try:
            if self.native is None:
                raise RuntimeError(NO_DESKTOP)
            if kind == "look_request":
                answer["capture"] = self.native.capture(str(event.get("mode", "window")))
            elif kind == "hands_request":
                answer.update(ok=True, result=self.native.hands_request(str(event["tool"]), event.get("args") or {}))
            else:
                answer.update(ok=True, result=self.native.app_request(str(event["op"]), event.get("args") or {}))
                self._wrote(str(event["op"]), event.get("args") or {}, answer["result"])
        except Exception as error:
            if kind == "look_request":
                answer["capture"] = {"error": str(error)}
            else:
                borrow = getattr(error, "borrow", None)
                answer.update(ok=False, result={"borrow": borrow} if borrow else {}, error=str(error))
        self.send(answer)

    def _wrote(self, op: str, args: dict, result) -> None:
        """Text Milo wrote (ADR 0033): pasted shows "Pasted", kept offers Copy under his next line."""
        if op != "text.write" or not isinstance(result, dict):
            return
        text = str(args.get("text", ""))
        if result.get("pasted"):
            self.views.presence.pasted(text)
        else:
            self.views.presence.offer_copy(text)

    def _office_done(self, request: dict, answer: dict) -> None:
        result = answer.get("result")
        if (answer.get("ok") and isinstance(result, dict) and result.get("path") and not result.get("opened")
                and request.get("tool") in ("sheet_write", "write_document") and self.native is not None):
            path = Path(str(result["path"])).resolve()
            root = self.home.resolve()
            work = (root / "work").resolve()
            if work.is_relative_to(root) and path.is_relative_to(work) and path.is_file():
                try:
                    self.native.hands_request("open_file", {"path": str(path)})
                    result["opened"] = True
                    result["text"] = f"Created {path}. Opened it with the installed document application."
                except Exception:
                    # The write already succeeded. Don't report it as failed and invite a retry that would
                    # create the document a second time.
                    self.views.window.set(notice=f"Saved {path.name}. Open it from your Milo/work folder to review it.")
        self.send(answer)

    def _waiting(self) -> None:
        store = self.views.store
        self.views.window.set_waiting(len(store.state.confirmations), len(store.state.drafts))

    def close(self) -> None:
        for timer in self._timers:
            timer.stop()
        if self.hotkeys is not None:
            self.hotkeys.stop()
        if self.native is not None:
            self.native.close()
        if self.office is not None:
            self.office.close()
        if self.connection is not None:
            self.connection.close()


def _pairs(fixes) -> list[tuple]:
    """Corrections as (heard, meant) pairs, whether the platform gives tuples or wire dicts."""
    return [(f["heard"], f["meant"]) if isinstance(f, dict) else tuple(f) for f in fixes]
