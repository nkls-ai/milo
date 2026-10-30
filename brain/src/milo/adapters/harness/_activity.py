"""What the worker agent is doing, in plain words, read from the CLIs' streamed JSON events.

Each step gets a title anyone can read ("Reading your Downloads folder") and keeps the raw command or
tool payload as its detail. Codex (`exec --json`) announces items with item.started/item.completed;
Claude Code (`-p --output-format stream-json --verbose`) sends tool_use blocks in assistant messages and
the matching tool_result blocks in user messages.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from milo.core.hands import SERVER_NAME
from milo.core.ports import StepCallback
from milo.core.types import Step, StepStatus

MAX_TITLE = 64
MAX_DETAIL = 2000
MAX_OUTPUT = 400  # of a failed step's output, appended to its detail

_HOME_FOLDERS = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Movies", "Public")
_SHELLS = ("sh", "bash", "zsh")
_SEGMENT = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
_TELL_APP = re.compile(r'tell application "([^"]+)"')
_READERS = ("cat", "head", "tail", "less", "more", "bat", "nl", "wc", "file", "stat", "xxd", "strings")
_RUNNERS = ("python", "python3", "node", "uv", "ruby", "perl", "swift", "bun", "deno", "npx")
_SKIPPED_CLAUDE_TOOLS = ("TodoWrite", "ToolSearch", "EnterPlanMode", "ExitPlanMode")
# Tools Milo's own Mac MCP server will offer (Phase 2), so computer use reads well from day one.
_KNOWN_TOOLS = {
    "screenshot": "Looking at the screen",
    "click": "Clicking",
    "type": "Typing",
    "type_text": "Typing",
    "ax_press": "Pressing a button",
    "ax_set_value": "Filling in a field",
    "ax_tree": "Looking at the window",
    "list_apps": "Checking which apps are open",
    "run_applescript": "Controlling an app",
}


def describe_command(command: str, workdir: Path) -> tuple[str, str]:
    """(kind, title) for a shell command. Falls back to "Running a command"."""
    inner = _unwrap_shell(command)
    cwd = workdir
    for segment in _SEGMENT.split(inner):
        argv = _split(segment)
        if argv and argv[0] == "cd" and len(argv) > 1:
            cwd = Path(_normalize(cwd / Path(argv[1]).expanduser()))
            continue
        if not argv or Path(argv[0]).name in ("cd", "export", "set", "true"):
            continue
        return _describe_argv(segment, argv, cwd, workdir)
    return "command", "Running a command"


def describe_read(path: str) -> tuple[str, str]:
    return "read", f"Reading {_name(path)}"


def describe_edit(path: str, change: str = "update") -> tuple[str, str]:
    verb = {"add": "Creating", "delete": "Deleting"}.get(change, "Editing")
    return "edit", f"{verb} {_name(path)}"


def describe_web_search(query: str) -> tuple[str, str]:
    return "web", f"Searching the web for “{_clip(query, 40)}”" if query else "Searching the web"


def describe_fetch(url: str) -> tuple[str, str]:
    host = urlparse(url).hostname or ""
    return "web", f"Reading {host.removeprefix('www.')}" if host else "Reading a web page"


def describe_tool(tool: str) -> tuple[str, str]:
    """An MCP or other named tool. Known tools get a sentence, others their name made readable."""
    if tool in _KNOWN_TOOLS:
        return "tool", _KNOWN_TOOLS[tool]
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tool).replace("_", " ").replace("-", " ").strip()
    return "tool", (words[:1].upper() + words[1:].lower()) or "Using a tool"


def _describe_argv(segment: str, argv: list[str], cwd: Path, workdir: Path) -> tuple[str, str]:
    prog = Path(argv[0]).name
    args = [a for a in argv[1:] if not a.startswith("-")]
    first = args[0] if args else ""
    redirect = re.search(r"(?<![0-9&])>>?\s*(\S+)", segment)
    if redirect and not redirect.group(1).startswith("/dev/"):
        return "edit", f"Writing {_name(redirect.group(1).strip(chr(34) + chr(39)))}"
    if prog == "open":
        if "-a" in argv[1:-1]:
            return "app", f"Opening {_clip(argv[argv.index('-a') + 1], 40)}"
        if first.startswith(("http://", "https://")):
            return "web", f"Opening {urlparse(first).hostname or 'a web page'}"
        return "app", f"Opening {_name(first)}" if first else "Opening an app"
    if prog == "osascript":
        app = _TELL_APP.search(segment)
        return "app", f"Working in {app.group(1)}" if app else "Controlling an app"
    if prog in ("ls", "tree", "du"):
        return "read", f"Looking in {_folder(first or '.', cwd, workdir)}"
    if prog in _READERS or (prog == "sed" and "-i" not in argv):
        target = args[-1] if prog == "sed" and len(args) > 1 else first
        return "read", f"Reading {_name(target)}" if target else "Reading a file"
    if prog == "sed":
        return "edit", f"Editing {_name(args[-1])}" if args else "Editing a file"
    if prog in ("rg", "grep", "ag", "ack"):
        return "search", f"Searching your files for “{_clip(first, 30)}”" if first else "Searching your files"
    if prog in ("find", "fd", "mdfind", "locate"):
        where = f" in {_folder(first, cwd, workdir)}" if prog == "find" and first else ""
        return "search", f"Looking for files{where}"
    if prog == "mkdir":
        return "edit", f"Making the {_name(first)} folder" if first else "Making a folder"
    if prog in ("mv", "cp", "rm", "trash", "touch", "unzip", "zip", "tar"):
        verb = {"mv": "Moving", "cp": "Copying", "rm": "Deleting", "trash": "Deleting", "touch": "Creating",
                "unzip": "Unpacking", "zip": "Packing", "tar": "Packing"}[prog]
        return "edit", f"{verb} {_name(first)}" if first else f"{verb} files"
    if prog in ("curl", "wget"):
        url = next((a for a in args if "://" in a), first)
        host = urlparse(url).hostname if "://" in url else url
        return "web", f"Downloading from {host.removeprefix('www.')}" if host else "Downloading a file"
    if prog in _RUNNERS:
        return "command", "Running a small program"
    if prog in ("date", "cal"):
        return "command", "Checking the date"
    return "command", "Running a command"


def _unwrap_shell(command: str) -> str:
    """`/bin/zsh -lc "ls ~/Downloads"` -> `ls ~/Downloads`. Codex wraps every command like this."""
    argv = _split(command)
    if len(argv) >= 3 and Path(argv[0]).name in _SHELLS and argv[1] in ("-c", "-lc", "-ic"):
        return argv[2]
    return command


def _split(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _name(path: str) -> str:
    return _clip(Path(path.rstrip("/")).name or path, 40)


def _folder(path: str, cwd: Path, workdir: Path) -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = cwd / p
    p = Path(_normalize(p))
    home = Path.home()
    if p == Path(_normalize(workdir)):
        return "Milo's folder"
    if p == home:
        return "your home folder"
    if p.parent == home and p.name in _HOME_FOLDERS:
        return f"your {p.name} folder"
    return f"the {_clip(p.name, 40)} folder"


def _normalize(p: Path) -> str:
    parts: list[str] = []
    for part in p.parts:
        if part == "..":
            if len(parts) > 1:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return str(Path(*parts)) if parts else str(p)


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _step(id: str, kind: str, title: str, detail: str, status: StepStatus) -> Step:
    return Step(id, kind, _clip(title, MAX_TITLE), detail[:MAX_DETAIL], status)


def _tail(output: Any) -> str:
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    text = text.strip()
    return text if len(text) <= MAX_OUTPUT else "…" + text[-MAX_OUTPUT:]


# ---- codex


class CodexActivity:
    """Feed it `codex exec --json` lines; it calls on_step for every command, file change, tool call and search."""

    def __init__(self, on_step: StepCallback, workdir: Path):
        self._on_step = on_step
        self._workdir = workdir

    def line(self, line: str) -> None:
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        if event.get("type") not in ("item.started", "item.updated", "item.completed"):
            return
        item = event.get("item")
        if isinstance(item, dict):
            step = codex_step(item, event["type"] == "item.completed", self._workdir)
            if step is not None:
                self._on_step(step)


def codex_step(item: dict, completed: bool, workdir: Path) -> Step | None:
    """One codex item as a step, or None for items that aren't actions (messages, reasoning, todo lists)."""
    kind = item.get("type")
    status = _codex_status(item.get("status"), completed)
    sid = str(item.get("id", ""))
    if kind == "command_execution":
        command = str(item.get("command", ""))
        exit_code = item.get("exit_code")
        if completed and isinstance(exit_code, int) and exit_code != 0:
            status = StepStatus.FAILED
        detail = _unwrap_shell(command)
        if status is StepStatus.FAILED and item.get("aggregated_output"):
            detail += "\n\n" + _tail(item["aggregated_output"])
        return _step(sid, *describe_command(command, workdir), detail, status)
    if kind == "file_change":
        changes = [c for c in item.get("changes") or [] if isinstance(c, dict)]
        detail = "\n".join(f"{c.get('kind', 'update')} {c.get('path', '')}" for c in changes)
        if len(changes) == 1:
            what = describe_edit(str(changes[0].get("path", "")), str(changes[0].get("kind", "update")))
        else:
            what = ("edit", f"Changing {len(changes)} files")
        return _step(sid, *what, detail, status)
    if kind == "mcp_tool_call":
        if item.get("server") == SERVER_NAME:
            return None  # the brain logs Mac actions itself, with what they touched
        tool = str(item.get("tool", ""))
        detail = f"{item.get('server', '')}.{tool} {json.dumps(item.get('arguments'), ensure_ascii=False)}"
        if item.get("error"):
            status = StepStatus.FAILED
            detail += "\n\n" + _tail(item["error"])
        return _step(sid, *describe_tool(tool), detail, status)
    if kind == "web_search":
        action = item.get("action") if isinstance(item.get("action"), dict) else {}
        query = str(item.get("query") or action.get("query") or "")
        return _step(sid, *describe_web_search(query), query, status)
    return None


