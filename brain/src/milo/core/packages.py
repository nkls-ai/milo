"""Installing a program the user asked for, through a package manager (install_package).

A helper's shell has no network and writes only in its own folder (ADR 0020), so `brew install` or `npm install -g`
fail there. The worker asks the brain instead, which runs the package manager outside the sandbox. Only these
managers, only their plain install command, and only a package name: no URLs, paths, git sources, flags or extra
arguments, so a name can't turn into code or another command. No `sudo`, ever.

Pure: a manager and a name in, the command to run out. services/installs.py runs it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Manager:
    label: str
    """The manager as the user knows it, for the question ("Install “tree” with Homebrew?")."""
    command: tuple[str, ...]
    """The install command; the package goes last."""
    name: re.Pattern[str]
    """What a package name for it may look like."""
    example: str


_BREW = re.compile(r"[a-z0-9][a-z0-9._+@-]*(/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._+@-]*)?")
"""A formula or cask, maybe in a tap: `tree`, `python@3.12`, `hashicorp/tap/terraform`."""
_NPM = re.compile(r"(@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*(@[a-zA-Z0-9][a-zA-Z0-9._+~^<>=*-]*)?")
"""A registry package, maybe scoped and with a version or tag: `cowsay`, `@openai/codex`, `@openai/codex@latest`."""
_PYPI = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,-]+\])?(==[A-Za-z0-9.!+*-]+)?")
"""A PyPI project, maybe with extras and an exact version: `ruff`, `httpie`, `black==24.10.0`."""

MANAGERS: dict[str, Manager] = {
    "brew": Manager("Homebrew", ("brew", "install"), _BREW, "tree"),
    "brew_cask": Manager("Homebrew", ("brew", "install", "--cask"), _BREW, "codex"),
    "npm": Manager("npm", ("npm", "install", "--global", "--no-fund", "--no-audit"), _NPM, "@openai/codex"),
    "uv": Manager("uv", ("uv", "tool", "install"), _PYPI, "ruff"),
}
"""The managers Milo installs with, by the name the worker passes. Each installs for the user, without sudo."""

MAX_NAME = 120
_FILE = re.compile(r"\.(rb|tgz|tar|gz|bz2|xz|zip|whl|egg)$", re.IGNORECASE)
"""Names a manager would read as a local file (a formula `.rb`, a tarball, a wheel) rather than a package."""


@dataclass(frozen=True)
class Install:
    manager: str
    package: str

    @property
    def label(self) -> str:
        return MANAGERS[self.manager].label

    @property
    def program(self) -> str:
        """The package manager's program, looked up on PATH by the runner."""
        return MANAGERS[self.manager].command[0]

    @property
    def argv(self) -> list[str]:
        return [*MANAGERS[self.manager].command, self.package]

    def __str__(self) -> str:
        return " ".join(self.argv)


def install(manager: str, package: str) -> Install:
    """The install the worker asked for. Raises ValueError in words the worker can act on."""
    manager = manager.strip().lower().replace("-", "_")
    if manager not in MANAGERS:
        raise ValueError(f"manager must be one of {', '.join(MANAGERS)}, not {manager!r}")
    package = package.strip()
    spec = MANAGERS[manager]
    if not package or len(package) > MAX_NAME or not spec.name.fullmatch(package) or _FILE.search(package):
        raise ValueError(f"{package!r} isn't a package name {manager} installs. Give only the name, like "
                         f"{spec.example!r}: no URL, path, flag or second command.")
    return Install(manager, package)


KNOWN: dict[str, frozenset[tuple[str, str]]] = {
    "codex": frozenset({("npm", "@openai/codex"), ("brew_cask", "codex")}),
    "claude code": frozenset({("npm", "@anthropic-ai/claude-code")}),
    "github": frozenset({("brew", "gh")}),
    "gh": frozenset({("brew", "gh")}),
    "node": frozenset({("brew", "node")}),
    "nodejs": frozenset({("brew", "node")}),
    "node js": frozenset({("brew", "node")}),
    "python": frozenset({("brew", "python")}),
    "ffmpeg": frozenset({("brew", "ffmpeg")}),
    "git": frozenset({("brew", "git")}),
    "tree": frozenset({("brew", "tree")}),
    "jq": frozenset({("brew", "jq")}),
    "wget": frozenset({("brew", "wget")}),
    "ripgrep": frozenset({("brew", "ripgrep")}),
    "uv": frozenset({("brew", "uv")}),
}
"""Programs people ask for by a name that isn't their package's, each with the exact (manager, package) their own
install instructions give. "the codex cli" may become npm's `@openai/codex` or Homebrew's `codex` cask, nothing
else; "the github cli" is Homebrew's `gh`."""

