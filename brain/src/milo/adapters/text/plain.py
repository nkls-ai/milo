"""Dictation cleanup that keeps every word: tidy whitespace and punctuation, capitalize the start."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from milo.core.registry import TEXT_CLEANERS, AdapterContext, options_from


def tidy(text: str) -> str:
    """No space before punctuation, single spaces, no leading stray punctuation, capital first letter."""
    text = re.sub(r"\s+([,.!?;:])", r"\1", text.strip())
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"^[,.;:]\s*", "", text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


@dataclass(frozen=True)
class PlainOptions:
    """No options. Still parsed, so a stray [dictation.plain] key fails loudly."""


class PlainCleaner:
    def clean(self, text: str) -> str:
        return tidy(text)


@TEXT_CLEANERS.register("plain")
def _plain(options: Mapping[str, Any], ctx: AdapterContext) -> PlainCleaner:
    options_from(PlainOptions, options, "dictation.plain")
    return PlainCleaner()
