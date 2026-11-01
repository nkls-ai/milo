"""The push-to-talk keys in words, as the user finds them on this keyboard."""
from __future__ import annotations


def key_label(key: str) -> str:
    from ..platform import key_label as platform_label  # one label per OS, in the platform layer
    return platform_label(key)
