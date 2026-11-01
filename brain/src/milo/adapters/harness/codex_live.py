"""Conversational Codex app-server session, separate from Milo's worker harness.

The CLI keeps its login and model conversation; Milo keeps every action. Shell,
web, app and extension tools are disabled, the session is read-only, and every
server request for permission or a tool result is refused. Unexpected tool events
end the session rather than silently replaying a potentially committed turn.
"""
from __future__ import annotations

import asyncio
import base64
import itertools
import json
import os
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo import system
from milo.core.registry import LIVE_MODELS, AdapterContext, ConfigError, options_from
from milo.core.types import HarnessError, Usage
from ._binary import executable_command, find_binary
from ._process import STDOUT_LIMIT, stop
from .codex import BUNDLED_CODEX, HOME_CONFIG, _replace, prepare_home, user_codex_home

STALLED_S = 45.0
RPC_S = 20.0
TEXT_ONLY = """You are Milo's conversational model. Reply only with text and Milo's
tags specified below. Never call tools, execute commands, edit files, browse, or
request permissions. Milo's separately approved helpers perform actions.\n"""

# Some Codex versions still advertise model-defined tools such as apply_patch.
# Read-only sandboxing and refused approvals enforce the action boundary too.
CHAT_CONFIG = HOME_CONFIG.replace("[features]", '''web_search = "disabled"
approval_policy = "on-request"
sandbox_mode = "read-only"
cli_auth_credentials_store = "file"

[features]
shell_tool = false
code_mode = false
code_mode_host = false
view_image = false
hooks = false
sleep_tool = false
workspace_dependencies = false
skill_search = false
skill_mcp_dependency_install = false
''')


@dataclass(frozen=True)
class CodexLiveOptions:
    binary: str = ""
    model: str = ""
    reasoning_effort: str = "low"

    def __post_init__(self):
        if not all(isinstance(x, str) for x in (self.binary, self.model, self.reasoning_effort)):
            raise ConfigError("[chat.codex_live] binary, model and reasoning_effort must be strings")


class _Rpc:
    def __init__(self, proc: asyncio.subprocess.Process):
        self.proc = proc
        self.events: asyncio.Queue[dict | HarnessError] = asyncio.Queue()
        self.pending: dict[int, asyncio.Future] = {}
        self.ids = itertools.count(1)
        self.starting = True
        self.startup_stderr = b""
        self.reader = asyncio.create_task(self._read())
        self.stderr = asyncio.create_task(self._drain())

    async def send(self, message: dict) -> None:
        if self.proc.stdin is None or self.proc.returncode is not None:
            raise HarnessError("Codex chat disconnected", transient=True)
        try:
            self.proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            raise HarnessError("Codex chat disconnected", transient=True) from None

    async def call(self, method: str, params: dict) -> dict:
        ident = next(self.ids)
        future = asyncio.get_running_loop().create_future()
        self.pending[ident] = future
        try:
            await self.send({"id": ident, "method": method, "params": params})
            return await asyncio.wait_for(future, RPC_S)
        except TimeoutError:
            raise HarnessError(f"Codex chat did not answer {method}", transient=True) from None
        finally:
            self.pending.pop(ident, None)

    async def _drain(self) -> None:
        # Keep only a bounded startup diagnostic, before any model turn exists.
        # After startup stderr is drained without retaining prompts or paths.
        while chunk := await self.proc.stderr.read(65536):
            if self.starting:
                self.startup_stderr = (self.startup_stderr + chunk)[-2048:]

    async def _read(self) -> None:
        error = HarnessError("Codex chat disconnected; please try a new conversation", transient=True)
        try:
            while raw := await self.proc.stdout.readline():
                event = json.loads(raw)
                if not isinstance(event, dict):
                    raise ValueError("expected an object")
                if "error" in event and "id" not in event and "method" not in event:
                    # app-server reports configuration admission errors before
                    # JSON-RPC initialization. These refer only to our config.
                    detail = event.get("error") or {}
                    data = detail.get("data") or {}
                    message = str(detail.get("message", "startup failed"))[:500]
                    if data.get("reason") == "configLoad":
                        error = HarnessError(f"Codex chat configuration: {message}", transient=False)
                        break
                if "method" in event and "id" in event:
                    # No server-initiated request can acquire authority in chat.
                    method = event["method"]
                    if method in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
                        response = {"result": {"decision": "cancel"}}
                    elif method == "item/permissions/requestApproval":
                        response = {"result": {"permissions": {}, "scope": "turn"}}
                    else:
                        response = {"error": {"code": -32601, "message": "Tools and approvals are disabled in Milo chat"}}
                    await self.send({"id": event["id"], **response})
                    self.events.put_nowait(HarnessError("Codex tried to use a tool in chat; the request was refused", transient=False))
                elif "id" in event:
                    future = self.pending.get(event["id"])
                    if future is not None and not future.done():
                        if "error" in event:
                            message = str((event.get("error") or {}).get("message", "request failed"))
                            future.set_exception(HarnessError(f"Codex chat: {message}", transient=False))
                        else:
                            future.set_result(event.get("result") or {})
                else:
                    self.events.put_nowait(event)
        except (ValueError, UnicodeError, OSError, HarnessError):
            error = HarnessError("Codex chat returned an invalid or disconnected stream", transient=True)
        finally:
            if self.starting and error.transient:
                try:
                    await asyncio.wait_for(asyncio.shield(self.stderr), .2)
                except (TimeoutError, asyncio.CancelledError):
                    pass
                diagnostic = re.sub(r"\x1b\[[0-9;]*m", "", self.startup_stderr.decode("utf-8", errors="replace"))
                for line in diagnostic.splitlines():
                    if line.lower().startswith("error:"):
                        message = "".join(c for c in line if c.isprintable())[:500]
                        error = HarnessError(f"Codex chat startup: {message}", transient=False)
                        break
            self.events.put_nowait(error)
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(error)

    async def close(self) -> None:
        await stop(self.proc, grace_s=0.5)
        for task in (self.reader, self.stderr):
            task.cancel()
        await asyncio.gather(self.reader, self.stderr, return_exceptions=True)


