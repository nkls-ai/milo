"""Platform risk vocabulary is data supplied to the shared action classifier."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskPolicy:
    code_apps: frozenset[str] = frozenset()
    settings_apps: frozenset[str] = frozenset()
    secret_apps: frozenset[str] = frozenset()
    file_apps: frozenset[str] = frozenset()
    trash_apps: frozenset[str] = frozenset()
    document_apps: frozenset[str] = frozenset()
    browsers: frozenset[str] = frozenset()
    key_aliases: tuple[tuple[str, str], ...] = ()
    risky_combos: tuple[tuple[str, str], ...] = ()
    key_labels: tuple[tuple[str, str], ...] = ()
    key_separator: str = ""


DEFAULT_RISK_POLICY = RiskPolicy()
