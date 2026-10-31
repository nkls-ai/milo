"""Apple Home through the user's own shortcuts (ADR 0037).

A Mac app can't reach HomeKit: that needs an entitlement Apple gives only to apps it reviews. Shortcuts can, so the
user's Home scenes and devices come in as shortcuts in one folder ("Milo Home", `[home.apple_home] folder`), listed
with `shortcuts list --folder-name`. Without that folder, the user's shortcuts whose names say something about the
home (lights, heating, blinds, a scene, a lock...) count.

A shortcut's name says what it does. "Living room lights on" and "Living room lights off" are one device, "Living room
lights", that can go on and off; "Wohnzimmer Licht an" and „Licht aus“ too. "Lock front door", "Garage open",
"Alarm arm" and their German words work the same. "Heating set" or "Licht dimmen" gets the level as its input. A
shortcut without such a word ("Movie night", „Gute Nacht“) is a scene. A name that says lock, door, garage, gate or
alarm (or Schloss, Tür, Tor, Alarm) is a lock, a garage or an alarm: it asks first, whatever it does.

Shortcuts don't say how a device is, so its state is "" and Undo runs the opposite shortcut.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.home import Device
from milo.core.registry import HOMES, AdapterContext, options_from
from milo.core.types import ToolError

LIST_TIMEOUT_S = 30
RUN_TIMEOUT_S = 120

Runner = Callable[[list[str], float], str]
"""Runs a `shortcuts` command and returns its output; raises ToolError. Tests pass a fake."""

_ACTIONS: tuple[tuple[str, str], ...] = (
    ("turn on", "on"), ("turn off", "off"), ("switch on", "on"), ("switch off", "off"),
    ("on", "on"), ("off", "off"), ("an", "on"), ("ein", "on"), ("aus", "off"), ("einschalten", "on"),
    ("ausschalten", "off"), ("anschalten", "on"), ("toggle", "toggle"), ("umschalten", "toggle"),
    ("set", "set"), ("dim", "set"), ("dimmen", "set"), ("level", "set"), ("helligkeit", "set"),
    ("temperature", "set"), ("temperatur", "set"),
    ("open", "open"), ("close", "close"), ("öffnen", "open"), ("schließen", "close"), ("auf", "open"), ("zu", "close"),
    ("up", "open"), ("down", "close"), ("hoch", "open"), ("runter", "close"),
    ("unlock", "unlock"), ("lock", "lock"), ("aufschließen", "unlock"), ("abschließen", "lock"),
    ("aufsperren", "unlock"), ("zusperren", "lock"), ("entriegeln", "unlock"), ("verriegeln", "lock"),
    ("disarm", "disarm"), ("arm", "arm"), ("unscharf", "disarm"), ("scharf", "arm"),
)
"""Words at the end of a shortcut's name that say what it does."""
_FIRST = frozenset({"turn on", "turn off", "switch on", "switch off", "toggle", "set", "dim", "open", "close", "lock",
                    "unlock", "arm", "disarm"})
"""The ones that may start it too, English style ("Turn on Kitchen light"). German puts them at the end, and „Zu
Hause“ isn't closing anything."""
_LOCK = re.compile(r"lock|schloss|schließ|sperr|riegel|door|tür|tuer", re.IGNORECASE)
_GARAGE = re.compile(r"garage|\bgate\b|\btor\b|[nf]tor\b|\btore\b", re.IGNORECASE)
_ALARM = re.compile(r"alarm|scharf", re.IGNORECASE)
"""A name that says who can get in: these ask every time (core.home.SECURE)."""
_KIND_WORDS = (
    ("light", re.compile(r"light|lamp|licht|lampe|leuchte", re.IGNORECASE)),
    ("climate", re.compile(r"heat|thermostat|heizung|klima|temperat", re.IGNORECASE)),
    ("cover", re.compile(r"blind|shutter|curtain|rollo|rolllad|rollad|jalousie|vorhang|vorhäng|markise", re.IGNORECASE)),
    ("fan", re.compile(r"\bfan\b|ventilator|lüfter", re.IGNORECASE)),
    ("switch", re.compile(r"plug|socket|outlet|steckdose|switch|schalter", re.IGNORECASE)),
)
_HOMEISH = re.compile(r"scene|szene|home|zuhause", re.IGNORECASE)
"""Without the folder, a shortcut counts as a home one when its name says one of these or a kind's word."""


@dataclass(frozen=True)
class AppleHomeOptions:
    folder: str = "Milo Home"


@dataclass(frozen=True)
class _Parsed:
    device: str
    do: str
    """"" for a scene."""


