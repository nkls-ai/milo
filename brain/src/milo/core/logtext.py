"""What brain log lines may contain.

The log keeps sizes and timings. What the user said, Milo's replies, remembered facts and reminder texts
show up only after `[logging] content = true`, which is for debugging and off by default.
"""

from __future__ import annotations

_content = False


def log_content(on: bool) -> None:
    global _content
    _content = on


def private(text: object) -> str:
    """`text` itself for a log line when content logging is on, otherwise only its size."""
    text = str(text)
    return repr(text) if _content else f"<{len(text)} chars>"
