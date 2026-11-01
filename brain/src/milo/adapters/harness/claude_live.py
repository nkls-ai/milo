"""Claude Code as Milo's live chat model: one persistent `claude -p` process speaking stream-json.

The process keeps the conversation in memory, so a turn sends only the new user message and the
reply streams back token by token. Protocol (measured against claude 2.x):

- in:  `{"type":"user","message":{"role":"user","content":...}}` per turn (a string, or text and base64
       image blocks when a screenshot goes along; checked against claude 2.1), and
       `{"type":"control_request","request_id":...,"request":{"subtype":"interrupt"}}` to stop a reply.
- out: `stream_event` lines carrying `content_block_delta`/`text_delta`, then one `result` per turn
       (`error_during_execution` after an interrupt). The process survives an interrupt.

start() also sends a short priming message and reads its reply in the background. The first message to a
fresh process is slow (the CLI finishes starting up, and the system prompt isn't in the prompt cache yet):
measured 2 to 3 s to the first token against about 1 s for later ones. The user's first turn then doesn't
pay for it. The priming exchange stays in the conversation; it says nobody has spoken yet.

A reader task routes stdout into a queue. A turn that ends early (interrupt, or the consumer stops
iterating) leaves its `result` owed; the next turn reads up to it first, so turns never see each
other's lines.
"""

from __future__ import annotations

import asyncio
import base64
import collections
import contextlib
import itertools
import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.registry import LIVE_MODELS, AdapterContext, options_from
from milo.core.types import HarnessError, Usage

from ._binary import executable_command, find_binary

log = logging.getLogger(__name__)

STDOUT_LIMIT = 16 * 1024 * 1024  # one JSON line can carry a whole message
CLOSE_TIMEOUT_S = 3.0
DRAIN_TIMEOUT_S = 15.0  # how long to wait for an abandoned turn's result before restarting
STALL_TIMEOUT_S = 30.0
"""A reply that sends nothing for this long is stuck: on 2026-10-31 the CLI stopped in the middle of one and sent
no more, and every later message waited behind it. Its first words take 1 to 5 seconds."""

PRIME_TEXT = "(Nobody has said anything yet. This only opens the line. Reply with just [neutral].)"

_QUIET_EVENTS = {"stream_event", "assistant", "result", "system", "rate_limit_event"}
"""Events every reply has; any other kind is logged, so a reply that stalls says what the CLI wanted."""

_EOF = object()  # the process closed stdout
_WAKE = object()  # interrupt() wants the running turn to notice at once


@dataclass(frozen=True)
class ClaudeLiveOptions:
    binary: str = ""
    model: str = "claude-haiku-5-5"  # first sentence after ~1.3 s; Sonnet 5.5 took 2 to 4 s (docs/research/voice.md)
    effort: str = "low"
    prime: bool = True  # send a priming message when a conversation starts, so the first turn is fast


class _Session:
    """One claude process and the queue its stdout lines land in."""

    def __init__(self, proc: asyncio.subprocess.Process):
        self.proc = proc
        self.events: asyncio.Queue[object] = asyncio.Queue()
        self.owed_results = 0  # turns that ended before their `result` line was read
        self.dead = False
        self.tasks = (asyncio.create_task(self._read_stdout()), asyncio.create_task(self._read_stderr()))

    async def _read_stdout(self) -> None:
        try:
            while line := await self.proc.stdout.readline():
                try:
                    self.events.put_nowait(json.loads(line))
                except json.JSONDecodeError:
                    log.debug("claude_live: non-JSON line %r", line[:200])
        except (ValueError, OSError) as e:  # ValueError: a line over STDOUT_LIMIT
            log.warning("claude_live: stdout broke: %s", e)
        finally:
            self.dead = True
            self.events.put_nowait(_EOF)

    async def _read_stderr(self) -> None:
        with contextlib.suppress(ValueError, OSError):
            while line := await self.proc.stderr.readline():
                log.info("claude_live stderr: %s", line.decode(errors="replace").rstrip())

    def send_nowait(self, message: dict) -> bool:
        """Write one JSON line without waiting. Usable in a finally block. False if the pipe is gone."""
        if self.dead or self.proc.stdin is None or self.proc.stdin.is_closing():
            return False
        try:
            self.proc.stdin.write((json.dumps(message) + "\n").encode())
        except (OSError, RuntimeError):
            return False
        return True

    async def send(self, message: dict) -> None:
        if not self.send_nowait(message):
            raise HarnessError("claude stopped unexpectedly", transient=True)
        try:
            await self.proc.stdin.drain()
        except (OSError, RuntimeError):
            raise HarnessError("claude stopped unexpectedly", transient=True) from None

    async def close(self) -> None:
        proc = self.proc
        if proc.returncode is None:
            if proc.stdin is not None and not proc.stdin.is_closing():
                proc.stdin.close()
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), CLOSE_TIMEOUT_S)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                await proc.wait()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


