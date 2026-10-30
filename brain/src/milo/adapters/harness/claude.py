"""Claude Code adapter: one `claude -p` process per turn, read as stream-json so tool use shows while it works."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.hands import SERVER_NAME
from milo.core.ports import StepCallback
from milo.core.registry import HARNESSES, AdapterContext, options_from
from milo.core.types import REPLY_SCHEMA, HarnessError, Reply, Usage

from ._activity import ClaudeActivity
from ._binary import find_binary
from ._process import last_line, run


@dataclass(frozen=True)
class ClaudeOptions:
    binary: str = ""
    model: str = ""
    permission_mode: str = "acceptEdits"
    timeout_s: float = 180


class ClaudeHarness:
    name = "claude"

    def __init__(self, binary: str, workdir: Path, *, model: str = "", permission_mode: str = "acceptEdits",
                 timeout_s: float = 180, mac_tools: Sequence[str] = ()):
        self.binary = binary
        self.workdir = workdir
        self.model = model
        self.permission_mode = permission_mode
        self.timeout_s = timeout_s
        self.mac_tools = tuple(mac_tools)

    def command(self, prompt: str, session_id: str | None) -> list[str]:
        cmd = [self.binary, "-p", "--output-format", "stream-json", "--verbose",
               "--json-schema", json.dumps(REPLY_SCHEMA), "--permission-mode", self.permission_mode]
        if session_id:
            cmd += ["--resume", session_id]
        if self.model:
            cmd += ["--model", self.model]
        if self.mac_tools:
            server = {"type": "stdio", "command": self.mac_tools[0], "args": list(self.mac_tools[1:])}
            # -p can't ask for permission, so the Mac tools are allowed up front; the brain gates each call.
            cmd += ["--mcp-config", json.dumps({"mcpServers": {SERVER_NAME: server}}),
                    "--allowedTools", f"mcp__{SERVER_NAME}"]
        return cmd + ["--", prompt]

    async def reply(self, prompt: str, session_id: str | None, *, on_step: StepCallback | None = None) -> Reply:
        on_line = ClaudeActivity(on_step, self.workdir).line if on_step is not None else None
        code, out, err = await run(self.command(prompt, session_id), cwd=self.workdir, timeout_s=self.timeout_s,
                                   on_line=on_line)
        return parse_result(result_line(out), code, err, session_id)


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
        mac_tools=ctx.mac_tools,
    )
