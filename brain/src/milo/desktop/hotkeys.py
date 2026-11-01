"""Global push-to-talk and shortcuts. OS listeners only report key names; the state machine runs on Qt's thread.

`PushToTalk` is the Mac's state machine (app/Sources/MiloKit/Hotkeys/PushToTalk.swift), so a key behaves the
same on every computer: a hold records while held, a tap is nothing, a double tap locks recording on until the
key is pressed again, Esc cancels, any other key during a hold makes it a shortcut. `GlobalHotkeys` is the
`HotkeySource` (see `platform/ports.py`), including the instant `ear` feedback.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot

log = logging.getLogger("milo.desktop.keys")


def key_name(key) -> str:
    char = getattr(key, "char", None)
    # XKB's ISO_Level3_Shift (AltGr on many European keyboards) is returned
    # as a bare KeyCode rather than pynput's Key.alt_gr on some X11 layouts.
    value = getattr(key, "value", key)
    vk = getattr(value, "vk", None)
    if sys.platform == "win32":
        special = {0xA3: "right_control", 0xA5: "right_option"}
        if vk in special:
            return special[vk]
        if vk is not None and not str(key).startswith("Key."):
            # Character translation changes with Ctrl/Shift and key-up order.
            # A physical C key is still C when pynput reports control-C (\x03).
            if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
                return chr(vk).casefold()
            return f"vk:{vk}"
    else:
        special = {0xFFE4: "right_control", 0xFFEA: "right_option",
                   0xFE03: "right_option", 0xFF7E: "right_option"}
    if vk in special:
        return special[vk]
    if char:
        return char.casefold()
    name = str(key).removeprefix("Key.")
    return {"ctrl_r": "right_control", "alt_r": "right_option", "alt_gr": "right_option",
            "cmd_r": "right_command", "ctrl_l": "ctrl", "alt_l": "alt", "cmd_l": "cmd",
            "shift_l": "shift", "shift_r": "shift", "esc": "escape"}.get(name, name)


def physical_key(name: str) -> str:
    # fn is not an observable key on ordinary PC keyboards. Preserve old configs
    # while giving them a physical right-Control equivalent on Windows/Linux.
    return "right_control" if name == "fn" and sys.platform != "darwin" else name


def combo_name(combo: str) -> tuple[frozenset[str], str]:
    parts = combo.casefold().replace(" ", "").split("+")
    aliases = {"option": "alt", "control": "ctrl", "command": "cmd"}
    return frozenset(aliases.get(v, v) for v in parts[:-1]), parts[-1]


class PushToTalk:
    """Pure push-to-talk, a port of the Mac's. Feed it presses, releases and expired deadlines.

    Recording starts the moment the key goes down, tentatively (`listen_start` with `tentative`), so no word
    is lost; it shows after `show_after` (`listen_confirm`). A press shorter than `min_hold` is a tap: the
    recording goes on for `double_s` in case a second tap comes, then it is cancelled. A second short tap in
    that time locks it on (hands-free), a second long press is an ordinary hold. A further press of a locked
    key stops it, Esc cancels it, and after `max_locked` it stops by itself. Other keys cancel a hold but not
    a locked recording: the user isn't typing then, and Milo's own pastes would otherwise end it.

    `send` gets the wire commands, `ear(kind, mode)` the instant feedback, `focus()` is called on key down.
    """
    min_hold = 0.25
    show_after = 0.08
    double_s = 0.35

    def __init__(self, send: Callable[[dict], None], focus: Callable[[], None] = lambda: None,
                 clock: Callable[[], float] = time.monotonic, *,
                 ear: Callable[[str, str], None] = lambda kind, mode: None,
                 hands_free: Callable[[str], None] = lambda mode: None, max_locked: float = 300.0):
        self.send, self.focus, self.clock, self.ear, self.hands_free = send, focus, clock, ear, hands_free
        self.max_locked = max_locked
        # idle | holding | tapped | locked
        self.phase = "idle"
        self.mode = ""
        self.since = 0.0
        self.second = False
        self.confirmed = False
        self.until = 0.0

    @property
    def active(self) -> str:
        return "" if self.phase == "idle" else self.mode

    @property
    def locked(self) -> bool:
        return self.phase == "locked"

    @property
    def deadline(self) -> float | None:
        """When `expire()` must be called next, on `clock`'s time; None: no timer needed."""
        if self.phase == "holding":
            return None if self.confirmed else self.since + self.show_after
        if self.phase in ("tapped", "locked"):
            return self.until
        return None

    def press(self, mode: str) -> None:
        now = self.clock()
        if self.phase == "idle":
            self._start(mode, now)
        elif self.phase == "tapped" and self.mode == mode:
            # The recording the first tap started goes on. A late second press is a fresh hold.
            self.phase, self.since, self.second = "holding", now, now < self.until
        elif self.phase == "tapped":
            self._cancel()
            self._start(mode, now)
        elif self.phase == "locked" and self.mode == mode:
            self._stop()
        # holding, or locked on the other key: ignored

    def release(self, mode: str) -> None:
        if self.phase != "holding" or self.mode != mode:
            return
        now = self.clock()
        if now - self.since >= self.min_hold:
            self._stop()
        elif self.second:
            self.phase, self.until = "locked", now + self.max_locked
            self.hands_free(mode)
            self._confirm()
        else:
            self.phase, self.until = "tapped", self.since + self.double_s

    def other_key(self) -> None:
        """Another key or modifier went down: a shortcut, unless recording is locked on."""
        if self.phase != "locked":
            self._cancel()

    def expire(self) -> None:
        deadline = self.deadline
        if deadline is None or self.clock() < deadline:
            return
        if self.phase == "holding":
            self._confirm()
        elif self.phase == "tapped":
            self._cancel()
        elif self.phase == "locked":
            self._stop()

    def cancel(self) -> None:
        """Esc, a rebind, a lost listener: forget any recording."""
        self._cancel()

    def _start(self, mode: str, now: float) -> None:
        self.phase, self.mode, self.since, self.second, self.confirmed = "holding", mode, now, False, False
        self.ear("armed", mode)
        # The mic opens before anything else: every millisecond here is the first syllable. The focus is read
        # right after, still before anything on screen can move it.
        self.send({"type": "listen_start", "mode": mode, "tentative": True})
        self.focus()

    def _confirm(self) -> None:
        self.confirmed = True
        self.ear("open", self.mode)
        self.send({"type": "listen_confirm"})

    def _stop(self) -> None:
        mode, locked, self.phase = self.mode, self.phase == "locked", "idle"
        if locked:
            self.hands_free("")
        self.ear("caught", mode)
        self.send({"type": "listen_stop"})

    def _cancel(self) -> None:
        if self.phase == "idle":
            return
        mode, locked, self.phase = self.mode, self.phase == "locked", "idle"
        if locked:
            self.hands_free("")
        self.ear("cancelled", mode)
        self.send({"type": "listen_cancel"})


