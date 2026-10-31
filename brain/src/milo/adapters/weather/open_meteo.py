"""Open-Meteo: a free forecast with no key and no account (open-meteo.com).

Two requests: its geocoding API turns the place's name into a position once (kept for the run), then the forecast
API gives the days, the hourly chance of rain and the weather now. Standard library only (urllib on the brain's
thread for it). The place's name and its position go to Open-Meteo; nothing else does.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from milo.core.registry import WEATHER, AdapterContext, options_from
from milo.core.types import ToolError
from milo.core.weather import DayWeather, Forecast

log = logging.getLogger("milo.weather")

GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
DAILY = ("weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max",
         "precipitation_sum", "wind_speed_10m_max", "wind_gusts_10m_max")
_POSITION = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")

Fetch = Callable[[str, float], Any]
"""GET a URL with a timeout and return its JSON. Raises OSError or ValueError."""


@dataclass(frozen=True)
class OpenMeteoOptions:
    timeout_s: float = 10.0


class OpenMeteo:
    """`fetch` does the HTTP (tests pass a stub)."""

    def __init__(self, *, timeout_s: float = 10.0, fetch: Fetch | None = None):
        self._timeout_s = timeout_s
        self._fetch = fetch or _get_json
        self._places: dict[str, tuple[float, float, str]] = {}

    def forecast(self, place: str, days: int, units: str) -> Forecast:
        lat, lon, name = self._locate(place)
        imperial = units == "imperial"
        query = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "timezone": "auto",
                 "forecast_days": max(1, min(days, 16)), "daily": ",".join(DAILY),
                 "hourly": "precipitation_probability", "current": "temperature_2m,weather_code",
                 "temperature_unit": "fahrenheit" if imperial else "celsius",
                 "wind_speed_unit": "mph" if imperial else "kmh", "precipitation_unit": "inch" if imperial else "mm"}
        data = self._get(f"{FORECAST}?{urllib.parse.urlencode(query)}")
        try:
            return _forecast(data, name, "imperial" if imperial else "metric")
        except (KeyError, TypeError, ValueError, IndexError) as e:
            raise ToolError(f"Open-Meteo sent a forecast I can't read ({type(e).__name__})") from None

    def _locate(self, place: str) -> tuple[float, float, str]:
        """The place's position and its name, from "Berlin", "Berlin, Germany" or "52.52,13.41"."""
        key = " ".join(place.split()).casefold()
        if key in self._places:
            return self._places[key]
        if m := _POSITION.match(place):
            found = (float(m[1]), float(m[2]), place.strip())
        else:
            # The search knows names, not "Berlin, Germany": the part after the comma picks among them.
            name, _, within = (p.strip() for p in place.partition(","))
            if not name:
                raise ToolError("no place is set for the weather")
            data = self._get(f"{GEOCODING}?{urllib.parse.urlencode({'name': name, 'count': 10, 'format': 'json'})}")
            results = [r for r in (data.get("results") or []) if isinstance(r, dict)]
            if within:
                results = [r for r in results if within.casefold() in
                           " ".join(str(r.get(k, "")) for k in ("country", "country_code", "admin1")).casefold()] \
                          or results
            if not results:
                raise ToolError(f"Open-Meteo doesn't know the place {place!r}")
            r = results[0]
            found = (float(r["latitude"]), float(r["longitude"]), str(r.get("name") or name))
        self._places[key] = found
        return found

    def _get(self, url: str) -> dict:
        try:
            data = self._fetch(url, self._timeout_s)
        except (OSError, ValueError) as e:
            raise ToolError(f"Open-Meteo can't be reached ({type(e).__name__})") from None
        if not isinstance(data, dict) or data.get("error"):
            raise ToolError(f"Open-Meteo said no: {str((data or {}).get('reason', ''))[:100]}"
                            if isinstance(data, dict) else "Open-Meteo sent something I can't read")
        return data


def _forecast(data: dict, place: str, units: str) -> Forecast:
    daily = data["daily"]
    hourly: dict[str, list[int]] = {}
    hours = data.get("hourly") or {}
    for at, chance in zip(hours.get("time") or [], hours.get("precipitation_probability") or []):
        hourly.setdefault(str(at)[:10], []).append(int(chance or 0))
    days = []
    for i, day in enumerate(daily["time"]):
        if daily["temperature_2m_max"][i] is None:
            continue  # the service has no forecast that far
        rain = hourly.get(day, [])
        days.append(DayWeather(
            date.fromisoformat(day), int(daily["weather_code"][i] or 0), float(daily["temperature_2m_min"][i]),
            float(daily["temperature_2m_max"][i]), int(_at(daily, "precipitation_probability_max", i)),
            float(_at(daily, "precipitation_sum", i)), float(_at(daily, "wind_speed_10m_max", i)), float(_at(daily, "wind_gusts_10m_max", i)),
            tuple(rain) if len(rain) == 24 else ()))
    current = data.get("current") or {}
    now = current.get("temperature_2m")
    code = current.get("weather_code")
    return Forecast(place, units, tuple(days), float(now) if now is not None else None,
                    int(code) if code is not None else None)


def _at(table: dict, key: str, i: int) -> float:
    values = table.get(key) or []
    return (values[i] if i < len(values) else None) or 0


def _get_json(url: str, timeout_s: float) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "Milo"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - fixed https URL
        return json.loads(response.read(1_000_000).decode("utf-8"))


@WEATHER.register("open_meteo")
def _open_meteo(options: Mapping[str, Any], ctx: AdapterContext) -> OpenMeteo:
    o = options_from(OpenMeteoOptions, options, "weather.open_meteo")
    return OpenMeteo(timeout_s=o.timeout_s)
