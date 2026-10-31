"""The name of the system's time zone ("Europe/Berlin"), so the weather needs no location permission (ADR 0038).

macOS and Linux point /etc/localtime at a file under a `zoneinfo` folder; TZ overrides it. Windows names its zones
differently ("W. Europe Standard Time"); it gets "" until the brain runs there, and the weather then needs
`[weather] place`.
"""

from __future__ import annotations

import os
import re

_ZONE = re.compile(r"zoneinfo/(.+)$")


def zone_name() -> str:
    """"Europe/Berlin", or "" when it can't be told."""
    tz = os.environ.get("TZ", "").lstrip(":")
    if "/" in tz and not tz.startswith("/"):
        return tz
    try:
        target = os.path.realpath(tz or "/etc/localtime")
    except OSError:
        return ""
    m = _ZONE.search(target)
    if m:
        return m[1]
    try:
        with open("/etc/timezone", encoding="utf-8") as f:  # older Debian and Ubuntu
            return f.read().strip()
    except OSError:
        return ""