class CodexLiveModel:
    name = "codex_live"

    def __init__(self, binary: str, workdir: Path, *, model: str = "", reasoning_effort: str = "low",
                 login_from: Path | None = None):
        self.binary, self.workdir = binary, workdir
        self.model, self.reasoning_effort = model, reasoning_effort
        self.login_from = login_from or user_codex_home()
        self.last_usage = Usage()
        self.stall_timeout_s = STALLED_S
        self._rpc: _Rpc | None = None
        self._thread_id = ""
        self._turn_id = ""
        self._system_prompt = ""
        self._lock = asyncio.Lock()
        self._interrupted = False

    def command(self) -> list[str]:
        return executable_command(self.binary, ["app-server", "--strict-config", "--listen", "stdio://"])

    async def start(self, system_prompt: str) -> None:
        await self.close()
        self._system_prompt = system_prompt
        home = self.workdir / "home"
        prepare_home(home, self.login_from)
        _replace(home / "config.toml", CHAT_CONFIG)
        cwd = self.workdir / "conversation"
        cwd.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, CODEX_HOME=str(home.resolve()))
        # Login comes only from the linked CLI login, never an inherited API key.
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_THREAD_ID"):
            env.pop(key, None)
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.command(), cwd=cwd, env=env, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=STDOUT_LIMIT,
                **system.isolated_process(),
            )
        except OSError as e:
            raise HarnessError(f"Could not start Codex chat: {e}", transient=False) from None
        rpc = self._rpc = _Rpc(proc)
        try:
            await rpc.call("initialize", {"clientInfo": {"name": "milo_chat", "version": "1.0"},
                                          "capabilities": {"experimentalApi": True}})
            await rpc.send({"method": "initialized", "params": {}})
            params: dict[str, Any] = {
                "cwd": str(cwd.resolve()), "baseInstructions": TEXT_ONLY + system_prompt,
                "approvalPolicy": "on-request", "approvalsReviewer": "user", "sandbox": "read-only",
                "ephemeral": True, "dynamicTools": [], "environments": [],
            }
            if self.model:
                params["model"] = self.model
            result = await rpc.call("thread/start", params)
            sandbox = result.get("sandbox") or {}
            if result.get("approvalPolicy") != "on-request" or sandbox.get("type") != "readOnly" or sandbox.get("networkAccess", False):
                raise HarnessError("Codex chat did not accept read-only permissions; update Codex or check managed settings", transient=False)
            self._thread_id = result["thread"]["id"]
            rpc.starting = False
            rpc.startup_stderr = b""
        except BaseException:
            await self.close()
            raise

    async def turn(self, text: str, images: Sequence[Path] = ()) -> AsyncIterator[str]:
        async with self._lock:
            rpc = self._rpc
            if rpc is None:
                raise HarnessError("Codex chat is not connected; start a new conversation", transient=True)
            self.last_usage = Usage()
            self._interrupted = False
            # Notifications from thread/start aren't turn output.
            while not rpc.events.empty():
                event = rpc.events.get_nowait()
                if isinstance(event, HarnessError):
                    await self.close()
                    raise event
            try:
                params: dict[str, Any] = {"threadId": self._thread_id, "input": content(text, images),
                    "approvalPolicy": "on-request", "approvalsReviewer": "user",
                    "sandboxPolicy": {"type": "readOnly", "networkAccess": False}, "environments": []}
                if self.reasoning_effort:
                    params["effort"] = self.reasoning_effort
                started = await rpc.call("turn/start", params)
                self._turn_id = started["turn"]["id"]
                while not self._interrupted:
                    event = await asyncio.wait_for(rpc.events.get(), self.stall_timeout_s)
                    if isinstance(event, HarnessError):
                        raise event
                    method, p = event.get("method", ""), event.get("params") or {}
                    if p.get("threadId", self._thread_id) != self._thread_id:
                        continue
                    event_turn = p.get("turnId") or (p.get("turn") or {}).get("id")
                    if event_turn is not None and event_turn != self._turn_id:
                        continue
                    if method in ("item/started", "item/completed"):
                        kind = (p.get("item") or {}).get("type")
                        if kind not in ("userMessage", "agentMessage", "reasoning", "contextCompaction", None):
                            raise HarnessError(f"Codex attempted a {kind} tool in chat; conversation stopped", transient=False)
                    if method.startswith(("item/commandExecution/", "item/fileChange/", "item/mcpToolCall/", "item/tool/")):
                        raise HarnessError("Codex attempted a tool in chat; conversation stopped", transient=False)
                    if method == "item/agentMessage/delta":
                        yield str(p.get("delta", ""))
                    elif method == "thread/tokenUsage/updated":
                        u = (p.get("tokenUsage") or {}).get("last") or {}
                        self.last_usage = Usage(input_tokens=u.get("inputTokens", 0),
                            cached_input_tokens=u.get("cachedInputTokens", 0), output_tokens=u.get("outputTokens", 0))
                    elif method == "error":
                        if not p.get("willRetry", False):
                            raise HarnessError("Codex chat: " + str((p.get("error") or {}).get("message", "turn failed")), transient=True)
                    elif method == "turn/completed":
                        turn = p.get("turn") or {}
                        if turn.get("status") == "failed":
                            raise HarnessError("Codex chat: " + str((turn.get("error") or {}).get("message", "turn failed")), transient=True)
                        return
            except TimeoutError:
                await self.close()
                raise HarnessError("Codex chat stopped responding; start a new conversation", transient=True) from None
            except asyncio.CancelledError:
                # Barge-in cancels the generator too. Keep the conversational
                # thread when Codex acknowledges its interrupted turn.
                await asyncio.shield(self.interrupt())
                raise
            except BaseException:
                await asyncio.shield(self.close())
                raise
            finally:
                self._turn_id = ""

    async def interrupt(self) -> None:
        rpc, turn_id = self._rpc, self._turn_id
        if rpc is None or not turn_id:
            return
        try:
            await asyncio.wait_for(rpc.call("turn/interrupt", {"threadId": self._thread_id, "turnId": turn_id}), 2.0)
        except (HarnessError, TimeoutError):
            self._interrupted = True
            await self.close()

    async def close(self) -> None:
        rpc, self._rpc = self._rpc, None
        self._thread_id = ""
        if rpc is not None:
            await rpc.close()


def content(text: str, images: Sequence[Path] = ()) -> list[dict]:
    blocks = [{"type": "text", "text": text}]
    for path in images:
        # Inline bytes keep screenshots independent of Codex filesystem tools.
        try:
            data = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError:
            raise HarnessError(f"Could not read screenshot {path.name}", transient=False) from None
        mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        blocks.append({"type": "image", "url": f"data:{mime};base64,{data}"})
    return blocks


@LIVE_MODELS.register("codex_live")
def _codex_live(options: Mapping[str, Any], ctx: AdapterContext) -> CodexLiveModel:
    o = options_from(CodexLiveOptions, options, "chat.codex_live")
    return CodexLiveModel(find_binary(o.binary, "codex", fallbacks=(BUNDLED_CODEX,), section="chat.codex_live"),
                          ctx.state_dir / "codex-chat", model=o.model, reasoning_effort=o.reasoning_effort)

