"""Keys in the words of the keyboard in front of the user: "Right Option" and "Control-Option-M" on a Mac,
"Right Alt" and "Ctrl+Alt+M" on a PC. Plain data per platform (`Platform.key_names`, filled in by
`milo.adapters.key_names`, ADR 0027); config.toml and the wire keep the neutral names (`right_option`,
`ctrl+option+m`)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyNames:
    keys: tuple[tuple[str, str], ...]
    """Push-to-talk key name -> label."""
    modifiers: tuple[tuple[str, str], ...]
    """Combo part -> label, for `ctrl+option+m`."""
    separator: str
    off: str = "Off"

    def key(self, name: str) -> str:
        return dict(self.keys).get(name) or name.replace("_", " ").title()

    def combo(self, combo: str) -> str:
        """`ctrl+option+m` -> "Control-Option-M" or "Ctrl+Alt+M"; "" -> "Off"."""
        if not combo:
            return self.off
        names = dict(self.modifiers)
        parts = [p for p in combo.casefold().replace(" ", "").split("+") if p]
        return self.separator.join(names.get(p) or (p.upper() if len(p) == 1 else p.capitalize()) for p in parts)


PLAIN_KEY_NAMES = KeyNames(keys=(), modifiers=(), separator="+")
"""The neutral names, title-cased, for a platform that names none of its own."""
