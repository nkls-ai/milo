"""Everything Milo says, asks or shows in words, in one catalogue keyed by (key, language).

Each area keeps its templates in a module of its own (`acts`, `talk`, `hands`, …), a dict of key to
{language code: template}. Here they are merged under the area's name: `say("acts.event", "de", title=…, when=…)`.
A language a key has no template for gets the English one, so every key has English. Days, dates, clock times and
spans are in `dates`.

Only the words live here. Which key a situation needs, and the values that go in, stay with the service that
knows the situation.
"""

from __future__ import annotations

from collections.abc import Mapping

from . import acts, talk

LANGS = ("en", "de")
"""The languages Milo has all his lines in. Another one falls back to English."""

Table = Mapping[str, Mapping[str, str]]

AREAS: dict[str, Table] = {"acts": acts.LINES, "acts.ask": acts.QUESTIONS, "talk": talk.WORDS}

CATALOGUE: dict[str, Mapping[str, str]] = {f"{area}.{key}": templates
                                           for area, table in AREAS.items() for key, templates in table.items()}


def language(code: str) -> str:
    """The language of the message being answered, if Milo has lines in it, else English."""
    return code if code in LANGS else "en"


def say(key: str, lang: str = "en", **values: object) -> str:
    """The template for `key` in `lang` (English if it has none), filled in with `values`."""
    templates = CATALOGUE[key]
    return templates.get(lang, templates["en"]).format(**values)


def has(key: str) -> bool:
    return key in CATALOGUE