class _Turn:
    def __init__(self, session: _Session):
        self.session = session
        self.interrupted = False


class ClaudeLiveModel:
    name = "claude_live"

    def __init__(self, binary: str, workdir: Path, *, model: str = "claude-haiku-5-5", effort: str = "low",
                 prime: bool = True):
        self.binary = binary
        self.workdir = workdir
        self.model = model
        self.effort = effort
        self.prime = prime
        self.stall_timeout_s = STALL_TIMEOUT_S
        self._priming: asyncio.Task | None = None
        self.last_usage = Usage()
        self._system_prompt = ""
        self._session: _Session | None = None
        self._turn: _Turn | None = None
        self._lock = asyncio.Lock()
        self._ids = itertools.count(1)

    def command(self, system_prompt: str) -> list[str]:
        cmd = [self.binary, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
               "--include-partial-messages"]
        if self.model:
            cmd += ["--model", self.model]
        if self.effort:
            cmd += ["--effort", self.effort]
        return cmd + ["--tools", "", "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
                      "--no-session-persistence", "--system-prompt", system_prompt]

    async def start(self, system_prompt: str) -> None:
        await self.close()
        self._system_prompt = system_prompt
        self._session = await self._spawn()
        if self.prime:
            self._priming = asyncio.create_task(self._prime())

    async def _prime(self) -> None:
        started = asyncio.get_running_loop().time()
        try:
            async for _ in self.turn(PRIME_TEXT):
                pass
        except HarnessError as e:
            log.warning("claude_live: priming failed: %s", e)
            return
        log.info("claude_live primed in %.2fs, %d in (%d cached)", asyncio.get_running_loop().time() - started,
                 self.last_usage.input_tokens, self.last_usage.cached_input_tokens)

    async def turn(self, text: str, images: Sequence[Path] = ()) -> AsyncIterator[str]:
        async with self._lock:
            session = await self._ready_session()
            turn = self._turn = _Turn(session)
            # Reset first: an interrupted turn ends before its usage arrives and must not report the
            # previous turn's numbers a second time.
            self.last_usage = Usage()
            got_result = False
            recent: collections.deque[str] = collections.deque(maxlen=8)  # what came last, for a stall's log line
            try:
                await session.send({"type": "user", "message": {"role": "user", "content": content(text, images)}})
                while True:
                    try:
                        async with asyncio.timeout(self.stall_timeout_s):
                            event = await session.events.get()
                    except TimeoutError:
                        got_result = True  # nothing more will come: start a fresh process for the next turn
                        log.warning("claude_live: nothing for %.0fs in the middle of a reply (last: %s); restarting",
                                    self.stall_timeout_s, ", ".join(recent) or "nothing")
                        await self._forget(session)
                        raise HarnessError("claude went quiet in the middle of a reply", transient=True) from None
                    recent.append(_kind(event))
                    if event is _EOF:
                        got_result = True  # nothing more will come from this process
                        await self._forget(session)
                        raise HarnessError("claude stopped in the middle of a reply", transient=True)
                    if isinstance(event, dict) and event.get("type") == "result":
                        got_result = True
                        self.last_usage = _usage(event.get("usage") or {})
                        if event.get("is_error") and not turn.interrupted:
                            raise HarnessError(f"claude failed: {event.get('result') or event.get('subtype')}",
                                               transient=True)
                        return
                    if turn.interrupted:
                        return
                    if isinstance(event, dict) and event.get("type") not in _QUIET_EVENTS:
                        # Something the CLI says besides the reply (a request, a tool call): no content.
                        log.info("claude_live: %s %s", event.get("type"),
                                 event.get("subtype") or (event.get("request") or {}).get("subtype") or "")
                    delta = _text_delta(event) if isinstance(event, dict) else ""
                    if delta:
                        yield delta
            finally:
                self._turn = None
                if not got_result:
                    # Interrupted, or the consumer stopped iterating: stop the reply (no await allowed
                    # here when the generator is being closed) and read its result on the next turn.
                    if not turn.interrupted:
                        session.send_nowait(self._interrupt_request())
                    session.owed_results += 1

    async def interrupt(self) -> None:
        turn = self._turn
        if turn is None or turn.interrupted:
            return
        turn.interrupted = True
        turn.session.events.put_nowait(_WAKE)
        if turn.session.send_nowait(self._interrupt_request()):
            with contextlib.suppress(OSError, RuntimeError):
                await turn.session.proc.stdin.drain()

    async def close(self) -> None:
        priming, self._priming = self._priming, None
        if priming is not None and not priming.done():
            priming.cancel()
            await asyncio.gather(priming, return_exceptions=True)
        session, self._session = self._session, None
        if session is not None:
            await session.close()

    async def _ready_session(self) -> _Session:
        """The running process with all earlier turns' output consumed; (re)started if needed."""
        session = self._session
        if session is not None and session.owed_results:
            try:
                async with asyncio.timeout(DRAIN_TIMEOUT_S):
                    while session.owed_results and not session.dead:
                        event = await session.events.get()
                        if isinstance(event, dict) and event.get("type") == "result":
                            session.owed_results -= 1
            except TimeoutError:
                log.warning("claude_live: no result after interrupt; restarting")
                await self._forget(session)
                session = None
        if session is not None and (session.dead or session.proc.returncode is not None):
            await self._forget(session)
            session = None
        if session is None:
            session = self._session = await self._spawn()
        return session

    async def _spawn(self) -> _Session:
        self.workdir.mkdir(parents=True, exist_ok=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                *executable_command(self.binary, self.command(self._system_prompt)[1:]), cwd=self.workdir, limit=STDOUT_LIMIT,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except OSError as e:
            raise HarnessError(f"could not start {Path(self.binary).name}: {e}", transient=False) from None
        log.info("claude_live started (%s, effort %s, pid %s)", self.model or "default model", self.effort, proc.pid)
        return _Session(proc)

    async def _forget(self, session: _Session) -> None:
        if self._session is session:
            self._session = None
        await session.close()

    def _interrupt_request(self) -> dict:
        return {"type": "control_request", "request_id": f"milo-interrupt-{next(self._ids)}",
                "request": {"subtype": "interrupt"}}


def _kind(event: object) -> str:
    """An event's kind without its content: "stream_event/content_block_delta/text_delta", "result"."""
    if not isinstance(event, dict):
        return "eof" if event is _EOF else "wake"
    inner = event.get("event") if isinstance(event.get("event"), dict) else {}
    delta = inner.get("delta") if isinstance(inner.get("delta"), dict) else {}
    return "/".join(str(p) for p in (event.get("type"), event.get("subtype"), inner.get("type"), delta.get("type"))
                    if p)


def content(text: str, images: Sequence[Path] = ()) -> str | list[dict]:
    """A user message's content: the plain text, or a text block followed by one block per readable PNG."""
    blocks: list[dict] = []
    for path in images:
        try:
            data = base64.b64encode(Path(path).read_bytes()).decode()
        except OSError as e:
            log.warning("claude_live: leaving out an image: %s", e)
            continue
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}})
    return [{"type": "text", "text": text}, *blocks] if blocks else text


def _text_delta(event: dict) -> str:
    if event.get("type") != "stream_event":
        return ""
    e = event.get("event") or {}
    if e.get("type") != "content_block_delta":
        return ""
    delta = e.get("delta") or {}
    return str(delta.get("text", "")) if delta.get("type") == "text_delta" else ""


def _usage(u: Mapping[str, Any]) -> Usage:
    """Same accounting as the claude harness: input_tokens counts cached and cache-write tokens too."""
    cached = u.get("cache_read_input_tokens", 0) or 0
    return Usage(
        input_tokens=(u.get("input_tokens", 0) or 0) + cached + (u.get("cache_creation_input_tokens", 0) or 0),
        cached_input_tokens=cached,
        output_tokens=u.get("output_tokens", 0) or 0,
    )


@LIVE_MODELS.register("claude_live")
def _claude_live(options: Mapping[str, Any], ctx: AdapterContext) -> ClaudeLiveModel:
    o = options_from(ClaudeLiveOptions, options, "chat.claude_live")
    return ClaudeLiveModel(
        find_binary(o.binary, "claude", section="chat.claude_live"),
        ctx.state_dir / "live",
        model=o.model,
        effort=o.effort,
        prime=o.prime,
    )
