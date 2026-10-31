"""What Milo says when an <open> fails (services/opener.py)."""

from __future__ import annotations

WORDS: dict[str, dict[str, str]] = {
    "couldnt": {"en": "I couldn't open {what}.", "de": "Ich konnte {what} nicht öffnen."},
}
