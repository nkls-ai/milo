"""Claude Code adapter: one `claude -p` process per turn, read as stream-json so tool use shows while it works.

The worker gets Milo's tools and instructions only: no user settings (so none of the user's plugins, hooks or
permission rules), no skills or slash commands, no auto-memory, only the MCP servers Milo passes and a fixed set
of built-in tools. It runs in the workspace's work/ folder with --restricted, so its file tools stay there, deny
rules keep them off Milo's control files, and Bash runs in Claude Code's sandbox, which writes only there
(ADR 0020). Its instructions are the workspace's CLAUDE.md, one folder up, which Claude Code finds there and
which imports AGENTS.md.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.control import STEERING, STEERING_FOLDERS, Protected, clear_steering
from milo.core.hands import mac_server
from milo.core.ports import PlanCallback, SessionCallback, StepCallback
from milo.core.registry import HARNESSES, AdapterContext, options_from
from milo.core.task_scope import ToolScope, server_env
from milo.core.types import REPLY_SCHEMA, HarnessError, Reply, ToolServer, Usage

from ._activity import ClaudeActivity, RunWatch, lines
from ._binary import find_binary
from ._process import last_line, run


# Built-in tools the worker may use: files in its own folder, a shell and the web. No sub-agents, workflows,
# schedules or worktrees.
BUILTIN_TOOLS = ("Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch")



def settings(deny: Sequence[str], no_writes: Sequence[str] = (), no_reads: Sequence[str] = ()) -> str:
    """The worker's only settings (--restricted ignores every settings file): no auto-memory; `deny`, the rules
    that keep its file tools off Milo's control files; and Bash in Claude Code's sandbox, which may write only
    the worker's folder and the temp folder, never `no_writes`, can't read `no_reads` (the keys), and runs
    nothing outside it (ADR 0020). No
    sandbox on this Mac means no task: --restricted keeps Bash, so it must not run unsandboxed."""
    return json.dumps({"autoMemoryEnabled": False, "permissions": {"deny": list(deny)},
                       "sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                                   "autoAllowBashIfSandboxed": True,
                                   "filesystem": {"denyWrite": list(no_writes), "denyRead": list(no_reads)}}})


@dataclass(frozen=True)
class ClaudeOptions:
    binary: str = ""
    model: str = ""
    light_model: str = ""
    """For helpers off the screen whose task names its connections (ToolScope.simple), e.g. "claude-haiku-5-5".
    "": `model` does those too. Not measured yet with Claude (ADR 0032)."""
    permission_mode: str = "acceptEdits"
    timeout_s: float = 180
    disallowed_tools: tuple[str, ...] = ()
    """Built-in tools the agent may not use, e.g. ["Bash", "WebFetch"]."""
    restricted: bool = True
    """`--restricted` (Claude Code 2.1.3xx): the file tools stay in the worker's folder, no settings file counts,
    and the worker can't approve writes to settings itself. False only for an older CLI without it."""


