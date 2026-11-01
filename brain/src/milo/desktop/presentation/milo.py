"""Everything the floating Milo shows (MiloKit/MiloModel.swift), on wire dicts and without Qt.

Changes are reported by name to `on_change`, once per event or key, so a view model emits only what moved.
The level goes on its own name: it arrives twenty times a second and must not redraw anything else.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable

from .clock import Clock, Scheduled, Scheduler, monotonic
from .speech_reveal import SpeechReveal
from .voice_phase import DICTATE, TALK, Ear, VoicePhase, label, phase_of, thinking_label

CAUGHT_BEAT = 0.6  # "Got it" after the key comes up: long enough to read, short enough not to hold anything up
PASTED_BEAT = 1.4
UNDO_LINGER = 8.0  # extra seconds a bubble with Undo or Copy stays, so there is time to reach it
COPY_OFFER_FOR = 30.0
THINKING_STEPS = (6.0, 20.0)  # the capsule says "Still on it", then "Taking a while"
HANDS_STEP = "hands_"  # every step of Milo's own hands starts with this, as opposed to the worker's
ACTIVE_HELPERS = frozenset(("queued", "working", "needs_you"))
COPIED = "Copied. Paste it where you like."


def bubble_duration(text: str) -> float:
    """How long a bubble stays up: longer for longer text, at most 20 s."""
    return min(20.0, 4 + len(text) / 15)


def _words(text: str) -> str:
    return " ".join(text.split())


class MiloState:
    def __init__(self, scheduler: Scheduler, clock: Clock = monotonic,
                 on_change: Callable[[set[str]], None] | None = None):
        self.scheduler, self.now = scheduler, clock
        self.on_change = on_change or (lambda names: None)
        self.on_celebrate: Callable[[], None] = lambda: None
        self.on_nudge: Callable[[], None] = lambda: None
        self.state, self.emotion = "idle", "neutral"
        self.bubble = self.heard = self.partial = ""
        self.level = 0.0
        self.connected = False
        self.hands_free: str | None = None
        self.looking = self.hands_active = self.pasted = False
        self.working_step = ""
        self.question: dict | None = None
        self.helpers: list[dict] = []
        self.undo_points: list[dict] = []
        self.meeting: dict = {}
        self.ear: Ear | None = None
        self.bubble_action: dict | None = None
        self.reveal = SpeechReveal()
        self.thinking_since: float | None = None
        self.last_mode = TALK
        self._copy_offer: tuple[str, float] | None = None
        self._timers: dict[str, Scheduled] = {}
        self._changed: set[str] = set()
        self._depth = 0

    # ---- derived

    @property
    def voice_phase(self) -> VoicePhase | None:
        return phase_of(state=self.state, ear=self.ear, hands_free=self.hands_free, pasted=self.pasted,
                        connected=self.connected, last_mode=self.last_mode,
                        answering=bool(self.bubble) or self.question is not None)

    @property
    def hint(self) -> str:
        """The capsule's words for the phase, with how long he has thought."""
        phase, words = self.voice_phase, bool(self.partial or self.heard)
        if phase is not None and phase.kind == "thinking" and self.thinking_since is not None:
            return thinking_label(self.now() - self.thinking_since, words=words)
        return label(phase, words=words)

    @property
    def helpers_active(self) -> bool:
        return any(h.get("status") in ACTIVE_HELPERS for h in self.helpers)

    @property
    def can_stop(self) -> bool:
        """Talking, thinking, working on screen, or a helper at work: the Stop button by him can stop it."""
        return self.state in ("speaking", "thinking") or self.hands_active or self.helpers_active

    @property
    def needed(self) -> bool:
        """What he is doing or showing that the user may need: he stays for it and comes back for it.
        Being offline isn't one: a brain that is gone for good would keep him up forever."""
        phase = self.voice_phase
        return bool(self.state != "idle" or self.question is not None or self.bubble or self.can_stop
                    or (phase is not None and phase.kind != "offline")
                    or self.ear is not None or self.hands_free is not None or self.looking
                    or self.meeting.get("phase") in ("recording", "paused", "writing"))

    # ---- batching

    @contextmanager
    def _batch(self):
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
            if not self._depth and self._changed:
                names, self._changed = self._changed, set()
                self.on_change(names)

    def _set(self, name: str, value) -> None:
        if getattr(self, name) != value:
            setattr(self, name, value)
            self._changed.add(name)

    def _later(self, name: str, seconds: float, work: Callable[[], None]) -> None:
        self._cancel(name)

        def run():
            self._timers.pop(name, None)
            with self._batch():
                work()
        self._timers[name] = self.scheduler.after(seconds, run)

    def _cancel(self, name: str) -> None:
        timer = self._timers.pop(name, None)
        if timer is not None:
            timer.cancel()

    # ---- the brain

    def set_connected(self, up: bool) -> None:
        with self._batch():
            self._set("connected", up)
            if not up:
                # A brain that died mid-answer never sends idle; its helpers and questions died with it.
                self.apply({"type": "state", "state": "idle"})
                self.apply({"type": "helpers", "helpers": []})
                self._set("hands_free", None)
                if self.question is not None:
                    self.apply({"type": "confirm_done", "id": self.question.get("id"), "answer": "timeout"})

    def apply(self, event: dict) -> None:
        with self._batch():
            self._apply(event)

    def _apply(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "state":
            self._state(str(event.get("state", "idle")))
        elif kind == "emotion":
            self._set("emotion", str(event.get("emotion", "neutral")))
        elif kind in ("bubble", "status"):
            self.show(str(event.get("text", "")))
        elif kind == "access":
            fix = {"kind": "access", "title": "Fix it", "need": event.get("need", ""), "app": event.get("app", "")}
            self.show(str(event.get("text", "")), fix if event.get("state") == "no" else None)
            self.on_nudge()
        elif kind == "heard":
            self._set("heard", str(event.get("text", "")))
        elif kind == "level":
            self._set("level", min(1.0, max(0.0, float(event.get("value", 0) or 0))))
        elif kind == "partial":
            self._set("partial", str(event.get("text", "")))
        elif kind == "looking":
            self._set("looking", bool(event.get("on")))
        elif kind == "hands_session":
            self._set("hands_active", bool(event.get("on")))
            if not self.hands_active:
                self._set("working_step", "")
        elif kind == "confirm":
            self._set("question", {k: v for k, v in event.items() if k != "type"})
            self._hide_later()
            self.on_nudge()
        elif kind == "confirm_done":
            if self.question is not None and self.question.get("id") == event.get("id"):
                self._set("question", None)
                self._hide_later()
        elif kind == "helpers":
            self._set("helpers", list(event.get("helpers") or []))
        elif kind == "undo_points":
            self._set("undo_points", list(event.get("points") or []))
            # The Undo under a bubble goes once its task is being undone, or can't be any more.
            action = self.bubble_action
            if action and action["kind"] == "undo" and self._undo_state(action["id"]) != "ready":
                self._set("bubble_action", None)
        elif kind == "meeting_status":
            self._set("meeting", {k: v for k, v in event.items() if k != "type"})
        elif kind == "action_done":
            self.on_celebrate()
        elif kind == "activity":
            # The caption under the working outline follows the hands' own steps; the worker's are its business.
            step = event.get("step") or {}
            if str(step.get("id", "")).startswith(HANDS_STEP) and step.get("status") == "running":
                self._set("working_step", str(step.get("title", "")))

    def _state(self, new: str) -> None:
        was_speaking = self.state == "speaking"
        self._set("state", new)
        if new == "listening":
            self._set("last_mode", TALK)
        if new == "dictating":
            self._set("last_mode", DICTATE)
        if was_speaking and new != "speaking":
            self.reveal.finish()
            self._changed.add("reveal")
        if new != "thinking":
            self._set("thinking_since", None)
            self._cancel("thinking")
        elif self.thinking_since is None:
            self._set("thinking_since", self.now())
            self._thinking_steps()
        if new in ("listening", "dictating"):
            self._set("heard", "")
        # A new question replaces the last answer, so its hide timer can't later wipe `heard` while he thinks.
        if new == "listening":
            self._clear_bubble()
        if new in ("idle", "speaking", "listening"):
            self._hide_later()
        if new not in ("speaking", "listening", "dictating"):
            self._set("level", 0.0)
        # A new recording starts empty; the last words stay while the final pass runs.
        if new != "transcribing":
            self._set("partial", "")

    def _thinking_steps(self) -> None:
        since = self.thinking_since

        def step(index: int):
            if self.thinking_since != since:
                return
            self._changed.add("hint")
            if index + 1 < len(THINKING_STEPS):
                self._later("thinking", THINKING_STEPS[index + 1] - THINKING_STEPS[index], lambda: step(index + 1))
        self._later("thinking", THINKING_STEPS[0], lambda: step(0))

    # ---- the bubble

    def show(self, text: str, action: dict | None = None) -> None:
        """Text in the bubble for a while, with a button that helps if there is one. Empty text hides it."""
        with self._batch():
            if not text:
                self._clear_bubble()
                self._hide_later()
                return
            action = action or self._undo_action(text) or self._take_copy_offer(text)
            paced = action is None or action["kind"] in ("undo", "copy")
            self.reveal.show(text, speaking=self.state == "speaking" and paced, at=self.now())
            self._changed.add("reveal")
            self._set("bubble", text)
            self._set("bubble_action", action)
            self._hide_later()

    def offer_copy(self, text: str) -> None:
        """Text Milo wrote stayed in his window instead of a field: the line he says about it gets Copy."""
        self._copy_offer = (text, self.now())

    def _take_copy_offer(self, text: str) -> dict | None:
        action = self.bubble_action
        if action and action["kind"] == "copy" and self.bubble and text.startswith(self.bubble):
            return action  # the same line, growing piece by piece as he speaks it
        offer, self._copy_offer = self._copy_offer, None
        if offer is None or self.now() - offer[1] > COPY_OFFER_FOR:
            return None
        return {"kind": "copy", "title": "Copy", "text": offer[0]}

    def _undo_state(self, task: str) -> str:
        return next((p.get("state", "") for p in self.undo_points if p.get("id") == task), "")

    def _undo_action(self, text: str) -> dict | None:
        """The newest task that can be undone, if Milo is saying what it did."""
        shown = _words(text)
        point = next((p for p in self.undo_points if p.get("state") == "ready"), None)
        if not shown or point is None:
            return None
        said = _words(str(point.get("said", "")))
        return {"kind": "undo", "title": "Undo", "id": point.get("id")} if said and said.startswith(shown) else None

    def _clear_bubble(self) -> None:
        self._set("bubble", "")
        self._set("bubble_action", None)
        self.reveal.clear()
        self._changed.add("reveal")

    def _hide_later(self) -> None:
        self._cancel("bubble")
        # A question stays up until it is answered or over.
        if not self.bubble or self.state == "speaking" or self.question is not None:
            return
        longer = UNDO_LINGER if self.bubble_action and self.bubble_action["kind"] in ("undo", "copy") else 0.0

        def hide():
            self._clear_bubble()
            self._set("heard", "")
            if self.state == "idle":
                self._set("emotion", "neutral")
        self._later("bubble", bubble_duration(self.bubble) + longer, hide)

    def answered(self) -> None:
        """The user clicked an answer: the question goes at once; `confirm_done` confirms it."""
        with self._batch():
            self._set("question", None)
            self._hide_later()

    # ---- the keys, a frame ahead of the brain

    def ear_event(self, kind: str, mode: str) -> None:
        """From the hotkeys: armed (key down), open (a real hold or a lock), caught (released after a hold),
        cancelled (a tap, a shortcut or Esc)."""
        with self._batch():
            if kind == "armed":
                self._cancel("ear")
                self._set("last_mode", mode)
                self._set("ear", Ear("armed", mode))
            elif kind == "open":
                self._set("last_mode", mode)
                self._set("ear", Ear("open", mode))
            elif kind == "caught":
                self._set("ear", Ear("caught", mode))
                self._later("ear", CAUGHT_BEAT,
                            lambda: self._set("ear", None) if self.ear and self.ear.kind == "caught" else None)
            elif kind == "cancelled":
                self._cancel("ear")
                self._set("ear", None)

    def set_hands_free(self, mode: str | None) -> None:
        with self._batch():
            self._set("hands_free", mode or None)

    def pasted_text(self, text: str) -> None:
        """Dictation went into the focused app: "Pasted" for a moment."""
        if not text.strip():
            return
        with self._batch():
            self._set("pasted", True)
            self._later("pasted", PASTED_BEAT, lambda: self._set("pasted", False))