def _codex_status(status: object, completed: bool) -> StepStatus:
    if status in ("failed", "declined"):
        return StepStatus.FAILED
    if status == "in_progress" or not completed:
        return StepStatus.RUNNING
    return StepStatus.DONE


# ---- claude


class ClaudeActivity:
    """Feed it `claude -p --output-format stream-json --verbose` lines; it calls on_step per tool use and result."""

    def __init__(self, on_step: StepCallback, workdir: Path):
        self._on_step = on_step
        self._workdir = workdir
        self._running: dict[str, Step] = {}

    def line(self, line: str) -> None:
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        kind = event.get("type")
        if kind not in ("assistant", "user"):
            return
        content = (event.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if kind == "assistant" and block.get("type") == "tool_use":
                step = claude_step(str(block.get("id", "")), str(block.get("name", "")), block.get("input") or {},
                                   self._workdir)
                if step is not None:
                    self._running[step.id] = step
                    self._on_step(step)
            elif kind == "user" and block.get("type") == "tool_result":
                step = self._running.pop(str(block.get("tool_use_id", "")), None)
                if step is None:
                    continue
                failed = bool(block.get("is_error"))
                detail = step.detail
                if failed:
                    detail += "\n\n" + _tail(_result_text(block.get("content")))
                self._on_step(_step(step.id, step.kind, step.title, detail,
                                    StepStatus.FAILED if failed else StepStatus.DONE))


def claude_step(id: str, name: str, args: dict, workdir: Path) -> Step | None:
    """A Claude Code tool_use block as a running step, or None for bookkeeping tools like TodoWrite."""
    if name in _SKIPPED_CLAUDE_TOOLS or not isinstance(args, dict) or name.startswith(f"mcp__{SERVER_NAME}__"):
        return None
    path = str(args.get("file_path") or args.get("notebook_path") or "")
    if name == "Bash":
        command = str(args.get("command", ""))
        kind, title = describe_command(command, workdir)
        if title == "Running a command" and args.get("description"):
            title = str(args["description"])
        detail = command
    elif name == "Read":
        (kind, title), detail = describe_read(path), path
    elif name in ("Edit", "MultiEdit", "NotebookEdit"):
        (kind, title), detail = describe_edit(path), path
    elif name == "Write":
        kind, title, detail = "edit", f"Writing {_name(path)}", path
    elif name == "Glob":
        where = f" in {_folder(str(args['path']), workdir, workdir)}" if args.get("path") else ""
        kind, title, detail = "search", f"Looking for files{where}", str(args.get("pattern", ""))
    elif name == "Grep":
        pattern = str(args.get("pattern", ""))
        kind, title, detail = "search", f"Searching your files for “{_clip(pattern, 30)}”", pattern
    elif name == "WebSearch":
        query = str(args.get("query", ""))
        (kind, title), detail = describe_web_search(query), query
    elif name == "WebFetch":
        url = str(args.get("url", ""))
        (kind, title), detail = describe_fetch(url), url
    elif name in ("Task", "Agent"):
        what = str(args.get("description", ""))
        kind, title = "other", f"Asking a helper: {what}" if what else "Asking a helper"
        detail = str(args.get("prompt", what))
    else:
        tool = name.split("__")[-1] if name.startswith("mcp__") else name
        (kind, title), detail = describe_tool(tool), f"{name} {json.dumps(args, ensure_ascii=False)}"
    return _step(id, kind, title, detail, StepStatus.RUNNING)


def _result_text(content: object) -> str:
    if isinstance(content, list):
        return "\n".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return str(content or "")
