"""Codex CLI adapter: one `codex exec` (or `codex exec resume`) process per turn.

The worker runs in a Codex home of its own (`<workspace>/.codex`), not the user's `~/.codex`: there it gets
Milo's tools and instructions only, none of the user's plugins, skills, MCP servers, global AGENTS.md or
settings. Only the login is shared, through a symlink to the user's `auth.json`. Codex writes a refreshed
login through the link (checked with codex 0.164), so the user's own Codex stays logged in. Codex's sandbox
keeps `.codex` read-only for the worker's commands, so a task can't change the home the next task runs in.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.hands import mac_server
from milo.core.ports import StepCallback
from milo.core.registry import HARNESSES, AdapterContext, options_from
from milo.core.types import REPLY_SCHEMA, HarnessError, Reply, ToolServer, Usage

from ._activity import CodexActivity
from ._binary import find_binary
from ._process import last_line, run

log = logging.getLogger(__name__)

# Long enough for a question to the user (approvals time out at 60 s by default).
TOOL_TIMEOUT_S = 240
# Where the ChatGPT desktop app ships its own codex.
BUNDLED_CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")

# The config.toml of Milo's own Codex home. Codex's built-in computer use, browser, plugins, apps, sub-agents,
# image generation and skills are off, so the worker uses Milo's tools, which check and show every action.
HOME_CONFIG = """\
# Written by Milo before every task; edits are overwritten. Milo's worker uses only Milo's tools.
check_for_update_on_startup = false

[features]
computer_use = false
browser_use = false
in_app_browser = false
plugins = false
remote_plugin = false
apps = false
tool_suggest = false
multi_agent = false
goals = false
memories = false
image_generation = false

[skills]
include_instructions = false

[skills.bundled]
enabled = false
"""


def user_codex_home() -> Path:
    """Where the user's own Codex keeps its login: $CODEX_HOME, else ~/.codex."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


# What Codex would read from its home as instructions, hooks, rules or extra config. Milo never puts any there.
_FOREIGN = ("AGENTS.md", "AGENTS.override.md", "hooks.json", "hooks", "rules", "skills", "plugins", "agents")


def prepare_home(home: Path, login_from: Path) -> None:
    """Milo's Codex home: a fresh config.toml, a link to the user's login, nothing else that steers Codex.

    A link that is already there is kept, and so is a real auth.json (a login made for Milo alone). Nothing
    here follows a symlink except the login: config.toml is replaced, not written through.
    """
    if home.is_symlink():
        raise HarnessError(f"{home} is a symlink; Milo's Codex home must be a real folder", transient=False)
    home.mkdir(parents=True, exist_ok=True)
    for name in _FOREIGN:
        path = home / name
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    for profile in home.glob("*.config.toml"):
        profile.unlink()
    staged = home / "config.toml.milo"
    staged.unlink(missing_ok=True)
    staged.write_text(HOME_CONFIG)
    os.replace(staged, home / "config.toml")
    auth, source = home / "auth.json", login_from / "auth.json"
    if auth.is_symlink() and not auth.exists():
        auth.unlink()  # the user's login moved or went away
    if not auth.exists() and not auth.is_symlink() and source.exists():
        auth.symlink_to(source)
    if not auth.exists():
        log.warning("codex has no login in %s; run `codex login` first", login_from)


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
                 mac_tools: Sequence[str] = (), tool_servers: tuple[ToolServer, ...] = (),
                 home: Path | None = None, login_from: Path | None = None):
        """`home` is Milo's own Codex home (None: the user's, for tests), `login_from` the user's."""
        self.binary = binary
        self.home = home
        self.login_from = login_from or user_codex_home()
        self.mac_tools = tuple(mac_tools)
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
            "--ignore-rules",  # the user's command rules are for their own Codex
            "--output-schema", str(self.schema_path),
            # `exec resume` has no --sandbox flag, so set it through config on both paths.
            "-c", f'sandbox_mode="{self.sandbox}"',
            "-c", f'model_reasoning_effort="{self.reasoning_effort}"',
        ]
        if self.model:
            cmd += ["-m", self.model]
        for server in (*mac_server(self.mac_tools), *self.tool_servers):
            cmd += mcp_overrides(server)
        return cmd + ["--", prompt]

    async def reply(self, prompt: str, session_id: str | None, *, on_step: StepCallback | None = None) -> Reply:
        on_line = CodexActivity(on_step, self.workdir).line if on_step is not None else None
        env = None
        if self.home is not None:
            prepare_home(self.home, self.login_from)
            env = {**os.environ, "CODEX_HOME": str(self.home)}
        code, out, err = await run(self.command(prompt, session_id), cwd=self.workdir, timeout_s=self.timeout_s,
                                   on_line=on_line, env=env)
        thread_id, text, usage, error = parse_events(out.splitlines())
        if error or code != 0 or text is None:
            raise HarnessError(f"codex failed: {error or last_line(err, code)}", transient=True)
        return Reply.from_model_text(text, usage, thread_id or session_id)


def mcp_overrides(server: ToolServer) -> list[str]:
    """`-c` overrides that add one MCP server. JSON strings and arrays are valid TOML values.

    exec can't ask for approval, so it would refuse every MCP call (checked with codex 0.164). Milo's tools
    ask the user themselves when it matters, so codex auto-approves them.
    """
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
        mac_tools=ctx.mac_tools,
        tool_servers=ctx.tool_servers,
        home=ctx.home / ".codex",
    )
