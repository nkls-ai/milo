"""Find a harness CLI. The app is launched from Finder, so PATH is often missing the usual dirs."""

from __future__ import annotations

import shutil
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from milo.core.registry import ConfigError
from milo.core.types import HarnessError

NPM_PACKAGES = {"codex": "@openai/codex", "claude": "@anthropic-ai/claude-code"}


def _native(path: str) -> str:
    if sys.platform == "win32" and Path(path).suffix.casefold() in ("", ".cmd", ".bat", ".ps1", ".exe"):
        executable = Path(path).with_suffix(".exe")
        if executable.is_file():
            return str(executable)
    return path


def _node() -> str:
    found = shutil.which("node.exe" if sys.platform == "win32" else "node")
    if not found:
        raise HarnessError("This JavaScript CLI needs Node.js. Install Node.js or configure a native CLI executable.",
                           transient=False)
    return found


def executable_command(binary: str, arguments: Sequence[str] = ()) -> list[str]:
    """A real executable plus literal arguments; never send model text to a shell.

    npm's Windows .cmd wrappers cannot safely receive arbitrary prompts through
    cmd.exe. Resolve known packages' declared entry points and invoke Node directly.
    Python drivers are supported explicitly, which also makes CLI tests portable.
    """
    found = shutil.which(binary) if not Path(binary).is_file() else binary
    path = Path(_native(found or binary)).expanduser()
    suffix = path.suffix.casefold()
    if suffix in (".py", ".pyw"):
        python = sys.executable if not getattr(sys, "frozen", False) else shutil.which("python")
        if not python:
            raise HarnessError("A Python CLI script needs an installed Python interpreter.", transient=False)
        return [python, "-u", str(path), *arguments]
    if suffix in (".js", ".mjs", ".cjs"):
        return [_node(), str(path), *arguments]
    if sys.platform == "win32" and suffix in (".cmd", ".bat", ".ps1"):
        package_name = NPM_PACKAGES.get(path.stem.casefold())
        if package_name:
            package = path.parent / "node_modules" / package_name
            try:
                manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
                entry = manifest.get("bin")
                entry = entry.get(path.stem.casefold()) if isinstance(entry, dict) else entry
                if manifest.get("name") != package_name or not isinstance(entry, str):
                    raise ValueError("unsupported package entry")
                target = (package / entry).resolve()
                if not target.is_relative_to(package.resolve()) or not target.is_file():
                    raise ValueError("package entry is outside its installation")
                if target.suffix.casefold() == ".exe":
                    return [str(target), *arguments]
                if target.suffix.casefold() not in (".js", ".mjs", ".cjs"):
                    raise ValueError("unsupported package entry")
                adjacent_node = path.parent / "node.exe"
                return [str(adjacent_node) if adjacent_node.is_file() else _node(), str(target), *arguments]
            except (OSError, ValueError, TypeError):
                pass
        raise HarnessError(f"Cannot safely launch the Windows shell wrapper {path.name}. "
                           "Configure the CLI's native executable or JavaScript entry point instead.", transient=False)
    return [str(path), *arguments]


def find_binary(configured: str, name: str, fallbacks: Sequence[Path] = (), *, section: str) -> str:
    """Configured path, then PATH, then ~/.local/bin and /opt/homebrew/bin, then `fallbacks`."""
    if configured:
        return _native(str(Path(configured).expanduser()))
    found = (shutil.which(name + ".exe") if sys.platform == "win32" else None) or shutil.which(name)
    if found:
        return _native(found)
    local = Path.home() / ".local/bin" / name
    windows = [local.with_suffix(".exe"), local.with_suffix(".cmd")]
    if os.environ.get("APPDATA"):
        windows += [Path(os.environ["APPDATA"]) / "npm" / (name + suffix) for suffix in (".exe", ".cmd")]
    if sys.platform == "win32" and name == "codex":
        local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        try:
            windows += sorted((local_app / "OpenAI/Codex/bin").glob("*/codex.exe"),
                              key=lambda item: item.stat().st_mtime, reverse=True)[:20]
        except OSError:
            pass
    if sys.platform == "win32" and name == "claude":
        # WinGet's user links are commonly missing from a GUI process's
        # inherited PATH, even though Claude Code is installed and authenticated.
        # These are Claude Code's CLI locations, never Claude Desktop's GUI exe.
        local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        winget = local_app / "Microsoft/WinGet"
        windows.append(winget / "Links/claude.exe")
        try:
            windows += sorted((winget / "Packages").glob("Anthropic.ClaudeCode_*/claude.exe"),
                              key=lambda item: item.stat().st_mtime, reverse=True)[:20]
        except OSError:
            pass
        windows.append(Path.home() / ".claude/local/claude.exe")
    for path in (*(windows if sys.platform == "win32" else ()), local, Path("/opt/homebrew/bin") / name, *fallbacks):
        if path.is_file():
            return str(path)
    raise ConfigError(f"could not find `{name}`; set `binary` in [{section}]")
