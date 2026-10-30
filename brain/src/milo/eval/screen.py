"""On-screen eval: real computer-use tasks on the real Mac, timed end to end. Run on demand, never in pytest.

    uv run python -m milo.eval.screen --app ../build/Milo.app [--only excel,numbers,file,mail]

It starts a second Milo.app on a throwaway workspace in /tmp (no microphone, no voice, files limited to a
folder in that workspace), types each request the way the Milo window does, and watches the task: when Milo
first answered, when the worker started, every step with its time, and when the task was done. Then it checks
the result and asks Milo to clean up (close what he opened without saving, delete the test draft).

It uses the real screen, Excel, Numbers and Mail, so run it only while nobody is using the Mac. It never sends
mail: the mail case writes a draft and deletes it again. None of the tasks should need a question; any
question is counted and answered no. During cleanup the runner says yes only to closing without saving, quitting or
deleting in the case's own apps (`_cleanup_answer`), and no to everything else.

The eval starts the brain itself, so Apple's Automation permission for Mail (and the other apps) is checked
against the terminal that runs it, not Milo. Allow it there first, or macOS asks in the middle of a case.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..services import sheets
from .runner import _connect, _stop

CASE_TIMEOUT_S = 300.0
QUIET_S = 3.0
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

CONFIG = """\
[chat]
use = "claude_live"

[chat.claude_live]
model = "{chat_model}"
effort = "low"

[harness]
use = "{harness}"

[harness.codex]
reasoning_effort = "low"
timeout_s = {timeout}

[harness.claude]
model = "{worker_model}"
timeout_s = {timeout}

[connections]
use = "mac"
calendar = false
reminders = false
notes = false
shortcuts = false
mail = true
files = true

