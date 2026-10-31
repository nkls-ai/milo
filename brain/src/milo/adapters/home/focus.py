"""Focus and Do Not Disturb on macOS, through Shortcuts (ADR 0037).

macOS has no public way for an app to switch a Focus. Shortcuts' "Set Focus" action can, so Milo runs a shortcut:
"Milo Do Not Disturb On" and "Milo Do Not Disturb Off" for Do Not Disturb, or the user's own for another Focus,
found by its name ("Work Focus on", „Arbeit an“).

Milo makes the two Do Not Disturb shortcuts himself when they are missing (`offer`): each is a one-action workflow
written as a property list, signed with `shortcuts sign --mode anyone` (Apple's signing service, a few seconds) and
opened, so Shortcuts shows its "Add Shortcut" sheet. The user clicks Add on each, once. Another Focus has an id
Milo can't know (the user's own Focus modes have made-up ones), so for those the user makes the shortcuts.
"""

from __future__ import annotations

import logging
import plistlib
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from milo.core.home import NotSetUp
from milo.core.types import ToolError

from .apple_home import LIST_TIMEOUT_S, RUN_TIMEOUT_S, Runner, _shortcuts

log = logging.getLogger("milo.focus")

SIGN_TIMEOUT_S = 60
DND = "Do Not Disturb"
OWN = {True: f"Milo {DND} On", False: f"Milo {DND} Off"}
"""The shortcuts Milo makes for Do Not Disturb."""
DND_MODE = "com.apple.donotdisturb.mode.default"
_DND_NAMES = frozenset({"", "dnd", "do not disturb", "nicht stören", "nicht stoeren", "bitte nicht stören"})
_ON = frozenset({"on", "an", "ein", "start", "einschalten", "anschalten"})
_OFF = frozenset({"off", "aus", "stop", "end", "ausschalten", "beenden"})
_FILLER = frozenset({"focus", "fokus", "mode", "modus", "turn", "switch", "set", "milo", "schalte", "the", "der",
                     "den", "die"})


def workflow(on: bool) -> dict:
    """A shortcut with one Set Focus action: Do Not Disturb on until turned off, or off."""
    parameters = {"Enabled": 1 if on else 0,
                  "FocusModes": {"Identifier": DND_MODE, "DisplayString": DND}}
    if on:
        parameters["AssertionType"] = "Turned Off"
    return {
        "WFWorkflowClientVersion": "2605.0.5",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 1440408063, "WFWorkflowIconGlyphNumber": 59446},
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowTypes": [],
        "WFQuickActionSurfaces": [],
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowActions": [{"WFWorkflowActionIdentifier": "is.workflow.actions.dnd.set",
                               "WFWorkflowActionParameters": parameters}],
    }


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold())


def _is_dnd(name: str) -> bool:
    return " ".join(w for w in _words(name) if w not in _FILLER) in _DND_NAMES


class ShortcutsFocus:
    def __init__(self, folder: Path, *, run: Runner | None = None, opener: Runner | None = None):
        self.folder = folder
        """Where the made shortcuts are kept, signed, so a second offer doesn't sign them again."""
        self._run = run or _shortcuts
        self._open = opener or _open

    def set(self, on: bool, name: str = "") -> None:
        shortcut = self._find(on, name)
        if shortcut is None:
            raise NotSetUp(f"There's no shortcut to turn {name or DND} {'on' if on else 'off'}.")
        self._run(["shortcuts", "run", shortcut], RUN_TIMEOUT_S)

    def offer(self, name: str = "") -> bool:
        if not _is_dnd(name):
            return False
        self.folder.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(2) as pool:
            files = list(pool.map(self._signed, (True, False)))
        for file in files:
            self._open(["open", str(file)], LIST_TIMEOUT_S)
        return True

    def _find(self, on: bool, name: str) -> str | None:
        """The shortcut that turns `name` on or off: Milo's own for Do Not Disturb, else the user's whose name holds
        the Focus's words and an on or off word."""
        listed = [n.strip() for n in self._run(["shortcuts", "list"], LIST_TIMEOUT_S).splitlines() if n.strip()]
        if _is_dnd(name) and OWN[on] in listed:
            return OWN[on]
        switch = _ON if on else _OFF
        for shortcut in listed:
            words = _words(shortcut)
            if not set(words) & switch:
                continue
            rest = [w for w in words if w not in _FILLER and w not in _ON | _OFF]
            if (_is_dnd(name) and _is_dnd(" ".join(rest))) or (not _is_dnd(name) and rest == [
                    w for w in _words(name) if w not in _FILLER]):
                return shortcut
        return None

    def _signed(self, on: bool) -> Path:
        signed = self.folder / f"{OWN[on]}.shortcut"
        if signed.exists():
            return signed
        unsigned = self.folder / f"{OWN[on]}.unsigned.shortcut"
        unsigned.write_bytes(plistlib.dumps(workflow(on), fmt=plistlib.FMT_BINARY))
        try:
            self._run(["shortcuts", "sign", "--mode", "anyone", "--input", str(unsigned), "--output", str(signed)],
                      SIGN_TIMEOUT_S)
        finally:
            unsigned.unlink(missing_ok=True)
        if not signed.exists():
            raise ToolError("Shortcuts couldn't sign the shortcut Milo made.")
        return signed


def _open(cmd: list[str], timeout_s: float) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        raise ToolError("I couldn't open the shortcut for you.") from None
    if done.returncode != 0:
        raise ToolError("I couldn't open the shortcut for you.")
    return done.stdout
