"""Tasks that repeat: what a task asks for with the things that change between times taken out.

"Make the sales report for September" and "the sales report for October please" have the same shape. Routines
use this to offer to keep a task the user keeps asking for. Pure: no I/O.
"""

from __future__ import annotations

import re

STOP = frozenset("""
a an the and or of for to in on at by with from into this that these those it its my me our your their his her
please can could would you will just also some all any each every new then than there here what which who how
when where do does did make makes made get got put let me us be is are was were been have has had not no so as
""".split())

CHANGES = frozenset("""
january february march april may june july august september october november december
jan feb mar apr jun jul aug sep sept oct nov dec
monday tuesday wednesday thursday friday saturday sunday mon tue wed thu fri sat sun
today tomorrow yesterday week weeks month months year years last next this morning afternoon evening tonight
""".split())
"""Words for when: they change from one time to the next, so they don't count."""

ALIKE = 0.6
"""Shared words over all words, for two tasks to count as the same kind."""


def shape(text: str) -> frozenset[str]:
    """The words that say what a task is about: lowercase, without numbers, filler and words for when.
    A plural 's' goes, so "reports" and "report" match."""
    words = set()
    for word in re.findall(r"[^\W\d_]+", text.lower()):
        if len(word) < 3 or word in STOP or word in CHANGES:
            continue
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.add(word)
    return frozenset(words)


def alike(a: frozenset[str], b: frozenset[str], threshold: float = ALIKE) -> bool:
    """Two shapes of the same kind of task. Shapes of fewer than two words never are: too little to tell."""
    if len(a) < 2 or len(b) < 2:
        return False
    return len(a & b) / len(a | b) >= threshold