[connections.mac]
files_scope = "{files}"

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
enabled = true
"""


@dataclass
class Step:
    title: str
    detail: str
    status: str
    started: float
    finished: float | None = None


@dataclass
class Run:
    """What one request looked like from the outside."""

    replies: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    steps: dict[str, Step] = field(default_factory=dict)
    task_status: str = ""
    task_result: str = ""
    first_reply_s: float | None = None
    task_started_s: float | None = None
    task_done_s: float | None = None
    seconds: float = 0.0
    error: str = ""

    def step_list(self) -> list[Step]:
        return sorted(self.steps.values(), key=lambda s: s.started)


@dataclass(frozen=True)
class ScreenCase:
    id: str
    say: Callable[[Path], str]
    check: Callable[[Run, Path], tuple[bool, str]]
    cleanup: str = ""
    apps: tuple[str, ...] = ()
    """The apps cleanup may close, quit or delete in."""
    setup: Callable[[Path], None] = lambda files: None


def _values(args: dict) -> dict[tuple[int, int], float]:
    """The numbers a sheet_write call puts on the sheet, by (column, row), formulas worked out like the app would."""
    first = str(args.get("start") or "A1").upper()
    col0, row0 = sheets.cell(first)
    raw = {(col0 + j, row0 + i): c for i, r in enumerate(args.get("rows") or []) for j, c in enumerate(r)}
    done: dict[tuple[int, int], float | None] = {}

    def value(at: tuple[int, int], depth: int = 0) -> float | None:
        if at not in done:
            done[at] = None
            done[at] = _amount(raw.get(at), lambda ref: value(sheets.cell(ref), depth + 1)) if depth < 50 else None
        return done[at]

    return {at: v for at in raw if (v := value(at)) is not None}


def _amount(cell: object, lookup: Callable[[str], float | None]) -> float | None:
    """A number, or what a formula of numbers, cell references, + - * /, SUM and ROUND comes to."""
    if isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    if not isinstance(cell, str) or not cell.startswith("="):
        return None
    expr = cell[1:].upper().replace(";", ",").replace("$", "")

    def total(m: re.Match) -> str:
        (c1, r1), (c2, r2) = sheets.cell(m[1]), sheets.cell(m[2])
        found = [lookup(f"{sheets.column_letters(c)}{r}") for c in range(c1, c2 + 1) for r in range(r1, r2 + 1)]
        return repr(sum(v for v in found if v is not None))

    try:
        expr = re.sub(r"\b([A-Z]{1,3}\d+):([A-Z]{1,3}\d+)\b", lambda m: f"[{total(m)}]", expr)
        expr = re.sub(r"\b[A-Z]{1,3}\d+\b", lambda m: repr(lookup(m[0]) or 0.0), expr)
    except Exception:
        return None
    expr = expr.replace("SUM(", "_sum(").replace("ROUND(", "round(").replace("[", "(").replace("]", ")")
    if not re.fullmatch(r"(_sum\(|round\(|[\d.eE+\-*/(), ])*", expr):
        return None
    try:
        tree = ast.parse(expr, mode="eval")
        return float(eval(compile(tree, "<formula>", "eval"),
                          {"__builtins__": {}, "round": round, "_sum": lambda *a: sum(a)}))
    except (SyntaxError, ArithmeticError, TypeError, ValueError):
        return None


def _check_table(app: str) -> Callable[[Run, Path], tuple[bool, str]]:
    def check(run: Run, files: Path) -> tuple[bool, str]:
        writes = [s for s in run.step_list() if s.detail.startswith("sheet_write ") and s.status == "done"]
        if not writes:
            used = ", ".join(s.title for s in run.step_list()) or "no steps"
            return False, f"no finished sheet_write ({used})"
        args = [json.loads(s.detail.removeprefix("sheet_write ")) for s in writes]
        if any(a.get("app") != app for a in args):
            return False, f"wrote into {', '.join(a.get('app', '?') for a in args)}, not {app}"
        cells = [c for a in args for row in a["rows"] for c in row]
        text = " ".join(str(c) for c in cells).lower()
        values = [v for a in args for v in _values(a).values()]
        missing = [d for d in WEEKDAYS if d not in text]
        if missing:
            return False, f"no row for {', '.join(missing)}"
        if "budget" not in text:
            return False, "no Budget column"
        days = [v for v in values if abs(v - 1500) > 0.01]
        if abs(sum(days) - 1500) > 1.0:
            return False, f"the daily amounts add up to {sum(days):.2f}, not 1500"
        if not any(abs(v - 1500) <= 0.01 for v in values):
            return False, "no total"
        if run.questions:
            return False, f"asked {run.questions}"
        return True, f"{len(writes)} sheet_write call(s)"
    return check


def _setup_files(files: Path) -> None:
    downloads = files / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    stamps = {"Kontoauszug August.pdf": 1_790_000_000, "Rechnung Stadtwerke Oktober.pdf": 1_790_900_000,
              "Einkaufsliste.txt": 1_791_000_000}
    for name, stamp in stamps.items():
        path = downloads / name
        if name.endswith(".pdf"):
            path.write_bytes(_pdf(name.removesuffix(".pdf")))
        else:
            path.write_text("Milch, Brot\n")
        os.utime(path, (stamp, stamp))


def _pdf(title: str) -> bytes:
    """A tiny valid one-page PDF with `title` on it."""
    text = title.replace("(", "").replace(")", "")
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def _check_filed(run: Run, files: Path) -> tuple[bool, str]:
    filed = files / "Invoices" / "Rechnung Stadtwerke Oktober.pdf"
    if not filed.exists():
        return False, "the PDF isn't in Invoices"
    if (files / "Downloads" / "Rechnung Stadtwerke Oktober.pdf").exists():
        return False, "the PDF is still in Downloads too"
    if not (files / "Downloads" / "Kontoauszug August.pdf").exists():
        return False, "the older PDF moved as well"
    if run.questions:
        return False, f"asked {run.questions}"
    return True, "filed"


def _check_draft(run: Run, files: Path) -> tuple[bool, str]:
    drafts = [s for s in run.step_list() if s.title.startswith(("Writing a reply", "Writing a draft"))]
    if not any(s.status == "done" for s in drafts):
        return False, f"no draft written ({', '.join(s.title for s in run.step_list()) or 'no steps'})"
    if any("send" in q.lower() and "until you send" not in q.lower() for q in run.questions):
        return False, f"asked to send: {run.questions}"
    return True, drafts[-1].title


CASES = (
    ScreenCase("excel", lambda f: "Open Excel and make a table with a row for each day of the week, a Budget column, "
               "1500 split over the days, and a total.", _check_table("Microsoft Excel"),
               "Close the Excel workbook you just made without saving it. If Excel has no other workbook open, "
               "quit Excel without saving.", apps=("Microsoft Excel",)),
    ScreenCase("numbers", lambda f: "Open Numbers and make a table with a row for each day of the week, a Budget "
               "column, 1500 split over the days, and a total.", _check_table("Numbers"),
               "Close the Numbers document you just made without saving it. If Numbers has no other document "
               "open, quit Numbers without saving.", apps=("Numbers",)),
    ScreenCase("file", lambda f: f"File the newest PDF in my Downloads folder ({f}/Downloads) into a folder called "
               f"Invoices in {f}.", _check_filed, setup=_setup_files),
    ScreenCase("mail", lambda f: "Write a reply to the newest email in my inbox saying thanks, I'll get back to you "
               "tomorrow. Just make the draft.", _check_draft,
               "Delete the reply draft you just made in Mail; it was only a test. Don't send anything.",
               apps=("Mail",)),
)


async def converse(reader, writer, text: str, *, cleanup: tuple[str, ...] | None = None,
                   timeout_s: float = CASE_TIMEOUT_S) -> Run:
    """Type `text` to Milo and follow the turn and its task until things are quiet."""
    run = Run()
    writer.write((json.dumps({"type": "text", "text": text, "speak": False}) + "\n").encode())
    await writer.drain()
    started = last = time.monotonic()
    replied = asked = False
    running: set[str] = set()
    tasks: set[str] = set()
    while True:
        now = time.monotonic()
        if now - started > timeout_s:
            run.error = "timed out"
            break
        if replied and not running and not asked and now - last >= QUIET_S:
            break
        try:
            line = await asyncio.wait_for(reader.readline(), 0.25)
        except TimeoutError:
            continue
        if not line:
            run.error = "the brain went away"
            break
        event = json.loads(line)
        kind = event["type"]
        if kind in ("level", "state", "emotion"):
            continue
        last = now = time.monotonic()
        if kind == "entry":
            entry = event["entry"]
            if entry["kind"] == "milo" and entry.get("done"):
                replied = True
                run.replies.append(entry.get("text", ""))
                if run.first_reply_s is None:
                    run.first_reply_s = now - started
            elif entry["kind"] == "task":
                tasks.add(entry["id"])
                if entry.get("status") == "running":
                    running.add(entry["id"])
                    if run.task_started_s is None:
                        run.task_started_s = now - started
                else:
                    running.discard(entry["id"])
                    run.task_status, run.task_result = entry.get("status", ""), entry.get("result", "")
                    run.task_done_s = now - started
                    replied = True
        elif kind == "activity":
            step = event["step"]
            known = run.steps.get(step["id"])
            if known is None:
                run.steps[step["id"]] = Step(step["title"], step.get("detail", ""), step["status"], now - started)
            else:
                known.title, known.status = step["title"], step["status"]
                known.detail = step.get("detail", "") or known.detail
            if step["status"] != "running":
                run.steps[step["id"]].finished = now - started
        elif kind == "confirm":
            run.questions.append(event["question"])
            asked = True
            yes = cleanup is not None and _cleanup_answer(cleanup, event["question"], run)
            writer.write((json.dumps({"type": "confirm_answer", "id": event["id"], "yes": yes}) + "\n").encode())
            await writer.drain()
        elif kind == "confirm_done":
            asked = False
    run.seconds = time.monotonic() - started
    return run


# During cleanup the runner says yes only to these, in the case's own apps; everything else is a no.
_CLEANUP_SCRIPT_BAD = re.compile(r"\b(send|forward|share|reply|redirect|do shell script|keystroke|key code|"
                                 r"save in|make new|set content|password|keychain)\b", re.IGNORECASE)
_CLEANUP_QUESTION_BAD = re.compile(r"\b(send|forward|share|redirect|trash|empty|password|keychain)\b",
                                   re.IGNORECASE)
_CLEANUP_SCRIPT_GOOD = re.compile(r"\b(close\b.*\bsaving no|quit|delete)\b", re.IGNORECASE)


def _cleanup_answer(apps: tuple[str, ...], question: str, run: Run) -> bool:
    """Yes only for closing without saving, quitting, or deleting, in `apps`, and only what the step shows."""
    named = "|".join(re.escape(a) for a in apps)
    if not named:
        return False
    if re.fullmatch(rf"May I use ({named}) for this\? You'll see each step\.", question):
        return True  # the careful gate; every step after it is checked on its own
    # The chat model starting the cleanup task; again every step inside is checked on its own.
    short = "|".join(re.escape(a.split()[-1]) for a in apps)
    if not _CLEANUP_QUESTION_BAD.search(question) and (
            re.fullmatch(rf"(Close|Quit) the [^?]*\b({named}|{short})\b[^?]* without saving( it)?\?", question)
            or ("Mail" in apps and re.fullmatch(r"Delete the (reply |test )?draft[^?]*\?", question))):
        return True
    if re.fullmatch(rf"I'm about to click “(Delete|Don['’]t Save)” in ({named})\. Go ahead\?", question):
        return True
    if not re.fullmatch(rf"Run a script in ({named})\? It's in my window\.", question):
        return False
    waiting = [s for s in run.step_list() if s.status == "running"]
    script = waiting[-1].detail if waiting else ""
    told = set(re.findall(r'tell application "([^"]+)"', script))
    return (bool(script) and told <= set(apps) and bool(_CLEANUP_SCRIPT_GOOD.search(script))
            and not _CLEANUP_SCRIPT_BAD.search(script))


def report(case: ScreenCase, run: Run, ok: bool, note: str) -> str:
    def t(value: float | None) -> str:
        return f"{value:5.1f}s" if value is not None else "   - "

    lines = [f"{case.id:8} {'PASS' if ok else 'FAIL'}  total {run.seconds:5.1f}s  first reply {t(run.first_reply_s)}"
             f"  task start {t(run.task_started_s)}  task done {t(run.task_done_s)}  {note}"]
    for step in run.step_list():
        took = f"{step.finished - step.started:4.1f}s" if step.finished is not None else "  ?  "
        lines.append(f"           {t(step.started)} +{took} {step.status:7} {step.title}")
    if run.questions:
        lines.append(f"           questions: {run.questions}")
    if run.task_result:
        lines.append(f"           said: {run.task_result[:300]}")
    return "\n".join(lines)


async def _start_brain(home: Path) -> asyncio.subprocess.Process:
    """The brain runs from this checkout with this Python, like `uv run milo` by hand; the app then connects to it
    instead of starting its own (which would install the voice extras)."""
    (home / "logs").mkdir(exist_ok=True)
    stderr = open(home / "logs" / "brain.stderr", "wb")
    return await asyncio.create_subprocess_exec(
        sys.executable, "-m", "milo.server", env={**os.environ, "MILO_HOME": str(home)},
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=stderr, start_new_session=True)


def _launch(app: Path, home: Path) -> None:
    subprocess.run(["open", "-n", "-g", str(app), "--env", f"MILO_HOME={home}"], check=True)


def _quit(app: Path) -> None:
    """Stop the test app. Only this build's Milo.app is touched, never the user's own."""
    for pid in _app_pids(app):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


async def run_all(cases: list[ScreenCase], app: Path, home: Path, files: Path) -> list[tuple[str, bool, Run]]:
    brain = await _start_brain(home)
    results = []
    try:
        reader, writer = await _connect(home / "run" / "brain.sock")
        _launch(app, home)
        await _wait_for_app(app)
        for case in cases:
            case.setup(files)
            run = await converse(reader, writer, case.say(files))
            try:
                ok, note = case.check(run, files)
            except Exception as e:
                ok, note = False, f"check failed: {e}"
            if run.error:
                ok, note = False, f"{run.error}; {note}"
            print(report(case, run, ok, note), flush=True)
            results.append((case.id, ok, run))
            if case.cleanup:
                tidy = await converse(reader, writer, case.cleanup, cleanup=case.apps)
                print(f"           cleanup {tidy.seconds:.1f}s: {tidy.task_result[:200] or tidy.replies[-1:]}",
                      flush=True)
        writer.close()
    finally:
        _quit(app)
        await _stop(brain)
    return results


async def _wait_for_app(app: Path, timeout_s: float = 30) -> None:
    """Wait for the test app's process, then give it a moment to connect to the brain."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and not _app_pids(app):
        await asyncio.sleep(0.5)
    await asyncio.sleep(4)


