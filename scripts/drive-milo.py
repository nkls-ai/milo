#!/usr/bin/env python3
"""Drive the running Milo like a user: type a message and see what he says and does, on the real Mac.

    scripts/drive-milo.py "open YouTube in Chrome"
    scripts/drive-milo.py "open YouTube in Chrome" --wait 12 --speak --answer yes

It connects to ~/Milo/run/brain.sock as an observer (the brain never sends it the app's requests, so the real app
opens, pastes and clicks), sends the text as a typed turn, and prints what comes back for --wait seconds: Milo's
words, questions, cards, steps and status lines, then which app is in front. --answer yes|no answers his
questions as a click would. Exits 1 if he asked anything and --answer wasn't given, so a check can fail on a
question that shouldn't have come.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain" / "src"))
from milo import system

SHOWN = {"bubble", "confirm", "confirm_done", "action_done", "status", "heard", "reply_delta", "activity"}


def front_app() -> str:
    if sys.platform == "win32":
        try:
            import win32gui
            import win32process
            import psutil
            _, pid = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
            return psutil.Process(pid).name()
        except Exception:
            return "unavailable"
    if sys.platform != "darwin":
        try:
            return subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True,
                                  text=True, timeout=2).stdout.strip() or "unavailable"
        except (OSError, subprocess.SubprocessError):
            return "unavailable"
    asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True).stdout.strip()
    info = subprocess.run(["lsappinfo", "info", "-only", "name", asn], capture_output=True, text=True).stdout
    return info.split("=", 1)[-1].strip().strip('"')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("text")
    parser.add_argument("--wait", type=float, default=10.0, help="seconds to watch after sending")
    parser.add_argument("--speak", action="store_true", help="let Milo speak the answer aloud")
    parser.add_argument("--answer", choices=("yes", "no"), help="answer his questions like a click")
    parser.add_argument("--home", type=Path, default=Path(os.environ.get("MILO_HOME", "~/Milo")).expanduser())
    args = parser.parse_args()

    sock = system.connect_local(args.home / "run" / "brain.sock", 3.0)
    sock.sendall(b'{"type": "observe"}\n')
    time.sleep(0.2)  # let the greeting pass
    sock.setblocking(False)
    _drain(sock)
    before = front_app()
    started = time.monotonic()
    sock.sendall((json.dumps({"type": "text", "text": args.text, "speak": args.speak}) + "\n").encode())
    asked = False
    buffer = b""
    deltas = ""
    while time.monotonic() - started < args.wait:
        ready, _, _ = select.select([sock], [], [], 0.2)
        if not ready:
            continue
        chunk = sock.recv(65536)
        if not chunk:
            break
        buffer += chunk
        *lines, buffer = buffer.split(b"\n")
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue  # the tail of the greeting
            kind = event.get("type")
            at = f"{time.monotonic() - started:5.2f}s"
            if kind == "reply_delta":
                deltas += event.get("text", "")
                continue
            if kind not in SHOWN:
                continue
            if kind == "activity":
                step = event.get("step") or {}
                print(f"{at} step: {step.get('title')} [{step.get('status')}]")
            elif kind == "confirm":
                asked = True
                print(f"{at} QUESTION: {event.get('question') or event.get('text')}")
                if args.answer:
                    sock.sendall((json.dumps({"type": "confirm_answer", "id": event["id"],
                                              "yes": args.answer == "yes"}) + "\n").encode())
                    print(f"{at}   answered {args.answer}")
            else:
                shown = {k: v for k, v in event.items() if k != "type" and v not in ("", None, [], {})}
                print(f"{at} {kind}: {json.dumps(shown, ensure_ascii=False)[:300]}")
    if deltas:
        print(f"said: {deltas.strip()[:400]}")
    print(f"front app: {before} -> {front_app()}")
    sock.close()
    return 1 if asked and not args.answer else 0


def _drain(sock: socket.socket) -> None:
    """Read the greeting until the socket has been quiet for a moment."""
    while select.select([sock], [], [], 0.3)[0]:
        if not sock.recv(65536):
            return


if __name__ == "__main__":
    sys.exit(main())
