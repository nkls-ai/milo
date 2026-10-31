"""The part of a helper's prompt that names its tools: each with its arguments and what it does, plus the rules
that come with them, once.

Without it the worker spends its first model call listing tools, and Codex hands back every tool's description
with its server's instructions in front of each one (14k tokens for a calendar read on 2026-10-31). With the
names and arguments in the prompt it calls the tool straight away. The tool servers send no instructions of their
own any more: these are they, for the tools the helper has (core/task_scope.py).
"""

from __future__ import annotations

from collections.abc import Iterable

from milo.core import hands
from milo.core.task_scope import CONNECT_SERVER, ToolScope

from .memory_tools import INSTRUCTIONS as MEMORY_INSTRUCTIONS
from .memory_tools import MEMORY_TOOLS
from .milo_tools import INSTRUCTIONS as MILO_INSTRUCTIONS
from .milo_tools import MILO_TOOLS
from .tools import INSTRUCTIONS, TOOLS

OWN = "milo"
"""The connection of Milo's own tools (reminders he says, undo): every helper has them."""
HEAD = "Your tools for this task. Call them directly by these names; you don't need to list or search for them."
MAX_SAID = 140


def served(kinds: frozenset[str] | None, available: frozenset[str] | None = None) -> frozenset[str] | None:
    """The connections a helper gets: those of its scope that are switched on. None: all there are."""
    if kinds is None:
        return available
    return kinds if available is None else kinds & available


def brief(scope: ToolScope, *, available: frozenset[str] | None = None) -> str:
    """The tools section of a helper's first prompt. `available`: the connections switched on (None: all)."""
    kinds = served(scope.kinds, available)

    def has(connection: str) -> bool:
        return connection == OWN or kinds is None or connection in kinds

    parts = [HEAD]
    if scope.screen:
        parts += [_lines(hands.SERVER_NAME, ((t.name, t.properties, t.required, t.description) for t in hands.TOOLS)),
                  hands.INSTRUCTIONS]
    tools = [t for t in (*TOOLS, *MEMORY_TOOLS, *MILO_TOOLS) if has(t.connection)]
    parts.append(_lines(CONNECT_SERVER, ((t.name, t.properties, t.required, t.description) for t in tools)))
    if any(t.connection not in (OWN, "memory") for t in tools):
        parts.append(INSTRUCTIONS.strip())
    if any(t.connection == "memory" for t in tools):
        parts.append(MEMORY_INSTRUCTIONS.strip())
    parts.append(MILO_INSTRUCTIONS.strip())
    return "\n\n".join(parts)


def _lines(server: str, tools: Iterable[tuple[str, dict, tuple[str, ...], str]]) -> str:
    prefix = f"mcp__{server.replace('-', '_')}__"
    return "\n".join(f"- {prefix}{name}({_args(properties, required)}): {_first(description)}"
                     for name, properties, required, description in tools)


def _args(properties: dict, required: tuple[str, ...]) -> str:
    return ", ".join(name if name in required else f"{name}?" for name in properties)


def _first(description: str) -> str:
    """The description's first sentence, which says what the tool does."""
    first = description.split(". ", 1)[0].rstrip(".") + "."
    return first if len(first) <= MAX_SAID else first[:MAX_SAID - 1].rstrip() + "…"
