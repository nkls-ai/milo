"""The recall eval in CI: scripted weeks of memory, asked 30 questions, with the hashing embedder. The real
embedder's numbers come from `uv run python -m milo.memory.recall_eval --embedder mlx_e5`."""

from __future__ import annotations

import statistics

from milo.adapters.embed.hashing import HashEmbedder
from milo.memory.recall_eval import run


def test_recall_finds_most_answers_within_the_budget():
    score = run(HashEmbedder(), budget=800)
    assert score.hit_rate >= 0.8, score.misses
    assert max(score.tokens) <= 800
    assert statistics.mean(score.tokens) < 200, "most turns carry little"


def test_recall_stays_fast_over_thousands_of_items():
    score = run(HashEmbedder(), budget=800, scale=10)
    assert score.items > 3000
    assert statistics.median(score.millis) < 50, score.report()
