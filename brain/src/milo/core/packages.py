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


def base_name(package: str) -> str:
    """The name a person would say: without an npm scope, a version, extras or a Homebrew `@version`.
    `@openai/codex@latest` -> `codex`, `black==24.10.0` -> `black`, `python@3.12` -> `python`."""
    name = package.split("/")[-1] if package.startswith("@") or "/" in package else package
    return re.split(r"[@=\[]", name, maxsplit=1)[0].lower()


def named_by(wanted: Install, words: str) -> bool:
    """Whether the user's own words name this package, so installing it needs no question in auto mode. Its base name
    must be there as words of their own ("install the codex cli" names `@openai/codex`; "install http server" names
    `http-server`), so a page the helper read can't swap in a package nobody named (`codex-helper` isn't `codex`).
    A Homebrew tap (`someone/tap/tool`) never counts: anyone can publish one, under any name."""
    if wanted.manager.startswith("brew") and "/" in wanted.package:
        return False
    parts = re.findall(r"[^\W_]+", base_name(wanted.package))
    said = re.findall(r"[^\W_]+", (words or "").lower())
    return bool(parts) and any(said[i:i + len(parts)] == parts for i in range(len(said) - len(parts) + 1))
