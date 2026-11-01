"""protocol/design.json is the one source of Milo's look: the generated files are current and the Mac reads them."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VIEWS = ROOT / "app" / "Sources" / "MiloKit" / "Views"


def test_generated_tokens_are_up_to_date():
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen-design-tokens.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_palette_and_theme_take_every_colour_from_the_tokens():
    palette = (VIEWS / "Palette.swift").read_text(encoding="utf-8")
    theme = (ROOT / "app" / "Sources" / "MiloKit" / "Theme.swift").read_text(encoding="utf-8")
    rig = (VIEWS / "Wren" / "WrenRig.swift").read_text(encoding="utf-8")
    for name, source in (("Palette.swift", palette), ("Theme.swift", theme)):
        assert not re.search(r"Color\(red:|rgb\(\d|srgbRed:|withAlphaComponent\(0", source), name
    assert re.findall(r"static let \w+ = DesignTokens\.\w+", palette)
    for token in ("primary", "tint", "accent", "ink", "glow", "onPrimary", "card", "rule"):
        assert f"DesignTokens.{token}" in theme, token
    assert "DesignTokens.springResponse" in theme and "DesignTokens.reducedFade" in theme
    # the rig's colours: no hex literal left
    assert not re.search(r"rgb\(0x[0-9A-Fa-f]{6}", rig)


def test_gentle_is_the_mac_formula():
    """ThemeMotion.gentle is response × 1.6, damping + 0.15; design.json's gentle must say the same."""
    from milo.desktop.design import load_tokens

    motion = load_tokens()["motion"]
    assert motion["gentle"]["response"] == round(motion["spring"]["response"] * 1.6, 3)
    assert motion["gentle"]["damping"] == round(min(1, motion["spring"]["damping"] + 0.15), 3)
