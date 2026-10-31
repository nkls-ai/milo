"""The user's home as Milo sees it (ADR 0037): devices, what can be done with each, and finding one by what the user
called it.

A home system (Home Assistant, Apple Home through the user's shortcuts) is an adapter behind the `Home` port
(core/ports.py). Here is only what every one of them shares: a device's kind, its state in plain words, and the
forgiving match from "the kitchen light" or „Licht in der Küche“ to "Kitchen ceiling light".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .types import ToolError

KINDS = ("light", "switch", "scene", "climate", "fan", "cover", "garage", "lock", "alarm", "other")
"""switch: plugs and anything else with on and off. cover: blinds, shutters, curtains. garage: a garage door or a
gate. scene: a scene or a script, which only runs."""
SECURE = ("lock", "garage", "alarm")
"""Who can get in: these ask every time, also in auto mode (the `lock` approval kind)."""
DOES = ("on", "off", "toggle", "set", "run", "open", "close", "lock", "unlock", "arm", "disarm")
"""What a device can do. Undo also uses "mode", which puts a heating back in the mode it was in ("heat")."""


@dataclass(frozen=True)
class Device:
    id: str
    """The home system's own id ("light.kitchen", or the name of the device's shortcuts)."""
    name: str
    kind: str
    room: str = ""
    state: str = ""
    """"on", "off", "open", "closed", "locked", "unlocked", "disarmed", "armed_away" and the like; a heating's mode
    ("heat", "off"); "" when the home doesn't say (shortcuts)."""
    level: float | None = None
    """A light's brightness and a blind's position in percent, a heating's target temperature in degrees."""
    does: tuple[str, ...] = ()
    """What `Home.act` can do with it, from DOES."""
    members: tuple[str, ...] = ()
    """A scene: the ids of the devices it sets, so Undo can put them back as they were."""


class NotSetUp(ToolError):
    """Milo has nothing yet to do this with (a Focus without its shortcut): the user has to add something once."""


# ---- finding a device by name

_FILLER = frozenset({
    "the", "a", "an", "my", "our", "all", "on", "of", "at", "to", "please", "lights", "both", "every",
    "der", "die", "das", "den", "dem", "des", "im", "in", "am", "vom", "von", "mein", "meine", "meinen", "unser",
    "unsere", "alle", "allen", "beide", "bitte", "zimmer",
})
"""Words that name no device. "lights" stays as a light word (`_SAME`) and also says "all of them" (`_MANY`)."""
_MANY = frozenset({"all", "lights", "lamps", "alle", "allen", "lichter", "lampen", "both", "beide", "every"})
"""The user means every device that matches, not one: "the kitchen lights", „alle Lichter“."""
_SAME = {
    "light": ("light", "lights", "lamp", "lamps", "licht", "lichter", "lampe", "lampen", "leuchte", "leuchten",
              "beleuchtung", "deckenlicht", "deckenlampe", "stehlampe"),
    "kitchen": ("kitchen", "küche", "kueche"),
    "living": ("living", "lounge", "wohnzimmer", "wohn", "stube"),
    "bedroom": ("bedroom", "schlafzimmer", "schlaf"),
    "bathroom": ("bathroom", "bath", "bad", "badezimmer"),
    "office": ("office", "study", "büro", "buero", "arbeitszimmer"),
    "hall": ("hall", "hallway", "corridor", "flur", "diele", "gang"),
    "garden": ("garden", "yard", "garten"),
    "heating": ("heating", "heat", "heater", "thermostat", "heizung", "climate", "klima"),
    "blinds": ("blinds", "blind", "shutters", "shutter", "curtains", "curtain", "rollo", "rollos", "rollladen",
               "rolladen", "jalousie", "jalousien", "vorhang", "vorhänge"),
    "plug": ("plug", "socket", "outlet", "steckdose"),
    "fan": ("fan", "ventilator", "lüfter"),
    "door": ("door", "tür", "tuer"),
    "front": ("front", "haus", "vorder", "eingang", "entrance"),
    "garage": ("garage", "garagentor"),
    "lock": ("lock", "schloss", "türschloss"),
    "alarm": ("alarm", "alarmanlage", "security"),
    "scene": ("scene", "szene", "stimmung"),
}
_CANON = {word.casefold(): canon for canon, words in _SAME.items() for word in words}
_KIND_WORD = {"light": "light", "climate": "heating", "cover": "blinds", "fan": "fan", "switch": "plug",
              "garage": "garage", "lock": "lock", "alarm": "alarm", "scene": "scene"}
"""The word a device's kind brings along: "the lights" are the lights, whatever each is called."""


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[^\W_]+", text.casefold()) if w]


def _expand(word: str) -> set[str]:
    """One word in a common form: synonyms and both languages as one (`_SAME`), a German compound as its known
    parts ("Küchenlicht" is kitchen and light), an English plural without its s."""
    if word in _CANON:
        return {_CANON[word]}
    parts = {canon for known, canon in _CANON.items() if len(known) >= 4 and known in word}
    if parts:
        return parts
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return {word[:-1]}
    return {word}


def _have(device: Device, *, extra: bool = False) -> set[str]:
    """The words a device answers to: its name, its room and its kind's word. extra=True: only its name's, in their
    common form, to count what the name says beyond the words said ("Desk lamp" says nothing more than "desk lamp",
    in whatever room)."""
    words = set()
    for said in _tokens(device.name if extra else f"{device.name} {device.room}"):
        words |= _expand(said) | (set() if extra else {said})
    if device.kind in _KIND_WORD:
        words.add(_KIND_WORD[device.kind])
    return words


def wanted_words(text: str) -> set[str]:
    return {w for raw in _tokens(text) if raw not in _FILLER or raw in _CANON for w in _expand(raw)}


def many(text: str) -> bool:
    """The words mean every device that matches ("the kitchen lights", „alle Lampen“)."""
    return any(w in _MANY for w in _tokens(text))


def find(devices: Sequence[Device], wanted: str, *, scene: bool | None = None) -> tuple[list[Device], bool]:
    """The devices `wanted` names, best first, and whether that is exactly one by its full name. `scene` True: only
    scenes; False: no scenes, unless only a scene matches (the model wrote a scene as a device). An exact name (or
    room and name) wins, and so does the one device whose words are just the words said; else every device whose
    words hold all the words said, the fewest extra words first."""
    pool = [d for d in devices if scene is None or (d.kind == "scene") == scene]
    if scene is False and not _find(pool, wanted)[0]:
        pool = [d for d in devices if d.kind == "scene"]
    return _find(pool, wanted)


def _find(pool: Sequence[Device], wanted: str) -> tuple[list[Device], bool]:
    said = " ".join(_tokens(wanted))
    exact = [d for d in pool if said in (" ".join(_tokens(d.name)), " ".join(_tokens(f"{d.room} {d.name}")))]
    if exact:
        return exact, True
    want = wanted_words(wanted)
    if not want:
        return [], False
    hits = [(len(_have(d, extra=True) - want), d) for d in pool if want <= _have(d)]
    hits.sort(key=lambda h: h[0])
    if not many(wanted) and hits and hits[0][0] == 0 and (len(hits) == 1 or hits[1][0] > 0):
        return [hits[0][1]], True  # "the kitchen light" is "Kitchen light", not "Kitchen light strip"
    return [d for _, d in hits], False
