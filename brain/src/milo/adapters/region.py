"""The user's region setting, for money formats in spreadsheets: a locale id like "en_US@rg=dezzzz" or "de_DE".

On a Mac it is the AppleLocale default, which keeps the region apart from the language ("en_US@rg=dezzzz":
English, but the money of Germany). Elsewhere it is the POSIX locale of money, LC_MONETARY, without its
encoding. Windows' GetUserDefaultLocaleName would go here once the brain runs there.
"""

from __future__ import annotations

import os
import subprocess
import sys


def region() -> str:
    """The region as a locale id. "" if it can't be read."""
    if sys.platform == "darwin":
        return _apple_locale()
    for name in ("LC_ALL", "LC_MONETARY", "LANG"):
        value = os.environ.get(name, "")
        if value and value not in ("C", "POSIX"):
            return value.split(".")[0]
    return ""


def _apple_locale() -> str:
    try:
        done = subprocess.run(["/usr/bin/defaults", "read", "-g", "AppleLocale"], capture_output=True, text=True,
                              timeout=5, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip()
