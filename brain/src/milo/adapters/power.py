"""Whether the Mac runs on the power adapter, from `pmset -g batt`. A Mac without a battery always does."""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)


def on_ac_power() -> bool:
    try:
        out = subprocess.run(["/usr/bin/pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("could not ask pmset about power: %s", e)
        return False
    return "AC Power" in out or "InternalBattery" not in out
