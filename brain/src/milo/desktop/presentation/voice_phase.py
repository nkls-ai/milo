"""The ear and the voice capsule's phase, exactly as the Mac decides them (MiloKit/VoicePhase.swift).

protocol/voice_phases.json holds the rules as cases; this module and the Swift one both run them.
"""
from __future__ import annotations

from dataclasses import dataclass

TALK, DICTATE = "talk", "dictate"
EAR_KINDS = ("armed", "open", "caught")
PHASE_KINDS = ("armed", "listening", "caught", "transcribing", "pasted", "thinking", "offline")


@dataclass(frozen=True)
class Ear:
    """The talk or dictate key as the app saw it, a frame before the brain can answer.

    armed: the key is down, it may still be a tap. open: a real hold or a hands-free lock.
    caught: the key came up after a hold, the short "got it" beat.
    """
    kind: str
    mode: str = TALK


@dataclass(frozen=True)
class VoicePhase:
    """What the small capsule over Milo shows about his ears and his head, one at a time."""
    kind: str
    mode: str = ""
    hands_free: bool = False

    @property
    def color_mode(self) -> str:
        """The mode whose colour the capsule wears; "" for neutral phases."""
        if self.kind == "pasted":
            return DICTATE
        if self.kind == "thinking":
            return TALK
        return "" if self.kind == "offline" else self.mode

    @property
    def recording(self) -> bool:
        """Recording, in any form: the answer bubble steps aside."""
        return self.kind in ("armed", "listening", "caught")

    @property
    def spoken(self) -> str:
        """A short name for screen readers."""
        if self.kind == "armed" or (self.kind == "listening" and self.mode == TALK):
            return "Milo is listening"
        return {
            "listening": "Milo is taking dictation",
            "caught": "Milo got it",
            "transcribing": "Milo is writing it down" if self.mode == DICTATE else "Milo is working out what you said",
            "pasted": "Pasted",
            "thinking": "Milo is thinking",
            "offline": "Milo is waking up",
        }[self.kind]


def phase_of(*, state: str, ear: Ear | None, hands_free: str | None, pasted: bool, connected: bool,
             last_mode: str, answering: bool) -> VoicePhase | None:
    """Order matters: the user's own key beats what the brain last said, since the brain is always a moment behind."""
    if not connected:
        return VoicePhase("offline")
    if ear is not None and ear.kind == "caught":
        return VoicePhase("pasted") if pasted and ear.mode == DICTATE else VoicePhase("caught", ear.mode)
    locked = hands_free is not None
    if state == "listening":
        return VoicePhase("listening", TALK, locked)
    if state == "dictating":
        return VoicePhase("listening", DICTATE, locked)
    if ear is not None and ear.kind == "open":
        return VoicePhase("listening", ear.mode, locked)
    if ear is not None and ear.kind == "armed":
        return VoicePhase("armed", ear.mode)
    if pasted:
        return VoicePhase("pasted")
    if state == "transcribing":
        return VoicePhase("transcribing", last_mode)
    if state == "thinking" and not answering:
        return VoicePhase("thinking")
    return None


def label(phase: VoicePhase | None, *, words: bool) -> str:
    """The capsule's words (VoiceCapsule.label): "" where the picture says enough. `words`: live words show."""
    if phase is None or phase.kind == "armed":
        return ""
    if phase.kind == "listening":
        return "Dictating" if phase.mode == DICTATE else "Listening"
    if phase.kind == "transcribing":
        return "Writing it down" if phase.mode == DICTATE else ("" if words else "One moment")
    if phase.kind == "thinking":
        return "" if words else "Thinking"
    return {"caught": "Got it", "pasted": "Pasted", "offline": "Waking up"}[phase.kind]


def thinking_label(seconds: float, *, words: bool) -> str:
    """Thinking for longer than a moment says so, so a slow answer never looks stuck."""
    if seconds < 6:
        return label(VoicePhase("thinking"), words=words)
    return "Still on it" if seconds < 20 else "Taking a while"


def level_height(level: float) -> float:
    """Meter bar height 0...1 for a mic level: room noise stays flat, a normal voice fills most of it."""
    return min(1.0, max(0.0, (level - 0.04) / 0.7)) ** 0.7


def tail(text: str, limit: int = 140) -> str:
    """The last `limit` characters, cut at a word, so the newest words stay visible."""
    if len(text) <= limit:
        return text
    end = text[-(limit + 1):]
    space = end.find(" ")
    return "…" + (end[space + 1:] if space >= 0 else end)
