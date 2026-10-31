"""Which of Milo's tools and instructions a helper gets, read from the task's own words.

Every tool a worker has costs tokens on every model call of its turn, and Codex repeats a tool server's
instructions in each of its tools' descriptions. So a helper gets the connections its task names ("Lies die
Termine im Kalender" -> the calendar), the sections of AGENTS.md those need, and the Mac tools only when it works
on the screen. A task whose kind isn't clear gets everything, as before; a helper that finds a tool missing says
NEEDS_TOOLS and runs again with all of them (services/task_runner.py).

Pure: words in, a scope out. The brain picks the scope; the connection server (milo.connect) serves only the
tools `server_env` names, and the worker adapters trim the instructions with `trim_instructions`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .types import ToolServer

CONNECT_SERVER = "milo"
"""The MCP server with Milo's app connections, memory and his own tools (milo.connect)."""
TOOLS_ENV = "MILO_TOOLS"
"""Tells the connection server which kinds to serve, comma-separated. Unset: all of them."""

_W = re.IGNORECASE | re.UNICODE
KINDS: dict[str, re.Pattern[str]] = {
    "calendar": re.compile(r"calendar|kalender|termin|appointment|\bmeetings?\b|besprechung|\bevents?\b|schedule|"
                           r"agenda|calendrier|rendez-vous|\bcitas?\b|reuni[oó]n", _W),
    "reminders": re.compile(r"remind|erinner|\bto-?dos?\b|aufgabe|\blists?\b|liste|rappel|recordatorio", _W),
    "mail": re.compile(r"e-?mails?\b|\bmails?\b|inbox|posteingang|draft|entwurf|forward|weiterleit|\breply\b|"
                       r"antwort|courriel|correo", _W),
    "notes": re.compile(r"\bnotes?\b|notiz|\blists?\b|liste|memo", _W),
    "shortcuts": re.compile(r"shortcut|kurzbefehl|weather|wetter|\blights?\b|licht|lampe?\b|raccourci|atajo", _W),
    "files": re.compile(r"\bfiles?\b|datei|document|dokument|folder|ordner|download|desktop|schreibtisch|\bpdfs?\b|"
                        r"invoice|rechnung|\bbills?\b|contract|vertrag|fichier|archivo|carpeta|\bscans?\b", _W),
    "phone": re.compile(r"\bphone\b|handy|iphone|telefon|send (it )?(to )?me\b|schick (es )?mir", _W),
    "memory": re.compile(r"remember|forget|vergiss|merk dir|birthday|geburtstag|what did (we|i)|last time|"
                         r"letztes mal|do you know|wei(ß|ss)t du|\bmy (wife|husband|sister|brother|mother|mum|mom|"
                         r"father|dad|son|daughter|partner)\b|meine? (frau|mann|schwester|bruder|mutter|vater|sohn|"
                         r"tochter)\b|sister|schwester", _W),
    "install": re.compile(r"\binstall|installier|\bupgrade|homebrew|\bbrew\b|\bnpm\b|\bpipx?\b|\buv tool", _W),
}
"""The connections, Milo's memory and installing programs (install_package), each with the words that name it in a
task (English, German, a little French and Spanish). A list could be a note or a reminder list, so it names both
(AGENTS.md: look in both)."""
_WEB = re.compile(r"\bweb\b|internet|online|google|recherch|im netz|website|webseite", _W)
"""Work on the web only: it needs none of the connections, which makes the task's kind known."""
_APP_KINDS = frozenset({"calendar", "reminders", "mail", "notes", "shortcuts", "files", "phone"})
_UNDO_KINDS = frozenset({"calendar", "reminders", "notes", "files"})


@dataclass(frozen=True)
class ToolScope:
    kinds: frozenset[str] | None
    """The connections (and "memory") the helper gets; None: every one of them."""
    screen: bool = False
    """It works on the screen, with the Mac tools."""

    @property
    def simple(self) -> bool:
        """Off the screen with a known, short list of connections: a reading or filing job a light model does well."""
        return not self.screen and self.kinds is not None

    def servers(self, servers: tuple[ToolServer, ...]) -> tuple[ToolServer, ...]:
        """`servers` with the connection server told what to serve."""
        extra = server_env(self)
        return tuple(replace(s, env=(*s.env, *extra)) if s.name == CONNECT_SERVER and extra else s for s in servers)


ALL = ToolScope(None)
"""Every connection, no screen: what a helper got before scopes, and what a NEEDS_TOOLS helper gets."""


def scope_for(text: str, *, screen: bool) -> ToolScope:
    """The tools a task needs, from its description. Unclear words mean every connection; a screen task always
    knows its scope (the Mac tools plus whatever connections it names)."""
    kinds = frozenset(kind for kind, words in KINDS.items() if words.search(text))
    if kinds or screen or _WEB.search(text):
        return ToolScope(kinds, screen)
    return ToolScope(None, screen)


def server_env(scope: ToolScope) -> tuple[tuple[str, str], ...]:
    """The environment that limits the connection server to the scope; () for every tool."""
    if scope.kinds is None:
        return ()
    return ((TOOLS_ENV, ",".join(sorted(scope.kinds))),)


def served(env_value: str | None) -> frozenset[str] | None:
    """What the connection server serves for its TOOLS_ENV value: None (unset) means everything."""
    if env_value is None:
        return None
    return frozenset(k for k in (part.strip() for part in env_value.split(",")) if k)


# AGENTS.md sections by their heading, and when a helper needs them. A heading not named here (one the user added)
# is always kept.
_SECTIONS = {
    "the user's apps": lambda s: s.kinds is None or bool(s.kinds & _APP_KINDS),
    "using the mac": lambda s: s.screen,
    "undo": lambda s: s.kinds is None or s.screen or bool(s.kinds & _UNDO_KINDS),
    "memory": lambda s: s.kinds is None or "memory" in s.kinds,
    "reminders": lambda s: s.kinds is None or "reminders" in s.kinds,
    "routines": lambda s: s.kinds is None,
}


def trim_instructions(text: str, scope: ToolScope) -> str:
    """AGENTS.md without the `## ` sections this helper has no use for. Everything else stays as written."""
    kept: list[str] = []
    keep = True
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            rule = _SECTIONS.get(line[3:].strip().lower())
            keep = rule is None or rule(scope)
        if keep:
            kept.append(line)
    return "".join(kept)
