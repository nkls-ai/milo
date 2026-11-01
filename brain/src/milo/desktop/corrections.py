"""Bounded, local observation of a dictated span. Only short word pairs leave this module."""
from __future__ import annotations

import difflib
import time
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from ._native_types import Focus


class WordList(Protocol):
    def is_word(self, word: str) -> bool: ...


class ConservativeWords:
    """Without a system dictionary, lowercase rewrites are presumed intentional."""
    _misspellings = frozenset({"teh", "hte", "adn", "taht", "thier", "recieve", "adress"})

    def is_word(self, word: str) -> bool:
        return word.casefold() not in self._misspellings


@dataclass(frozen=True)
class _Token:
    text: str
    sentence_end: bool


def _tokens(value: str) -> list[_Token]:
    result = []
    for raw in value.split():
        word = raw
        while word and unicodedata.category(word[0])[0] in "PS":
            word = word[1:]
        while word and unicodedata.category(word[-1])[0] in "PS":
            word = word[:-1]
        if word:
            result.append(_Token(word, raw[-1] in ".!?"))
    return result


def _fold(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def distance(a: str, b: str) -> int:
    table = [list(range(len(b) + 1))] + [[i] + [0] * len(b) for i in range(1, len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            table[i][j] = min(table[i - 1][j] + 1, table[i][j - 1] + 1,
                              table[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                table[i][j] = min(table[i][j], table[i - 2][j - 2] + 1)
    return table[-1][-1]


_CALENDAR = frozenset("monday tuesday wednesday thursday friday saturday sunday january february march april may june "
                     "july august september october november december today tomorrow yesterday montag dienstag "
                     "mittwoch donnerstag freitag samstag sonntag januar februar märz juni juli oktober dezember "
                     "heute morgen gestern".split())


def correction_pairs(pasted: str, edited: str, words: WordList | None = None) -> list[tuple[str, str]]:
    words = words or ConservativeWords()
    before, after = _tokens(pasted), _tokens(edited)
    if not before or not after or len(before) > 200 or len(after) > 450:
        return []
    matcher = difflib.SequenceMatcher(None, [t.text for t in before], [t.text for t in after], autojunk=False)
    codes = matcher.get_opcodes()
    removed = sum(b - a for tag, a, b, _, _ in codes if tag in ("replace", "delete"))
    if removed > max(3, len(before) // 2):
        return []
    matched = {index for tag, _, _, c, d in codes if tag == "equal" for index in range(c, d)}
    fixes = []
    for tag, a, b, c, d in codes:
        if tag != "replace":
            continue
        original = (a, b, c, d)
        while a < b and c < d and before[a].text.casefold() == after[c].text.casefold():
            a, c = a + 1, c + 1
        while a < b and c < d and before[b - 1].text.casefold() == after[d - 1].text.casefold():
            b, d = b - 1, d - 1
        if (a == b) != (c == d):
            continue
        if a == b:
            a, b, c, d = original
        if not 0 < b - a <= 3:
            continue
        heard = " ".join(t.text for t in before[a:b])
        if len(heard) > 160:
            continue
        candidates = [(c, d)]
        if d == len(after) and d - c > b - a:
            candidates.append((c, c + b - a))
        if c == 0 and d - c > b - a:
            candidates.append((d - b + a, d))
        selected = None
        for lower, upper in candidates:
            meant = " ".join(t.text for t in after[lower:upper])
            if len(meant) > 160:
                continue
            x, y = _fold(heard), _fold(meant)
            if upper - lower > 3 or not x or len(y) < 2 or (x.isdigit() and y.isdigit() and x != y):
                continue
            if x == y or distance(x, y) <= max(len(x), len(y)) * 0.5:
                selected = lower, upper, meant
                break
        if selected is None:
            continue
        lower, upper, meant = selected
        start = a == 0 or c == 0 or before[a - 1].sentence_end or after[c - 1].sentence_end
        if start and heard != meant and heard[1:] == meant[1:] and heard[:1].casefold() == meant[:1].casefold():
            continue
        if heard.casefold() in _CALENDAR and meant.casefold() in _CALENDAR:
            continue
        if not any(ch.isupper() for ch in meant) and _fold(heard) != _fold(meant) and all(words.is_word(w) for w in heard.split()):
            continue
        heard_words, meant_words = heard.split(), meant.split()
        def name_part(index):
            return (after[index].text[:1].isupper() and after[index].text != "I" and index > 0
                    and not after[index - 1].sentence_end)
        if b - a == 1 and upper - lower == 1 and meant[:1].isupper():
            if lower > 0 and lower - 1 in matched and name_part(lower - 1):
                heard_words.insert(0, after[lower - 1].text)
                meant_words.insert(0, after[lower - 1].text)
            if not after[upper - 1].sentence_end and upper < len(after) and upper in matched and name_part(upper):
                heard_words.append(after[upper].text)
                meant_words.append(after[upper].text)
        pair = " ".join(heard_words), " ".join(meant_words)
        if pair not in fixes and max(map(len, pair)) <= 160:
            fixes.append(pair)
    return fixes[:8]


@dataclass
class _Span:
    identity: str
    pid: int
    pasted: str
    before: str
    after: str
    start: int
    latest: str
    expires: float

    def find(self, value: str) -> str | None:
        lower = 0
        if self.before:
            positions, offset = [], 0
            while (index := value.find(self.before, offset)) >= 0:
                positions.append(index + len(self.before))
                offset = index + 1
            if not positions:
                return None
            lower = min(positions, key=lambda pos: abs(pos - self.start))
        upper = value.find(self.after, lower) if self.after else len(value)
        if upper < lower or upper - lower > max(200, len(self.pasted) * 3):
            return None
        self.start = lower
        return value[lower:upper]


class CorrectionObserver:
    """Call poll with an already-read safe field. No field text is logged or emitted."""
    def __init__(self, safe, *, words: WordList | None = None, clock=time.monotonic):
        self.safe, self.words, self.clock = safe, words or ConservativeWords(), clock
        self.enabled = True
        self._waiting: tuple[Focus, str, float] | None = None
        self._watch: _Span | None = None
        self._ready: list[tuple[str, str]] = []

    @property
    def active(self) -> bool:
        return self.enabled and bool(self._waiting or self._watch)

    def enable(self, on: bool) -> None:
        self.enabled = bool(on)
        if not on:
            self._waiting = self._watch = None
            self._ready.clear()

    def cancel(self) -> None:
        """An automated edit or undo must never be mistaken for the user's spelling fix."""
        self._waiting = self._watch = None

    def pasted(self, before: Focus, text: str) -> None:
        if not self.enabled or not text.strip() or not self.safe(before) or len(before.text) >= 16000:
            self._finish()
            return
        if self._waiting and self._same(self._waiting[0].identity, self._waiting[0].pid, before):
            original, previous, _ = self._waiting
            self._waiting = original, previous + text, self.clock() + 0.3
        elif len(text.split()) <= 200:
            self._waiting = before, text, self.clock() + 0.3

    def poll(self, snapshot: Focus | None) -> None:
        if not self.enabled:
            return
        if self._waiting:
            before, pasted, ready = self._waiting
            if self.clock() < ready:
                return
            self._waiting = None
            if not self._same(before.identity, before.pid, snapshot):
                self._finish()
                return
            watch = self._watch
            if watch and self._same(watch.identity, watch.pid, snapshot):
                combined = watch.find(snapshot.text)
                if combined == watch.latest + pasted and len((watch.pasted + pasted).split()) <= 200:
                    watch.pasted += pasted
                    watch.latest = combined
                    watch.expires = self.clock() + 45
                    return
            self._finish()
            start, matches = 0, []
            while (index := snapshot.text.find(pasted, start)) >= 0:
                if snapshot.text[:index] + snapshot.text[index + len(pasted):] == before.text:
                    matches.append(index)
                start = index + 1
            if len(matches) != 1:
                return
            lower, upper = matches[0], matches[0] + len(pasted)
            self._watch = _Span(before.identity, before.pid, pasted, snapshot.text[max(0, lower - 24):lower],
                                snapshot.text[upper:upper + 24], lower, pasted, self.clock() + 45)
            return
        watch = self._watch
        if watch is None:
            return
        if self.clock() >= watch.expires or not self._same(watch.identity, watch.pid, snapshot):
            self._finish()
            return
        current = watch.find(snapshot.text)
        if current is None or not current.strip():
            self._finish()
        else:
            watch.latest = current

    def _same(self, identity, pid, snapshot) -> bool:
        return bool(snapshot and self.safe(snapshot) and len(snapshot.text) < 16000 and
                    snapshot.identity == identity and snapshot.pid == pid)

    def _finish(self) -> None:
        if self._watch and self.enabled:
            self._ready.extend(correction_pairs(self._watch.pasted, self._watch.latest, self.words))
        self._watch = None
        self._waiting = None

    def take(self) -> list[tuple[str, str]]:
        ready, self._ready = self._ready[:8], []
        return ready