_VERB = re.compile(r"^((re)?install(s|ed|ing)?|upgrade|installier\w*)$", re.IGNORECASE)
_FILLER = frozenset({"the", "a", "an", "me", "us", "please", "mir", "uns", "bitte", "mal", "den", "die", "das", "dem",
                     "der"})
_KIND = frozenset({"cli", "app", "tool", "ui", "command", "program", "package", "programm", "paket"})
"""Words after a program's name that say what kind of thing it is: "the codex cli", "the codex app"."""
_STOP = frozenset({"with", "using", "via", "from", "through", "and", "or", "for", "on", "to", "in", "too", "also",
                   "please", "mit", "über", "von", "und", "oder", "für", "auf", "bitte", "auch"})
_MANAGER_WORDS = {"brew": ("brew", "brew_cask"), "homebrew": ("brew", "brew_cask"), "cask": ("brew_cask",),
                  "npm": ("npm",), "uv": ("uv",), "pip": ("uv",), "pipx": ("uv",), "pypi": ("uv",)}
POINTS_OUTSIDE = re.compile(
    r"\b(page|web ?page|website|site|mail|e-?mail|message|file|document|readme|article|link|screen|post|tweet|"
    r"chat|seite|webseite|datei|dokument|nachricht|bildschirm|mentions?|mentioned|says|said|tells?|recommend\w*|"
    r"suggest\w*|listed|erwähn\w*|empfiehlt|empfohlen\w*|steht|sagt)\b", re.IGNORECASE)
"""A request that points at text someone else wrote ("install what this page mentions", "the one on the screen"):
the user didn't name the program, the text did."""


def pinned(wanted: Install) -> bool:
    """A version, tag or other source: `cowsay@1.5.0`, `black==24.10.0`, `python@3.12`, a Homebrew tap. A person
    asking for a program asks for the program, so these always ask."""
    name = wanted.package[1:] if wanted.package.startswith("@") else wanted.package
    if wanted.manager == "npm":
        return "@" in name
    return any(c in wanted.package for c in "@=[/")


def _objects(words: str) -> list[list[str]]:
    """What each install verb in `words` is about, as the words that follow it: "Can you install the Codex CLI for
    me?" -> [["codex", "cli"]]. Fillers ("the", "mir", "bitte") are skipped; the object ends at "with", "and" and
    the like."""
    tokens = [t.strip(".,;:!?\"'“”‘’()") for t in words.split()]
    tokens = [t.lower() for t in tokens if t]
    found = []
    for i, token in enumerate(tokens):
        if not _VERB.match(token):
            continue
        j = i + 1
        while j < len(tokens) and tokens[j] in _FILLER:
            j += 1
        thing = []
        while j < len(tokens) and tokens[j] not in _STOP and not _VERB.match(tokens[j]) and len(thing) < 4:
            thing.append(tokens[j])
            j += 1
        if thing:
            found.append(thing)
    return found


def named_by(wanted: Install, words: str) -> bool:
    """Whether the user's own words asked for this very install, so it needs no question in auto mode. Either the
    object of their install verb is a program `KNOWN` maps to exactly this (manager, package) ("install the codex
    cli" -> npm `@openai/codex`, never npm's unrelated `codex`), or, for a program the map doesn't know, it is the
    package's exact name ("install cowsay", "install @openai/codex": a scoped package only with its scope, so
    `@evil/codex` isn't "codex"). A manager they named must be the one used.
    Never for a version, tag, tap or other source (`pinned`), and never when the words point at text someone else
    wrote (`POINTS_OUTSIDE`)."""
    if not words or pinned(wanted) or POINTS_OUTSIDE.search(words):
        return False
    things = _objects(words)
    asked_for = {thing[0] for thing in things}  # "install uv" asks for uv the program, not for uv to install with
    said = {m for w in re.findall(r"[^\W_]+", words.lower()) if w not in asked_for for m in _MANAGER_WORDS.get(w, ())}
    if said and wanted.manager not in said:
        return False
    for thing in things:
        name = list(thing)
        while len(name) > 1 and name[-1] in _KIND:
            name.pop()
        known = KNOWN.get(" ".join(name))
        if known is not None:  # a known program is only what its own instructions name: npm's `codex` isn't Codex
            if (wanted.manager, wanted.package) in known:
                return True
        elif thing[0] == wanted.package.lower():
            return True
    return False
