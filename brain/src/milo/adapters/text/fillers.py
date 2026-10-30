"""Dictation cleanup that drops filler words ("um", "äh") for the configured languages, then tidies."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from milo.core.registry import TEXT_CLEANERS, AdapterContext, ConfigError, options_from

from .plain import tidy

# Regex per filler word, so stretched forms ("ummm", "ähhh") match too. Whole words only.
FILLERS: dict[str, tuple[str, ...]] = {
    "en": (r"u+m+", r"u+h+", r"e+r+m+", r"h+m+"),  # um, uh, erm, hmm
    "de": (r"ä+h+m*", r"ö+h+m*", r"h+m+"),  # äh, ähm, öh, öhm, hm
}


@dataclass(frozen=True)
class FillersOptions:
    languages: tuple[str, ...] = ("en", "de")


class FillerCleaner:
    def __init__(self, languages: Iterable[str]):
        words = sorted({w for lang in languages for w in FILLERS[lang]}, key=len, reverse=True)
        self._re = (re.compile(rf"(?<![\w-])(?:{'|'.join(words)})(?![\w-])[,.]?\s*", re.IGNORECASE)
                    if words else None)

    def clean(self, text: str) -> str:
        if self._re is not None:
            text = self._re.sub("", text.strip())
        return tidy(text)


@TEXT_CLEANERS.register("fillers")
def _fillers(options: Mapping[str, Any], ctx: AdapterContext) -> FillerCleaner:
    o = options_from(FillersOptions, options, "dictation.fillers")
    if isinstance(o.languages, str):
        raise ConfigError('[dictation.fillers] languages must be a list, e.g. ["en", "de"]')
    unknown = sorted(set(o.languages) - set(FILLERS))
    if unknown:
        raise ConfigError(f"unknown language(s) in [dictation.fillers] languages: {', '.join(unknown)}; "
                          f"available: {', '.join(sorted(FILLERS))}")
    return FillerCleaner(o.languages)