class GlobalHotkeys(QObject):
    """The `HotkeySource`: pynput's OS hook, plus (on Windows) a 25 ms poll of the physical key state.

    Windows silently removes a low-level hook whose callback was slow once too often, so the hook alone can
    go deaf with no error; the poll keeps the voice keys working and reconciles releases the hook missed.
    """
    command = Signal(dict)
    ear = Signal(str, str)
    hands_free = Signal(str)
    focus_requested = Signal()
    status = Signal(str)
    _key_event = Signal(str, bool)
    _takeover = Signal()

    def __init__(self, on_command=None, remember_focus=None, *, synthetic=lambda: False, keys=None, parent=None):
        super().__init__(parent)
        if on_command is not None:
            self.command.connect(on_command)
        if remember_focus is not None:
            self.focus_requested.connect(remember_focus)
        if keys is None:
            from .platform import keys as platform_keys
            keys = platform_keys()
        self.keys = keys
        self.synthetic = synthetic
        self._keyboard = self._mouse = None
        self._pressed: set[str] = set()
        self._session = False
        self._dictate, self._talk = "right_control", "right_option"
        self._shortcuts = {"ctrl+alt+m": "whats_this", "ctrl+alt+n": "meeting_toggle"}
        self._meeting_on = False
        self._ptt = PushToTalk(self.command.emit, self.focus_requested.emit, ear=self._ear,
                               hands_free=self.hands_free.emit)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._expire)
        self._key_event.connect(self._on_key)
        self._takeover.connect(self._on_takeover)
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(2000)
        self._health_timer.timeout.connect(self._check_listeners)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(25)
        self._poll_timer.timeout.connect(self._poll_keys)
        self._diagnostic_path = None
        self._diagnostic = {"voice_events": 0, "last_stage": "created"}

    # HotkeySource

    def set_synthetic(self, busy: Callable[[], bool]) -> None:
        self.synthetic = busy

    def configure(self, event: dict) -> None:
        self._ptt.cancel()
        self._dictate = physical_key(str(event.get("dictate_key", "right_control")))
        self._talk = physical_key(str(event.get("talk_key", "right_option")))
        self._ptt.max_locked = max(1.0, float(event.get("hands_free_max_s", 300.0)))
        self._shortcuts = {}
        for key, command in (("whats_this_key", "whats_this"), ("meeting_key", "meeting_toggle")):
            if event.get(key):
                self._shortcuts[str(event[key])] = command
        self._schedule()
        self._diagnose("configured")

    def set_session(self, on: bool) -> None:
        self._session = bool(on)
        # The mouse hook costs every pointer move system-wide; it only matters while Milo works the screen.
        if self._session and self._keyboard is not None and self._mouse is None:
            self._start_mouse()
        elif not self._session and self._mouse is not None:
            self._mouse.stop()
            self._mouse = None

    def set_meeting(self, on: bool) -> None:
        self._meeting_on = bool(on)

    def start(self) -> None:
        if self._keyboard is not None:
            return
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            self.status.emit("Global shortcuts require an X11 session on Linux. Use Milo's Talk and Dictate buttons.")
            return
        try:
            from pynput import keyboard
            self._keyboard = keyboard.Listener(
                on_press=lambda key: self._listener_key(key, True),
                on_release=lambda key: self._listener_key(key, False),
                **self.keys.listener_options())
            self._keyboard.start()
            if self._session:
                self._start_mouse()
            self._health_timer.start()
            if getattr(self.keys, "polls", False):
                self._poll_timer.start()
            self._diagnose("started")
            log.info("global keys on: dictate %s, talk %s", self._dictate, self._talk)
        except Exception as e:
            self.stop()
            log.exception("global keys unavailable")
            self.status.emit(f"Global shortcuts are unavailable: {e}. Use Milo's Talk and Dictate buttons.")

    def stop(self) -> None:
        self._poll_timer.stop()
        self._health_timer.stop()
        self._timer.stop()
        self._ptt.cancel()
        for listener in (self._keyboard, self._mouse):
            if listener:
                listener.stop()
        self._keyboard = self._mouse = None
        self._pressed.clear()
        self._diagnose("stopped")

    # Internals

    def _start_mouse(self) -> None:
        from pynput import mouse
        self._mouse = mouse.Listener(on_move=lambda *_: self._listener_takeover(),
                                     on_click=lambda *_: self._listener_takeover(),
                                     on_scroll=lambda *_: self._listener_takeover())
        self._mouse.start()

    def _ear(self, kind: str, mode: str) -> None:
        if kind == "armed":
            try:
                self.keys.mask_menu(self._talk if mode == "talk" else self._dictate)
            except Exception:
                log.debug("menu mask failed", exc_info=True)
        log.info("ear %s %s", kind, mode)
        self.ear.emit(kind, mode)

    def _schedule(self) -> None:
        deadline = self._ptt.deadline
        if deadline is None:
            self._timer.stop()
        else:
            self._timer.start(max(0, round((deadline - self._ptt.clock()) * 1000)))

    @Slot()
    def _expire(self) -> None:
        self._ptt.expire()
        self._schedule()

    def set_diagnostics_path(self, path: Path) -> None:
        """Record voice-control health only; never key contents or typed text."""
        self._diagnostic_path = Path(path)
        self._diagnose("configured")

    def _diagnose(self, stage: str) -> None:
        if stage.startswith("voice_"):
            self._diagnostic["last_voice_stage"] = stage
        self._diagnostic.update(last_stage=stage, dictate=self._dictate, talk=self._talk,
                                active_mode=self._ptt.active, phase=self._ptt.phase,
                                pressed_count=len(self._pressed), polling=self._poll_timer.isActive(),
                                keyboard_alive=bool(self._keyboard and self._keyboard.is_alive()))
        if self._diagnostic_path is not None:
            try:
                self._diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._diagnostic_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(self._diagnostic), encoding="utf-8")
                temporary.replace(self._diagnostic_path)
            except OSError:
                pass

    def _poll_keys(self) -> None:
        if self.synthetic():
            return
        # Reconcile missed releases before considering a voice-key press.
        for key in list(self._pressed):
            if self.keys.is_down(key) is False:
                self._on_key(key, False)
        for key in dict.fromkeys((self._dictate, self._talk)):
            held = self.keys.is_down(key)
            if held is not None and held != (key in self._pressed):
                self._on_key(key, held)

    def _check_listeners(self) -> None:
        self._diagnose("health")
        for listener in (self._keyboard, self._mouse):
            if listener is not None and not listener.is_alive():
                detail = "the system input listener stopped"
                try:
                    listener.join(timeout=0)
                except Exception as error:
                    detail = str(error)
                self.stop()
                log.warning("global keys stopped: %s", detail)
                self.status.emit(f"Global shortcuts are unavailable: {detail}. Use Milo's Talk and Dictate buttons.")
                return

    def _listener_key(self, key, pressed: bool) -> None:
        # Runs on the hook's thread: only a queued signal, never Qt objects or slow work.
        if key is None:
            return
        if not self.synthetic():
            self._key_event.emit(key_name(key), pressed)

    def _listener_takeover(self) -> None:
        if self._session and not self.synthetic():
            self._session = False
            self._takeover.emit()

    @Slot()
    def _on_takeover(self) -> None:
        self.command.emit({"type": "hands_stop", "reason": "The user took over the mouse or keyboard."})

    @Slot(str, bool)
    def _on_key(self, key: str, pressed: bool) -> None:
        voice = key in (self._dictate, self._talk)
        if voice:
            self._diagnostic["voice_events"] += 1
        if pressed and self._session:
            self._session = False
            self._on_takeover()
        if pressed and key in self._pressed:
            return  # key repeat never starts another recording
        if voice and pressed and self.keys.polls:
            # Drop keys whose release the hook never delivered, so they can't block a voice press as a chord.
            self._pressed = {held for held in self._pressed if self.keys.is_down(held) is not False}
        if pressed:
            self._pressed.add(key)
        else:
            self._pressed.discard(key)
        try:
            self._key(key, pressed, voice)
        finally:
            self._schedule()

    def _key(self, key: str, pressed: bool, voice: bool) -> None:
        if key == "escape":
            if pressed:
                self._ptt.cancel()
            return
        if voice:
            mode = "dictate" if key == self._dictate else "talk"
            if not pressed:
                self._ptt.release(mode)
                self._diagnose("voice_release")
                return
            if self._ptt.active and self._ptt.mode != mode:
                return  # the other voice key during a recording is ignored, as on the Mac
            # A voice key pressed inside a normal shortcut (Shift+Right Ctrl, Ctrl+Alt) is not a voice request.
            if not self._ptt.active and (self._pressed - {key} or self.keys.other_down(key)):
                self._diagnose("voice_blocked_chord")
                log.info("voice key %s pressed in a chord: not recording", key)
                return
            self._ptt.press(mode)
            self._diagnose("voice_press")
            return
        if not pressed:
            return
        self._ptt.other_key()
        modifiers = set()
        for held in self._pressed - {key}:
            modifiers.add({"right_control": "ctrl", "right_option": "alt", "right_command": "cmd"}.get(held, held))
        for shortcut, command in self._shortcuts.items():
            expected, final = combo_name(shortcut)
            if final == key and modifiers == expected:
                if command == "whats_this":
                    # UI fills capture at the instant this shortcut was pressed.
                    self.command.emit({"type": "whats_this"})
                else:
                    self._meeting_on = not self._meeting_on
                    self.command.emit({"type": "meeting_toggle", "on": self._meeting_on})


Hotkeys = GlobalHotkeys
