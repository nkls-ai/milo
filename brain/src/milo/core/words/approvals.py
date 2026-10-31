"""What Approvals says around a yes-or-no question (services/approvals.py)."""

from __future__ import annotations

WORDS: dict[str, dict[str, str]] = {
    "no_answer": {"en": "No answer, so I left it.", "de": "Keine Antwort, also habe ich es gelassen."},
    "money_yes": {"en": "That one involves money, so only a click on Yes counts.",
                  "de": "Da geht es um Geld, deshalb zählt nur ein Klick auf Ja."},
    "see_window": {"en": " (all of it is in the Milo window)", "de": " (alles steht im Milo-Fenster)"},
}
