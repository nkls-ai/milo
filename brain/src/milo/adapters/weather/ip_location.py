"""Roughly where the computer is, from its internet address, for the weather when `[weather] place` is empty
(ADR 0038). ipinfo.io: free, no key, HTTPS.

An address often belongs to the provider's nearest hub, so this can be tens of kilometres off (a university network
near Osnabrück shows Münster): close enough for a forecast, never used for anything else. The request carries the
computer's address, as every request does; nothing else goes. Standard library only.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from collections.abc import Callable
from typing import Any

log = logging.getLogger("milo.weather")

URL = "https://ipinfo.io/json"
_POSITION = re.compile(r"^\s*-?\d{1,2}(\.\d+)?\s*,\s*-?\d{1,3}(\.\d+)?\s*$")

Fetch = Callable[[str, float], Any]


def ip_place(timeout_s: float = 5.0, fetch: Fetch | None = None) -> tuple[str, str]:
    """(the city's name, "lat,lon"), or ("", "") when it can't be told. Never raises."""
    try:
        data = (fetch or _get_json)(URL, timeout_s)
    except (OSError, ValueError) as e:
        log.info("couldn't tell the place from the internet address: %s", e)
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    at = str(data.get("loc") or "")
    if not _POSITION.match(at):
        return "", ""
    city = " ".join(str(data.get("city") or "").split())[:60]
    return city, at.replace(" ", "")


def _get_json(url: str, timeout_s: float) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "Milo", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - fixed https URL
        return json.loads(response.read(100_000).decode("utf-8"))
