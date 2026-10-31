"""Home Assistant over its REST API (ADR 0037). Works wherever the brain runs.

`[home.home_assistant]` names the `url` ("http://homeassistant.local:8123") and `key_ref`, the file in ~/Milo/secrets
that holds a long-lived access token (the user makes one under their Home Assistant profile, Security). The token is
read when Milo first needs it, so a missing one is said then, in plain words, not at start.

`GET /api/states` lists every entity; the ones Milo can switch become Devices. Rooms come from one
`POST /api/template` (Home Assistant's areas), cached for ten minutes; without it there are no rooms. Acting is
`POST /api/services/<domain>/<service>`, then `GET /api/states/<id>` for the state after it.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.home import Device
from milo.core.registry import HOMES, AdapterContext, options_from
from milo.core.secrets import SecretError, read_secret
from milo.core.types import ToolError

log = logging.getLogger("milo.home")

HTTP_TIMEOUT_S = 8.0
AREAS_S = 600.0
"""How long the rooms are kept before they are asked for again."""

Send = Callable[[str, str, dict, bytes | None], tuple[int, bytes]]
"""(method, url, headers, body) -> (status, body). urllib by default; tests pass a stub."""

_AREAS = ("{% set ns = namespace(out=[]) %}{% for s in states %}{% set a = area_name(s.entity_id) %}"
          "{% if a %}{% set ns.out = ns.out + [[s.entity_id, a]] %}{% endif %}{% endfor %}{{ ns.out | tojson }}")
"""Each entity with a room, as [[entity_id, area], ...]."""

_KINDS = {"light": "light", "switch": "switch", "input_boolean": "switch", "scene": "scene", "script": "scene",
          "climate": "climate", "fan": "fan", "cover": "cover", "lock": "lock", "alarm_control_panel": "alarm"}
"""The domains Milo switches, and the kind each is. A cover with device_class garage or gate is a garage."""
_DOES = {"light": ("on", "off", "toggle", "set"), "switch": ("on", "off", "toggle"), "scene": ("run",),
         "climate": ("on", "off", "set", "mode"), "fan": ("on", "off", "toggle", "set"),
         "cover": ("open", "close", "toggle", "set"), "garage": ("open", "close"), "lock": ("lock", "unlock"),
         "alarm": ("arm", "disarm")}
_ARM = ("away", "home", "night", "vacation")


@dataclass(frozen=True)
class HomeAssistantOptions:
    url: str = ""
    key_ref: str = "home_assistant.token"
    """The token's file in ~/Milo/secrets, or a path."""


class HomeAssistant:
    name = "Home Assistant"
    setup = "home_assistant"

    def __init__(self, url: str, key_file: Path, *, send: Send | None = None):
        self.url = url.rstrip("/")
        self._key_file = key_file
        self._send = send or _urllib
        self._areas: dict[str, str] = {}
        self._areas_at: float | None = None
        self._lock = threading.Lock()

    def devices(self) -> list[Device]:
        states = self._call("GET", "/api/states")
        if not isinstance(states, list):
            raise ToolError("Home Assistant sent something Milo can't read.")
        rooms = self._rooms()
        found = [_device(s, rooms) for s in states if isinstance(s, dict)]
        return [d for d in found if d is not None]

    def act(self, id: str, do: str, value: str = "") -> Device | None:
        domain = id.split(".", 1)[0]
        service, data = _service(domain, do, value)
        self._call("POST", f"/api/services/{domain}/{service}", {"entity_id": id, **data})
        try:
            now = self._call("GET", f"/api/states/{id}")
        except ToolError:
            return None
        return _device(now, self._areas) if isinstance(now, dict) else None

    # ---- HTTP

    def _rooms(self) -> dict[str, str]:
        with self._lock:
            if self._areas_at is not None and time.monotonic() - self._areas_at < AREAS_S:
                return self._areas
        try:
            pairs = self._call("POST", "/api/template", {"template": _AREAS}, raw=True)
            areas = {str(e): str(a) for e, a in json.loads(pairs)}
        except (ToolError, ValueError, TypeError) as e:
            log.info("no rooms from Home Assistant: %s", e)
            areas = {}
        with self._lock:
            self._areas, self._areas_at = areas, time.monotonic()
        return areas

    def _call(self, method: str, path: str, body: dict | None = None, *, raw: bool = False) -> Any:
        if not self.url:
            raise ToolError("Home Assistant has no address: put url under [home.home_assistant] in config.toml.")
        try:
            token = read_secret(self._key_file, "The Home Assistant token",
                                missing=f"Home Assistant needs a long-lived token, alone in {self._key_file}. Make "
                                        "one in Home Assistant under your profile, Security.")
        except SecretError as e:
            raise ToolError(str(e)) from None
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        status, data = self._send(method, self.url + path, headers,
                                  json.dumps(body).encode() if body is not None else None)
        if status == 401:
            raise ToolError("Home Assistant didn't take Milo's token. Make a new long-lived token and put it in "
                            f"{self._key_file}.")
        if status == 404:
            raise ToolError("Home Assistant doesn't know that one.")
        if status >= 400:
            text = data.decode("utf-8", "replace").strip()[:200]
            raise ToolError(f"Home Assistant said {status}" + (f": {text}" if text else "") + ".")
        text = data.decode("utf-8", "replace")
        if raw:
            return text
        try:
            return json.loads(text) if text.strip() else None
        except ValueError:
            raise ToolError("Home Assistant sent something Milo can't read.") from None


