"""Run AppleScript with its inputs as arguments (`on run argv`), never pasted into the script's source."""

from __future__ import annotations

import subprocess

from milo.core.types import ToolError

TIMEOUT_S = 90  # the first call waits for the user to answer macOS's Automation prompt
US, RS = "\x1f", "\x1e"  # field and record separators the scripts put between values

NOT_ALLOWED = ("Milo isn't allowed to use {app} yet. Allow it in System Settings › Privacy & Security › "
               "Automation, then ask again.")


def run(script: str, *args: str, app: str, timeout_s: float = TIMEOUT_S) -> str:
    """stdout of the script. Raises ToolError in plain words."""
    try:
        done = subprocess.run(["osascript", "-", *args], input=script, capture_output=True, text=True,
                              timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise ToolError(f"{app} didn't answer in time.") from None
    except OSError:
        raise ToolError(f"I couldn't reach {app}.") from None
    if done.returncode != 0:
        err = done.stderr
        if "-1743" in err or "Not authorized" in err:
            raise ToolError(NOT_ALLOWED.format(app=app))
        if "4040" in err:
            raise ToolError(f"I couldn't find that in {app} any more.")
        if "4041" in err:
            raise ToolError(err.split("execution error:")[-1].split("(4041)")[0].strip())
        raise ToolError(f"{app} didn't do what I asked.")
    return done.stdout.rstrip("\n")


def records(out: str) -> list[list[str]]:
    return [r.split(US) for r in out.split(RS) if r.strip()]
