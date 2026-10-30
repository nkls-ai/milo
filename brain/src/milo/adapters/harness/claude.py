"""Claude Code adapter: one `claude -p` process per turn, read as stream-json so tool use shows while it works."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.ports import StepCallback
from milo.core.registry import HARNESSES, AdapterContext, options_from
from milo.core.types import REPLY_SCHEMA, HarnessError, Reply, ToolServer, Usage

from ._activity import ClaudeActivity
from ._binary import find_binary
from ._process import last_line, run


@dataclass(frozen=True)
class ClaudeOptions:
    binary: str = ""
    model: str = ""
    permission_mode: str = "acceptEdits"
    timeout_s: float = 180
    disallowed_tools: tuple[str, ...] = ()
    """Built-in tools the agent may not use, e.g. ["Bash", "WebFetch"]."""


class ClaudeHarness:
    name = "claude"

    def __init__(self, binary: str, workdir: Path, *, model: str = "", permission_mode: str = "acceptEdits",
                 timeout_s: float = 180, tool_servers: tuple[ToolServer, ...] = (), mcp_config: Path | None = None,
                 disallowed_tools: tuple[str, ...] = ()):
        self.binary = binary
        self.workdir = workdir
        self.model = model
        self.permission_mode = permission_mode
        self.timeout_s = timeout_s
        self.tool_servers = tool_servers
        self.mcp_config = mcp_config
        self.disallowed_tools = disallowed_tools
        if tool_servers and mcp_config is not None:
            mcp_config.parent.mkdir(parents=True, exist_ok=True)
            mcp_config.write_text(json.dumps(mcp_servers(tool_servers)))

    def command(self, prompt: str, session_id: str | None) -> list[str]:
        cmd = [self.binary, "-p", "--output-format", "stream-json", "--verbose",
               "--json-schema", json.dumps(REPLY_SCHEMA), "--permission-mode", self.permission_mode]
        if session_id:
            cmd += ["--resume", session_id]
        if self.model:
            cmd += ["--model", self.model]
        if self.tool_servers and self.mcp_config is not None:
            # Milo's tools ask the user themselves when it matters, so -p mode may call them without a prompt.
            cmd += ["--mcp-config", str(self.mcp_config),
                    "--allowedTools", *(f"mcp__{s.name}" for s in self.tool_servers)]
        if self.disallowed_tools:
            cmd += ["--disallowedTools", *self.disallowed_tools]
        return cmd + ["--", prompt]

    async def reply(self, prompt: str, session_id: str | None, *, on_step: StepCallback | None = None) -> Reply:
        on_line = ClaudeActivity(on_step, self.workdir).line if on_step is not None else None
        code, out, err = await run(self.command(prompt, session_id), cwd=self.workdir, timeout_s=self.timeout_s,
                                   on_line=on_line)
        return parse_result(result_line(out), code, err, session_id)


def mcp_servers(servers: tuple[ToolServer, ...]) -> dict:
    """The --mcp-config file for Claude Code."""
    return {"mcpServers": {s.name: {"type": "stdio", "command": s.command[0], "args": list(s.command[1:]),
                                    "env": dict(s.env)} for s in servers}}


def result_line(out: str) -> str:
    """The last `{"type":"result",...}` line of stream-json output; all of `out` if there is none."""
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{") and '"result"' in line:
            try:
                if json.loads(line).get("type") == "result":
                    return line
            except (json.JSONDecodeError, AttributeError):
                continue
    return out


def parse_result(out: str, code: int, err: str, session_id: str | None) -> Reply:
    """Read the result object of `claude -p`. The answer is in `structured_output`, else in `result`."""
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise HarnessError(f"claude failed: {last_line(err, code)}", transient=True) from None
    if not isinstance(data, dict):
        raise HarnessError(f"claude failed: unexpected output {out[:80]!r}", transient=True)
    if data.get("is_error"):
        raise HarnessError(f"claude failed: {data.get('result') or data.get('subtype')}", transient=True)
    u = data.get("usage", {})
    usage = Usage(
        input_tokens=u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        + u.get("cache_creation_input_tokens", 0),
        cached_input_tokens=u.get("cache_read_input_tokens", 0),
        output_tokens=u.get("output_tokens", 0),
    )
    structured = data.get("structured_output")
    text = json.dumps(structured) if isinstance(structured, dict) else str(data.get("result", ""))
    return Reply.from_model_text(text, usage, data.get("session_id") or session_id)


@HARNESSES.register("claude")
def _claude(options: Mapping[str, Any], ctx: AdapterContext) -> ClaudeHarness:
    o = options_from(ClaudeOptions, options, "harness.claude")
    return ClaudeHarness(
        find_binary(o.binary, "claude", section="harness.claude"),
        ctx.home,
        model=o.model,
        permission_mode=o.permission_mode,
        timeout_s=o.timeout_s,
        tool_servers=ctx.tool_servers,
        mcp_config=ctx.state_dir / "mcp-servers.json",
        disallowed_tools=o.disallowed_tools,
    )
