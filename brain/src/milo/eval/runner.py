"""Replay the eval tasks as typed turns against a real brain on made-up data, and score them.

Each case gets a fresh workspace under /tmp with fake connections, no microphone, no voice and no
heartbeat, and its own brain process. The runner connects to that brain's socket the way the app does,
types the request, answers Milo's questions the way the case says, waits until he is done, then checks
the made-up world. Nothing touches the user's real calendar, mail, notes, files or ~/Milo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from milo import system
from milo.adapters.harness._process import stop as _stop

from .cases import CASES, Case, Outcome
from .world import seed

QUIET_S = 3.0
CASE_TIMEOUT_S = 300.0
START_TIMEOUT_S = 30.0

CONFIG = """\
[chat]
use = "claude_live"

[chat.claude_live]
model = "{chat_model}"
effort = "low"

[harness]
use = "claude"

[harness.claude]
model = "{worker_model}"
# Only Milo's tools: no shell, no file reading outside them, no web. The worker can't reach real data.
permission_mode = "default"
disallowed_tools = ["Bash", "Glob", "Grep", "Read", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch",
                    "Task", "Agent"]
timeout_s = 240

[connections]
use = "fake"

[approvals]
timeout_s = 30
speak = false

[stt]
use = "none"

[tts]
use = "none"
fallback = ""

[audio]
use = "none"

[dictation]
use = "plain"
keep_history = false

[heartbeat]
enabled = false