def _app_pids(app: Path) -> list[int]:
    binary = str(app / "Contents" / "MacOS" / "Milo")
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    return [int(pid) for pid, _, command in (line.strip().partition(" ") for line in out.splitlines())
            if command.startswith(binary)]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m milo.eval.screen", description=__doc__.splitlines()[0])
    parser.add_argument("--app", default=str(Path(__file__).resolve().parents[4] / "build" / "Milo.app"),
                        help="the Milo.app to start (default: the checkout's build/Milo.app)")
    parser.add_argument("--only", help="comma-separated case ids: excel, numbers, file, mail")
    parser.add_argument("--harness", default="codex", choices=("codex", "claude"))
    parser.add_argument("--chat-model", default="claude-sonnet-5-5")
    parser.add_argument("--worker-model", default="claude-sonnet-5-5", help="for --harness claude")
    parser.add_argument("--keep", action="store_true", help="keep the workspace for a look afterwards")
    args = parser.parse_args(argv)
    app = Path(args.app).resolve()
    if not (app / "Contents" / "MacOS" / "Milo").exists():
        raise SystemExit(f"no Milo.app at {app}; build it with scripts/build-app.sh")
    wanted = set(args.only.split(",")) if args.only else None
    cases = [c for c in CASES if wanted is None or c.id in wanted]
    home = Path(tempfile.mkdtemp(prefix="milo-screen-", dir="/tmp"))
    files = home / "files"
    files.mkdir()
    (home / "config.toml").write_text(CONFIG.format(chat_model=args.chat_model, harness=args.harness,
                                                    worker_model=args.worker_model, files=files,
                                                    timeout=int(CASE_TIMEOUT_S)))
    print(f"on-screen eval in {home} with {len(cases)} case(s), worker {args.harness}", flush=True)
    results = asyncio.run(run_all(cases, app, home, files))
    passed = sum(ok for _, ok, _ in results)
    times = ", ".join(f"{cid} {run.seconds:.1f}s" for cid, _, run in results)
    print(f"score {passed}/{len(results)} ({times})")
    (home / "results.json").write_text(json.dumps(
        [{"id": cid, "ok": ok, "seconds": round(run.seconds, 1), "first_reply_s": run.first_reply_s,
          "task_started_s": run.task_started_s, "task_done_s": run.task_done_s, "questions": run.questions,
          "said": run.task_result, "steps": [vars(s) for s in run.step_list()]} for cid, ok, run in results],
        indent=1, ensure_ascii=False))
    if not args.keep:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
