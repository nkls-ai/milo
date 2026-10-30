"""Vectors from hashed words and word pieces: no model, no download, no memory to speak of.

Finds text sharing words or parts of words ("Zahnarzt" in "Zahnarzttermin"), not meaning. The tests and the
CI eval use it; `[memory] embedder = "hash"` is the choice for a Mac without room for a model.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from milo.core.registry import EMBEDDERS, AdapterContext, options_from

_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class HashOptions:
    dimensions: int = 384


class HashEmbedder:
    name = "hash"
    relevant_margin = 0.25
    """Text sharing a word or two lands this far above unrelated text, which sits near 0."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions
        self.key = f"hash:{dimensions}"
        self.calls = 0

    def warm(self) -> None:
        pass

    def embed(self, texts: Sequence[str], *, query: bool = False) -> np.ndarray:
        self.calls += 1
        out = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature, weight in _features(text):
                h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "little")
                out[row, h % self.dimensions] += weight if (h >> 63) & 1 else -weight
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norms, 1e-9)


def _features(text: str):
    for word in _WORD.findall(text.lower()):
        yield "w:" + word, 1.0
        padded = f"<{word}>"
        for i in range(len(padded) - 3):
            yield "g:" + padded[i:i + 4], 0.35


@EMBEDDERS.register("hash")
def _hash(options: Mapping[str, Any], ctx: AdapterContext) -> HashEmbedder:
    return HashEmbedder(**vars(options_from(HashOptions, options, "memory.hash")))