[hands]
# No milo-mac tools: they would act on the real screen.
enabled = false
"""


@dataclass
class Result:
    case: Case
    ok: bool
    seconds: float
    said: str
    questions: list[str]
    error: str = ""


async def run_case(case: Case, home: Path, today: date, *, chat_model: str, worker_model: str,
                   timeout_s: float = CASE_TIMEOUT_S) -> Result:
    home.mkdir(parents=True)
    (home / "config.toml").write_text(CONFIG.format(chat_model=chat_model, worker_model=worker_model))
    world = seed(home / "fake", today)
    (home / "logs").mkdir()
    stderr = open(home / "logs" / "brain.stderr", "wb")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "milo.server", env={**os.environ, "MILO_HOME": str(home)},
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=stderr, **system.isolated_process())
    try:
        events, questions, seconds, error = await _converse(case, home / "run" / "brain.sock", timeout_s)
    finally:
        await _stop(proc)
        stderr.close()
    entries: dict[str, dict] = {}
    for event in events:
        for entry in event.get("entries", []) + ([event["entry"]] if "entry" in event else []):
            entries[entry["id"]] = entry
    replies = [e["text"] for e in entries.values() if e["kind"] == "milo" and e.get("text")]
    replies += [e["result"] for e in entries.values() if e["kind"] == "task" and e.get("result")]
    profile = home / "memory" / "profile.md"
    outcome = Outcome(today, world.load(), replies, questions,
                      [e["text"] for e in entries.values() if e["kind"] == "task"],
                      profile.read_text(encoding="utf-8") if profile.exists() else "")
    try:
        ok = not error and bool(case.check(outcome))
    except Exception as e:  # a check that trips over an odd world is a failed case, not a crashed run
        ok, error = False, f"check failed: {e}"
    return Result(case, ok, seconds, " | ".join(replies), questions, error)


async def _converse(case: Case, socket: Path, timeout_s: float) -> tuple[list[dict], list[str], float, str]:
    reader, writer = await _connect(socket)
    events: list[dict] = []
    questions: list[str] = []
    writer.write((json.dumps({"type": "text", "text": case.say, "speak": False}) + "\n").encode())
    await writer.drain()
    started = last = time.monotonic()
    replied = asked = False
    running: set[str] = set()
    error = ""
    while True:
        now = time.monotonic()
        if now - started > timeout_s:
            error = "timed out"
            break
        if replied and not running and not asked and now - last >= QUIET_S:
            break
        try:
            line = await asyncio.wait_for(reader.readline(), 0.25)
        except TimeoutError:
            continue
        if not line:
            error = "the brain went away"
            break
        event = json.loads(line)
        if event["type"] in ("level", "state", "emotion"):
            continue
        events.append(event)
        last = time.monotonic()
        if event["type"] == "entry":
            entry = event["entry"]
            if entry["kind"] == "milo" and entry.get("done"):
                replied = True
            if entry["kind"] == "task":
                (running.add if entry.get("status") == "running" else running.discard)(entry["id"])
        elif event["type"] == "confirm":
            questions.append(event["question"])
            asked = True
            answer = {"type": "confirm_answer", "id": event["id"], "yes": case.answer == "yes"}
            writer.write((json.dumps(answer) + "\n").encode())
            await writer.drain()
        elif event["type"] == "confirm_done":
            asked = False
    writer.close()
    return events, questions, last - started, error


async def _connect(socket: Path):
    deadline = time.monotonic() + START_TIMEOUT_S
    while True:
        try:
            sock = await asyncio.to_thread(system.connect_local, socket, 3.0)
            sock.setblocking(False)
            reader, writer = await asyncio.open_connection(sock=sock, limit=16 * 1024 * 1024)
            return reader, writer
        except OSError:
            if time.monotonic() > deadline:
                raise RuntimeError(f"no brain on {socket} after {START_TIMEOUT_S:.0f}s") from None
            await asyncio.sleep(0.2)


async def run(cases: list[Case], root: Path, *, chat_model: str, worker_model: str, timeout_s: float) -> list[Result]:
    today = date.today()
    results = []
    for case in cases:
        try:
            result = await run_case(case, root / case.id, today, chat_model=chat_model, worker_model=worker_model,
                                    timeout_s=timeout_s)
        except Exception as e:
            result = Result(case, False, 0.0, "", [], f"runner error: {e}")
        results.append(result)
        mark = "PASS" if result.ok else "FAIL"
        print(f"{case.id} {mark} {result.seconds:5.1f}s  {case.say}", flush=True)
        if not result.ok:
            print(f"     expected: {case.expect}", flush=True)
            print(f"     got: {(result.error + ' ' if result.error else '')}{result.said[:300]}", flush=True)
    return results


def summary(results: list[Result]) -> str:
    passed = [r for r in results if r.ok]
    times = [r.seconds for r in results if not r.error]
    median = f", median {statistics.median(times):.1f}s" if times else ""
    by_ability: dict[str, list[bool]] = {}
    for r in results:
        by_ability.setdefault(r.case.ability, []).append(r.ok)
    parts = ", ".join(f"{a} {sum(v)}/{len(v)}" for a, v in sorted(by_ability.items()))
    return f"score {len(passed)}/{len(results)}{median} ({parts})"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m milo.eval", description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated case ids, e.g. c01,c12")
    parser.add_argument("--root", help="where the throwaway workspaces go (default: a new folder in /tmp)")
    parser.add_argument("--keep", action="store_true", help="keep the workspaces for a look afterwards")
    parser.add_argument("--chat-model", default="claude-sonnet-5-5")
    parser.add_argument("--worker-model", default="claude-sonnet-5-5")
    parser.add_argument("--timeout", type=float, default=CASE_TIMEOUT_S, help="seconds per case")
    args = parser.parse_args(argv)

    wanted = set(args.only.split(",")) if args.only else None
    cases = [c for c in CASES if wanted is None or c.id in wanted]
    root = Path(args.root) if args.root else Path(tempfile.mkdtemp(prefix="milo-eval-", dir="/tmp"))
    real_home = Path(os.environ.get("MILO_HOME", "~/Milo")).expanduser().resolve()
    if root.resolve() == real_home or real_home.is_relative_to(root.resolve()) or \
            not str(root.resolve()).startswith(("/tmp", "/private/tmp", "/var/folders", "/private/var/folders")):
        raise SystemExit(f"refusing to use {root}: the eval only runs in a throwaway folder under /tmp")
    root.mkdir(parents=True, exist_ok=True)
    print(f"eval in {root} with {len(cases)} case(s)", flush=True)
    results = asyncio.run(run(cases, root, chat_model=args.chat_model, worker_model=args.worker_model,
                              timeout_s=args.timeout))
    line = summary(results)
    print(line)
    (root / "results.json").write_text(json.dumps(
        [{"id": r.case.id, "ok": r.ok, "seconds": round(r.seconds, 1), "said": r.said, "questions": r.questions,
          "error": r.error} for r in results], indent=1, ensure_ascii=False))
    if not args.keep:
        for case in cases:
            shutil.rmtree(root / case.id, ignore_errors=True)
