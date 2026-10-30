"""Pairing a phone: who may reach Milo by message (ADR 0017).

Someone messages Milo's bot. Milo shows a 6-digit code on the Mac, tied to that chat, and the person sends
it back. Only someone who can see the Mac's screen can do that, so whoever does becomes the owner, and from
then on only their chat counts. A code works for 10 minutes and 5 tries; a chat that used up its tries
waits an hour before it gets a new one, and at most 3 chats can wait for a code at a time.
"""

from __future__ import annotations

import hmac
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from milo.core.ports import Clock

CODE_TTL_S = 600.0
MAX_TRIES = 5
MAX_WAITING = 3
LOCKOUT_S = 3600.0
_CODE = re.compile(r"\d[\d\s-]{4,10}\d")


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def as_code(text: str) -> str | None:
    """The digits of a message that is only a code ("482 913", "482-913"), else None."""
    text = text.strip()
    return re.sub(r"\D", "", text) if _CODE.fullmatch(text) else None


def spaced(code: str) -> str:
    """A code the way Milo shows it: "482 913"."""
    return f"{code[:3]} {code[3:]}"


@dataclass
class Request:
    chat: str
    sender: str
    name: str
    code: str
    made_at: float
    tries: int = 0


class Pairing:
    """The codes waiting to be sent back. In memory only: a restart cancels them, which is safe."""

    def __init__(self, clock: Clock, *, ttl_s: float = CODE_TTL_S, max_tries: int = MAX_TRIES,
                 max_waiting: int = MAX_WAITING, lockout_s: float = LOCKOUT_S, code: Callable[[], str] = new_code):
        self._clock = clock
        self._ttl_s = ttl_s
        self._max_tries = max_tries
        self._max_waiting = max_waiting
        self._lockout_s = lockout_s
        self._code = code
        self._waiting: dict[str, Request] = {}
        self._locked: dict[str, float] = {}

    def request(self, chat: str, sender: str, name: str) -> tuple[Request | None, bool]:
        """The code for this chat: (request, True) when it is new and must be shown, (request, False) when
        one is still waiting, (None, False) when this chat is locked out or too many wait already."""
        self.expire()
        if chat in self._locked:
            return None, False
        waiting = self._waiting.get(chat)
        if waiting is not None:
            return waiting, False
        if len(self._waiting) >= self._max_waiting:
            return None, False
        request = Request(chat, sender, name, self._code(), self._clock.monotonic())
        self._waiting[chat] = request
        return request, True

    def redeem(self, chat: str, sender: str, code: str) -> bool | None:
        """True: the right code from the chat and person it was made for; every other code is cancelled.
        False: a wrong code (it counts as a try). None: there is no code waiting for this chat."""
        self.expire()
        request = self._waiting.get(chat)
        if request is None or request.sender != sender:
            return None
        if hmac.compare_digest(request.code, code):
            self._waiting.clear()
            return True
        request.tries += 1
        if request.tries >= self._max_tries:
            del self._waiting[chat]
            self._locked[chat] = self._clock.monotonic()
        return False

    def tries_left(self, chat: str) -> int:
        request = self._waiting.get(chat)
        return 0 if request is None else self._max_tries - request.tries

    def cancel(self) -> None:
        self._waiting.clear()

    def expire(self) -> None:
        now = self._clock.monotonic()
        for chat in [c for c, r in self._waiting.items() if now - r.made_at >= self._ttl_s]:
            del self._waiting[chat]
        for chat in [c for c, at in self._locked.items() if now - at >= self._lockout_s]:
            del self._locked[chat]
