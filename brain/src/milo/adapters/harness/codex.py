"""Codex CLI adapter: one `codex exec` (or `codex exec resume`) process per turn."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.ports import StepCallback
from milo.core.registry import HARNESSES, AdapterContext, options_from
from milo.core.types import REPLY_SCHEMA, HarnessError, Reply, ToolServer, Usage

from ._activity import CodexActivity
from ._binary import find_binary
from ._process import last_line, run

# Long enough for a question to the user (approvals time out at 60 s by default).
TOOL_TIMEOUT_S = 240
# Where the ChatGPT desktop app ships its own codex.
BUNDLED_CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")


@dataclass(frozen=True)
class CodexOptions:
    binary: str = ""
    model: str = ""
    reasoning_effort: str = "low"
    sandbox: str = "workspace-write"
    timeout_s: float = 180


class CodexHarness:
    name = "codex"

    def __init__(self, binary: str, workdir: Path, schema_path: Path, *, model: str = "",
                 reasoning_effort: str = "low", sandbox: str = "workspace-write", timeout_s: float = 180,
                 tool_servers: tuple[ToolServer, ...] = ()):
        self.binary = binary
        self.tool_servers = tool_servers
        self.workdir = workdir
        self.schema_path = schema_path
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.sandbox = sandbox
        self.timeout_s = timeout_s
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(json.dumps(REPLY_SCHEMA))

    def command(self, prompt: str, session_id: str | None) -> list[str]:
        cmd = [self.binary, "exec"]
        if session_id:
            cmd += ["resume", session_id]
        cmd += [
            "--json",
            "--skip-git-repo-check",
            "--output-schema", str(self.schema_path),
            # `exec resume` has no --sandbox flag, so set it through config on both paths.
            "-c", f'sandbox_mode="{self.sandbox}"',
            "-c", f'model_reasoning_effort="{self.reasoning_effort}"',
        ]
        if self.model:
            cmd += ["-m", self.model]
        for server in self.tool_servers:
            cmd += mcp_overrides(server)
        return cmd + ["--", prompt]

    async def reply(self, prompt: str, session_id: str | None, *, on_step: StepCallback | None = None) -> Reply:
        on_line = CodexActivity(on_step, self.workdir).line if on_step is not None else None
        code, out, err = await run(self.command(prompt, session_id), cwd=self.workdir, timeout_s=self.timeout_s,
                                   on_line=on_line)
        thread_id, text, usage, error = parse_events(out.splitlines())
        if error or code != 0 or text is None:
            raise HarnessError(f"codex failed: {error or last_line(err, code)}", transient=True)
        return Reply.from_model_text(text, usage, thread_id or session_id)


def mcp_overrides(server: ToolServer) -> list[str]:
    """`-c` overrides that add one MCP server. Milo's tools ask the user themselves, so codex auto-approves them."""
    key = f"mcp_servers.{server.name}"
    env = ", ".join(f"{k} = {json.dumps(v)}" for k, v in server.env)
    return ["-c", f"{key}.command={json.dumps(server.command[0])}",
            "-c", f"{key}.args={json.dumps(list(server.command[1:]))}",
            "-c", f"{key}.env={{{env}}}",
            "-c", f'{key}.default_tools_approval_mode="approve"',
            "-c", f"{key}.tool_timeout_sec={TOOL_TIMEOUT_S}"]


def parse_events(lines: Iterable[str]) -> tuple[str | None, str | None, Usage, str | None]:
    """Read `codex exec --json` JSONL into (thread_id, last agent message, usage, error)."""
    thread_id = text = error = None
    usage = Usage()
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "thread.started":
            thread_id = event.get("thread_id")
        elif kind == "item.completed" and event.get("item", {}).get("type") == "agent_message":
            text = event["item"].get("text", "")
        elif kind == "turn.completed":
            u = event.get("usage", {})
            usage = Usage(u.get("input_tokens", 0), u.get("cached_input_tokens", 0), u.get("output_tokens", 0))
        elif kind in ("turn.failed", "error"):
            error = str(event.get("error", {}).get("message") if isinstance(event.get("error"), dict)
                        else event.get("message") or event.get("error") or kind)
    return thread_id, text, usage, error


@HARNESSES.register("codex")
def _codex(options: Mapping[str, Any], ctx: AdapterContext) -> CodexHarness:
    o = options_from(CodexOptions, options, "harness.codex")
    return CodexHarness(
        find_binary(o.binary, "codex", (BUNDLED_CODEX,), section="harness.codex"),
        ctx.home,
        ctx.state_dir / "reply-schema.json",
        model=o.model,
        reasoning_effort=o.reasoning_effort,
        sandbox=o.sandbox,
        timeout_s=o.timeout_s,
        tool_servers=ctx.tool_servers,
    )