def parse(name: str) -> _Parsed:
    """What a shortcut's name says: the device and the action at its start or end ("Turn on Kitchen light",
    "Kitchen light on", „Licht aus“), or the whole name as a scene."""
    words = name.split()
    folded = [w.casefold().strip(".,:;!-–") for w in words]
    for phrase, do in sorted(_ACTIONS, key=lambda a: -len(a[0].split())):
        said = phrase.casefold().split()  # casefold makes "ß" "ss"
        n = len(said)
        if len(words) <= n:
            continue
        if folded[-n:] == said:
            return _Parsed(" ".join(words[:-n]).strip(" -–:"), do)
        if phrase in _FIRST and folded[:n] == said:
            return _Parsed(" ".join(words[n:]).strip(" -–:"), do)
    return _Parsed(name.strip(), "")


def kind_of(name: str, do: str) -> str:
    if _GARAGE.search(name):
        return "garage"
    if _ALARM.search(name) or do in ("arm", "disarm"):
        return "alarm"
    if _LOCK.search(name) or do in ("lock", "unlock"):
        return "lock"
    for kind, pattern in _KIND_WORDS:
        if pattern.search(name):
            return kind
    if not do:
        return "scene"
    if do in ("open", "close"):
        return "cover"
    return "switch"


class AppleHome:
    name = "Apple Home"
    setup = "shortcuts"

    def __init__(self, folder: str = "Milo Home", *, run: Runner | None = None):
        self.folder = folder
        self._run = run or _shortcuts

    def devices(self) -> list[Device]:
        return list(self._devices()[0].values())

    def act(self, id: str, do: str, value: str = "") -> Device | None:
        _, shortcuts = self._devices()
        name = shortcuts.get((id, do))
        if name is None:
            raise ToolError(f"There's no shortcut to {do} “{id}”.")
        self._shortcut(name, value if do == "set" else "")
        return None

    def _devices(self) -> tuple[dict[str, Device], dict[tuple[str, str], str]]:
        """The devices by id (their name, folded), and the shortcut for each (device, action)."""
        names = self._list()
        actions: dict[str, dict[str, str]] = {}
        shown: dict[str, str] = {}
        for shortcut in names:
            parsed = parse(shortcut)
            key = parsed.device.casefold()
            shown.setdefault(key, parsed.device)
            actions.setdefault(key, {})[parsed.do or "run"] = shortcut
        devices, shortcuts = {}, {}
        for key, does in actions.items():
            # A lone "Movie night on" is a scene called "Movie night"; with an "off" it is a device.
            kind = kind_of(shown[key], "" if set(does) <= {"run"} else next(iter(does)))
            if kind == "switch" and set(does) == {"on"}:
                kind = "scene"
            if kind == "scene":
                does = {"run": next(iter(does.values()))}
            devices[key] = Device(key, shown[key], kind, does=tuple(does))
            shortcuts.update({(key, do): name for do, name in does.items()})
        return devices, shortcuts

    def _list(self) -> list[str]:
        """The shortcuts in the folder; without the folder, the user's shortcuts whose names are about the home. A
        folder that isn't there lists as empty, so the folders are asked first."""
        folders = self._run(["shortcuts", "list", "--folders"], LIST_TIMEOUT_S).splitlines()
        if any(f.strip().casefold() == self.folder.casefold() for f in folders):
            listed = self._run(["shortcuts", "list", "--folder-name", self.folder], LIST_TIMEOUT_S)
            return [n.strip() for n in listed.splitlines() if n.strip()]
        listed = self._run(["shortcuts", "list"], LIST_TIMEOUT_S)
        return [n.strip() for n in listed.splitlines() if n.strip() and _homeish(n.strip())]

    def _shortcut(self, name: str, given: str) -> str:
        with tempfile.TemporaryDirectory(prefix="milo-home-") as tmp:
            cmd = ["shortcuts", "run", name]
            if given:
                path = Path(tmp) / "input.txt"
                path.write_text(given, encoding="utf-8")
                cmd += ["--input-path", str(path)]
            return self._run(cmd, RUN_TIMEOUT_S)


def _homeish(name: str) -> bool:
    parsed = parse(name)
    return bool(_HOMEISH.search(name) or _LOCK.search(name) or _GARAGE.search(name) or _ALARM.search(name)
                or any(p.search(name) for _, p in _KIND_WORDS)) and (bool(parsed.do) or bool(_HOMEISH.search(name)))


def _shortcuts(cmd: list[str], timeout_s: float) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise ToolError("The shortcut took too long, so I stopped waiting.") from None
    except OSError:
        raise ToolError("I couldn't reach the Shortcuts app.") from None
    if done.returncode != 0:
        raise ToolError("The shortcut didn't work: " + (done.stderr.strip().splitlines() or ["no reason given"])[-1])
    return done.stdout


@HOMES.register("apple_home")
def _apple_home(options: Mapping[str, Any], ctx: AdapterContext) -> AppleHome:
    return AppleHome(options_from(AppleHomeOptions, options, "home.apple_home").folder)