def _urllib(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""
    except (urllib.error.URLError, OSError, TimeoutError):
        raise ToolError(f"I couldn't reach Home Assistant at {url.split('/api/', 1)[0]}.") from None


def _device(s: Mapping[str, Any], rooms: Mapping[str, str]) -> Device | None:
    id = str(s.get("entity_id") or "")
    domain = id.split(".", 1)[0]
    kind = _KINDS.get(domain)
    if kind is None:
        return None
    attrs = s.get("attributes") if isinstance(s.get("attributes"), dict) else {}
    if kind == "cover" and attrs.get("device_class") in ("garage", "gate"):
        kind = "garage"
    state = str(s.get("state") or "")
    level = None
    if kind == "light" and isinstance(attrs.get("brightness"), (int, float)):
        level = round(attrs["brightness"] * 100 / 255)
    elif kind in ("cover", "garage") and isinstance(attrs.get("current_position"), (int, float)):
        level = float(attrs["current_position"])
    elif kind == "climate" and isinstance(attrs.get("temperature"), (int, float)):
        level = float(attrs["temperature"])
    elif kind == "fan" and isinstance(attrs.get("percentage"), (int, float)):
        level = float(attrs["percentage"])
    if kind in ("cover", "garage"):
        state = {"opening": "open", "closing": "closed"}.get(state, state)
    members = attrs.get("entity_id") if kind == "scene" and isinstance(attrs.get("entity_id"), list) else []
    return Device(id, str(attrs.get("friendly_name") or id.split(".", 1)[-1].replace("_", " ")), kind,
                  room=rooms.get(id, ""), state=state, level=level, does=_DOES[kind],
                  members=tuple(str(m) for m in members),
                  known=domain != "script" and (kind != "scene" or bool(members)))


def _service(domain: str, do: str, value: str) -> tuple[str, dict]:
    """The service for `do` on an entity of `domain`, and the data it takes besides the entity."""
    number = _number(value) if do == "set" else None
    match domain, do:
        case ("scene" | "script"), ("run" | "on"):
            return "turn_on", {}
        case "light", "set":
            return "turn_on", {"brightness_pct": max(0, min(100, round(number)))}
        case "climate", "set":
            return "set_temperature", {"temperature": number}
        case "climate", "mode":
            return "set_hvac_mode", {"hvac_mode": value}
        case "fan", "set":
            return "set_percentage", {"percentage": max(0, min(100, round(number)))}
        case "cover", "set":
            return "set_cover_position", {"position": max(0, min(100, round(number)))}
        case "cover", ("open" | "close"):
            return f"{do}_cover", {}
        case "cover", "toggle":
            return "toggle", {}
        case "lock", ("lock" | "unlock"):
            return do, {}
        case "alarm_control_panel", "arm":
            return f"alarm_arm_{value if value in _ARM else 'away'}", {}
        case "alarm_control_panel", "disarm":
            return "alarm_disarm", {}
        case ("light" | "switch" | "input_boolean" | "fan" | "climate"), ("on" | "off" | "toggle"):
            return {"on": "turn_on", "off": "turn_off", "toggle": "toggle"}[do], {}
    raise ToolError(f"Home Assistant can't {do} that.")


def _number(value: str) -> float:
    try:
        return float(value.replace(",", ".").strip())
    except ValueError:
        raise ToolError(f"{value!r} isn't a number.") from None


@HOMES.register("home_assistant")
def _home_assistant(options: Mapping[str, Any], ctx: AdapterContext) -> HomeAssistant:
    o = options_from(HomeAssistantOptions, options, "home.home_assistant")
    ref = Path(o.key_ref).expanduser()
    return HomeAssistant(o.url, ref if ref.is_absolute() else ctx.home / "secrets" / ref)