class ClaudeHarness:
    name = "claude"

    def __init__(self, binary: str, workdir: Path, *, model: str = "", light_model: str = "",
                 permission_mode: str = "acceptEdits",
                 timeout_s: float = 180, mac_tools: Sequence[str] = (), tool_servers: tuple[ToolServer, ...] = (),
                 mcp_config: Path | None = None, disallowed_tools: tuple[str, ...] = (),
                 protected: Protected | None = None, restricted: bool = True):
        """`mac_tools` starts the milo-mac server, `tool_servers` are Milo's app connections. Both go into
        `mcp_config` if given, else inline on the command line."""
        self.binary = binary
        self.workdir = workdir
        self.model = model
        self.light_model = light_model
        self.permission_mode = permission_mode
        self.timeout_s = timeout_s
        self.mac_tools = tuple(mac_tools)
        self.tool_servers = tool_servers
        self.mcp_config = mcp_config
        self.disallowed_tools = disallowed_tools
        # And what in its own folder would steer the next task (instructions, settings, MCP servers). They are
        # removed before each run too, which also covers Codex.
        own = [f"/{workdir.resolve().as_posix()}/{deep}{name}" + ("/**" if name in STEERING_FOLDERS else "")
               for name in STEERING for deep in ("", "**/")]
        self.deny = [*(protected.deny_rules() if protected is not None else []),
                     *(f"{tool}({path})" for path in own for tool in ("Edit", "Write"))]
        self.no_writes = [*(protected.resolved() if protected is not None else []),
                          *(str(workdir.resolve() / deep / name) for name in STEERING for deep in ("", "**"))]
        self.no_reads = [str((protected.home / "secrets").resolve())] if protected is not None else []
        self.restricted = restricted
        self.servers = (*mac_server(self.mac_tools), *tool_servers)

    def _config(self, servers: tuple[ToolServer, ...], scope: ToolScope | None) -> str:
        """The --mcp-config value: a file per scope (helpers of different scopes may start at once), else JSON."""
        if self.mcp_config is None:
            return json.dumps(mcp_servers(servers))
        key = server_env(scope)[0][1].replace(",", "-") if scope is not None and server_env(scope) else ""
        path = self.mcp_config.with_name(f"{self.mcp_config.stem}-{key}.json") if key else self.mcp_config
        text = json.dumps(mcp_servers(servers))
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            staged = path.with_name(path.name + ".milo")
            staged.write_text(text, encoding="utf-8")
            staged.replace(path)
        return str(path)

    def command(self, prompt: str, session_id: str | None, scope: ToolScope | None = None) -> list[str]:
        cmd = [self.binary, "-p", "--output-format", "stream-json", "--verbose",
               "--json-schema", json.dumps(REPLY_SCHEMA), "--permission-mode", self.permission_mode,
               *(["--restricted"] if self.restricted else ["--setting-sources", "project,local"]),
               "--settings", settings(self.deny, self.no_writes, self.no_reads), "--disable-slash-commands",
               "--tools", ",".join(t for t in BUILTIN_TOOLS if t not in self.disallowed_tools)]
        if session_id:
            cmd += ["--resume", session_id]
        model = self.light_model if scope is not None and scope.simple and self.light_model else self.model
        if model:
            cmd += ["--model", model]
        # Strict: the worker gets Milo's MCP servers only, not whatever else Claude Code has configured.
        cmd += ["--strict-mcp-config"]
        servers = scope.servers(self.servers) if scope is not None else self.servers
        if servers:
            # -p can't ask for permission, so Milo's tools are allowed up front: the brain checks each call and
            # asks the user when it matters.
            cmd += ["--mcp-config", self._config(servers, scope), "--allowedTools", *(f"mcp__{s.name}" for s in servers)]
        if self.disallowed_tools:
            cmd += ["--disallowedTools", *self.disallowed_tools]
        return cmd + ["--", prompt]

    async def reply(self, prompt: str, session_id: str | None, *, on_step: StepCallback | None = None,
                    on_session: SessionCallback | None = None, on_plan: PlanCallback | None = None,
                    scope: ToolScope | None = None) -> Reply:
        on_line = lines(ClaudeActivity(on_step, self.workdir).line if on_step is not None else None,
                        RunWatch(on_session, on_plan).line if on_session or on_plan else None)
        try:
            self.workdir.mkdir(parents=True, exist_ok=True)
            clear_steering(self.workdir)  # nothing a helper left there steers this one (ADR 0020)
        except OSError as e:
            raise HarnessError(f"the worker's folder isn't safe to work in: {e}", transient=False) from None
        code, out, err = await run(self.command(prompt, session_id, scope), cwd=self.workdir, timeout_s=self.timeout_s,
                                   on_line=on_line, done=is_result)
        return parse_result(result_line(out), code, err, session_id)


def mcp_servers(servers: tuple[ToolServer, ...]) -> dict:
    """The --mcp-config file for Claude Code."""
    return {"mcpServers": {s.name: {"type": "stdio", "command": s.command[0], "args": list(s.command[1:]),
                                    **({"env": dict(s.env)} if s.env else {})} for s in servers}}


def is_result(line: str) -> bool:
    """The `{"type":"result",...}` line, which ends a `claude -p` turn."""
    return '"type":"result"' in line[:40] and line.lstrip().startswith("{")


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
        ctx.worker_dir,
        model=o.model,
        light_model=o.light_model,
        permission_mode=o.permission_mode,
        timeout_s=o.timeout_s,
        mac_tools=ctx.mac_tools,
        tool_servers=ctx.tool_servers,
        mcp_config=ctx.state_dir / "mcp-servers.json",
        disallowed_tools=o.disallowed_tools,
        protected=Protected(ctx.home),
        restricted=o.restricted,
    )
