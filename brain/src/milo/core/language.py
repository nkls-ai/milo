"""Which language a message is in, cheaply: the code the transcriber reported, else a guess from the words.

Milo answers in the language of the message he is answering, not of what he remembers. The speech engines say
which language they heard (Whisper detects it, ElevenLabs Scribe reports a `language_code`); typed text has no
engine, so `detect` guesses from common short words, which is enough to tell German from English in a sentence.
"""

from __future__ import annotations

import re
from collections.abc import Callable

NAMES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch",
         "pt": "Portuguese", "pl": "Polish", "sv": "Swedish", "da": "Danish", "no": "Norwegian", "fi": "Finnish",
         "tr": "Turkish", "ru": "Russian", "uk": "Ukrainian", "cs": "Czech", "ja": "Japanese", "zh": "Chinese",
         "ko": "Korean", "ar": "Arabic", "hi": "Hindi"}
"""Two-letter codes to the names a model reads."""

_THREE = {"eng": "en", "deu": "de", "ger": "de", "fra": "fr", "fre": "fr", "spa": "es", "ita": "it", "nld": "nl",
          "dut": "nl", "por": "pt", "pol": "pl", "swe": "sv", "dan": "da", "nor": "no", "nob": "no", "fin": "fi",
          "tur": "tr", "rus": "ru", "ukr": "uk", "ces": "cs", "cze": "cs", "jpn": "ja", "zho": "zh", "chi": "zh",
          "cmn": "zh", "kor": "ko", "ara": "ar", "hin": "hi"}
_BY_NAME = {name.lower(): code for code, name in NAMES.items()}

_WORD = re.compile(r"[a-zäöüß']+")
_EN = frozenset("""the a an and or but is are was were be been it its this that these those you your i me my we our
they them their he she his her to of in on at for with from by as do does did not no yes can could would should
will what why how who where when which please open go get make show tell me just so now then there here have has
had into about up out all some any thanks thank okay hey hi hello morning bye""".split())
_DE = frozenset("""der die das den dem des ein eine einen einem einer und oder aber ist sind war waren sein bin bist
es ich mich mir mein meine du dich dir dein wir uns unser ihr sie er ihm ihn sein nicht kein keine ja nein kann
kannst könntest würde sollte wird was warum wie wer wo wann welche bitte öffne öffnen geh gehe mach mache zeig
zeige sag sage jetzt dann dort hier habe hast hat hatte auf zu mit von für bei aus nach über auch noch mal doch
danke schön okay hallo moin servus tschüss morgen""".split())


def normalize(code: str) -> str:
    """"en", "en-US", "eng" or "English" to "en". "" for nothing or something unknown."""
    code = (code or "").strip().lower().replace("_", "-")
    if not code:
        return ""
    if code in _BY_NAME:
        return _BY_NAME[code]
    base = code.split("-", 1)[0]
    if len(base) == 3:
        return _THREE.get(base, "")
    return base if len(base) == 2 and base.isalpha() else ""


def detect(text: str) -> str:
    """"en" or "de" when the words say so clearly, else "" (too short, mixed, or another language)."""
    words = _WORD.findall((text or "").lower())
    en = sum(w in _EN for w in words)
    de = sum(w in _DE for w in words) + sum(ch in "äöüß" for ch in "".join(words)) // 2
    if max(en, de) < 1 or en == de:
        return ""
    if len(words) >= 3 and max(en, de) < 2:
        return ""
    return "en" if en > de else "de"


def name(code: str) -> str:
    """The language's English name for a prompt ("German"), or the code itself if unknown."""
    code = normalize(code) or code
    return NAMES.get(code, code)


class SpokenLanguage:
    """The language of the user's latest message, shared by everything that speaks to them about it: the talker's
    reply, a helper's answer and the questions Milo asks while it works. Set once per turn by LiveTalk.

    `code`: the language to start in, the last one the user spoke before a restart, so a first "hi" isn't answered
    in a guessed language. `changed` is told each new one, to keep it for next time."""

    def __init__(self, code: str = "", changed: Callable[[str], None] | None = None):
        self.code = normalize(code)
        self._changed = changed

    def hear(self, text: str, reported: str = "") -> str:
        """A new message: the language its words clearly are, else the one its transcriber reported, else the one
        before (a short "okay" or "yes" keeps the conversation's language). Returns the code. The words go first:
        the reply should match them, and a transcriber hears English with a German accent as German now and then."""
        code = detect(text) or normalize(reported) or self.code
        if code != self.code and self._changed is not None:
            self._changed(code)
        self.code = code
        return self.code

    def get(self) -> str:
        return self.code
