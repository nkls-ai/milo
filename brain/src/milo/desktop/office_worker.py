"""Private, persistent JSONL Office actor. No Qt objects or arbitrary code entry points.

Only the three structured Office tools and their read-only descriptions are
accepted. The GUI owns this process and can kill it when Office displays a
modal dialog. One OfficeTools instance preserves target fingerprints between
describe and write. stdout is reserved exclusively for protocol responses.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import threading
from pathlib import Path

from milo import system
from milo.core.hands import validate

from ._office import OfficeTools, PortableOffice

TOOLS = frozenset(("sheet_write", "sheet_read", "write_document"))
MAX_LINE = 8 * 1024 * 1024


def handle(message: object, office: OfficeTools) -> dict:
    identity = message.get("id") if isinstance(message, dict) else None
    try:
        if not isinstance(message, dict) or set(message) != {"id", "operation", "tool", "args"}:
            raise ValueError("Invalid Office request envelope")
        if isinstance(identity, bool) or not isinstance(identity, int) or identity < 1:
            raise ValueError("Invalid Office request ID")
        operation, tool, args = message["operation"], message["tool"], message["args"]
        if operation not in ("describe", "run") or tool not in TOOLS or not isinstance(args, dict):
            raise ValueError("Unsupported Office operation")
        args = dict(args)
        locale = args.pop("locale", "")
        if not isinstance(locale, str) or len(locale) > 128:
            raise ValueError("Invalid Office locale")
        _, checked = validate(tool, args)
        checked["locale"] = locale
        result = office.describe(tool, checked) if operation == "describe" else office.run(tool, checked)
        if not isinstance(result, dict):
            raise ValueError("Invalid Office result")
        return {"id": identity, "ok": True, "result": result}
    except Exception as error:
        return {"id": identity, "ok": False, "error": str(error) or "Office couldn't complete the operation."}


def _watch_parent(stop: threading.Event) -> None:
    """The daemon does not keep the actor alive if the GUI disappears mid-COM call."""
    import psutil

    try:
        parent = psutil.Process(int(os.environ.get("MILO_OFFICE_PARENT_PID", os.getppid())))
        started = parent.create_time()
    except (psutil.Error, ValueError):
        # If the parent vanished before the watchdog started, a buffered COM
        # request must not become an unowned actor.
        try:
            system.signal_processes(os.getpid(), [], force=True)
        finally:
            os._exit(2)
    while not stop.wait(0.5):
        try:
            alive = parent.is_running() and parent.create_time() == started and parent.status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            alive = False
        if not alive:
            try:
                system.signal_processes(os.getpid(), [], force=True)
            finally:
                os._exit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        try:
            os.setsid()  # only this actor and its descendants belong to its killable group
        except OSError:
            pass
    stopped = threading.Event()
    threading.Thread(target=_watch_parent, args=(stopped,), name="office-parent", daemon=True).start()
    home = args.home.expanduser().resolve()
    office = OfficeTools(home, portable=PortableOffice(home, opener=lambda _path, _app: False))
    output = sys.stdout
    try:
        while raw := sys.stdin.buffer.readline(MAX_LINE + 1):
            if len(raw) > MAX_LINE:
                output.write(json.dumps({"id": None, "ok": False, "error": "Office request too large"}) + "\n")
                output.flush()
                return 1
            try:
                message = json.loads(raw)
                # A library's incidental print must never corrupt stdout JSONL.
                with contextlib.redirect_stdout(sys.stderr):
                    result = handle(message, office)
            except (ValueError, RecursionError):
                result = {"id": None, "ok": False, "error": "Invalid Office JSON"}
            output.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
            output.flush()
    finally:
        stopped.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
