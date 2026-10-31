"""The weather as the talker reads it in <today> (ADR 0038): a forecast, and its few short lines.

A `Weather` service (core/ports.py, adapters/weather/) returns a `Forecast`: a day per entry, with the sky as a WMO
weather code (the numbers every weather service uses), the low and the high, the chance of rain by the hour, and the
wind. `lines` turns it into what goes into the block: today and tomorrow with the rain's hours and the wind when it
is worth saying, then the next days in one short line each. It is numbers from a service, not text a person wrote,
so it doesn't make the conversation "outside".

The words are English like the rest of the block; the talker answers in the user's language.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .words.dates import long_date

SKY = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "heavy showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}
"""A word for each WMO weather code."""

UNITS = {"metric": ("°C", "km/h", "mm"), "imperial": ("°F", "mph", "in")}
WINDY = {"metric": (30.0, 50.0), "imperial": (19.0, 31.0)}
"""Wind and gusts from which a day says it is windy."""
RAIN_LIKELY = 40
"""An hour with at least this chance of rain counts in "rain 70%, mostly 14–18h"."""
RAIN_WORTH = 20
"""Below this chance, and with no rain to measure, the later days say nothing about rain."""
DAYS = 7


@dataclass(frozen=True)
class DayWeather:
    day: date
    code: int
    """The sky, as a WMO weather code (`SKY`)."""
    low: float
    high: float
    rain_chance: int = 0
    """The day's highest chance of rain, in percent."""
    rain: float = 0.0
    """How much falls, rain and snow, in mm or inches."""
    wind: float = 0.0
    """The strongest wind, in the forecast's unit (km/h or mph)."""
    gusts: float = 0.0
    hourly_rain: tuple[int, ...] = ()
    """The chance of rain for each hour, 0 to 23, when the service gave it."""


@dataclass(frozen=True)
class Forecast:
    place: str
    """Where it is for, as the service named it ("Berlin")."""
    units: str
    """"metric" (°C, km/h) or "imperial" (°F, mph)."""
    days: tuple[DayWeather, ...]
    now: float | None = None
    """The temperature now."""
    now_code: int | None = None


def lines(forecast: Forecast, now: datetime, *, place: str = "") -> list[str]:
    """The forecast for <today>, from `now`'s day on; [] when it has no day left. `place` is how it is named."""
    degree, speed, _ = UNITS.get(forecast.units, UNITS["metric"])
    today = now.date()
    days = [d for d in forecast.days if d.day >= today]
    if not days:
        return []
    out = [f"Weather in {place or forecast.place} ({degree}, {speed}):"]
    if forecast.now is not None and forecast.days[0].day == today:  # read today: "now" still means now
        sky = SKY.get(forecast.now_code, "") if forecast.now_code is not None else ""
        out.append(f"- Now: {_deg(forecast.now)}{degree}" + (f", {sky}" if sky else "") + ".")
    tomorrow = today + timedelta(days=1)
    for d in days:
        if d.day == today:
            out.append(f"- Today: {_day(d, forecast.units, from_hour=now.hour)}.")
        elif d.day == tomorrow:
            out.append(f"- Tomorrow, {long_date(d.day, short=True)}: {_day(d, forecast.units)}.")
        else:
            out.append(f"- {long_date(d.day, short=True)}: {_short(d, forecast.units)}.")
    return out


def _day(d: DayWeather, units: str, *, from_hour: int = 0) -> str:
    """Today or tomorrow: the range, the sky, the chance of rain (today's from now on) and roughly when, how much
    falls, and the wind if it is notable."""
    degree, speed, amount = UNITS.get(units, UNITS["metric"])
    parts = [f"{_deg(d.low)}–{_deg(d.high)}{degree}", SKY.get(d.code, "")]
    hours = d.hourly_rain[from_hour:] if len(d.hourly_rain) == 24 else ()
    chance = max(hours) if hours else d.rain_chance
    likely = [from_hour + i for i, p in enumerate(hours) if p >= RAIN_LIKELY]
    when = ""
    if likely and (likely[0] > from_hour or likely[-1] < 23):  # not all day
        when = f", mostly {likely[0]:02d}–{likely[-1] + 1:02d}h"
    parts.append(f"rain chance {chance}%{when}")
    places = 2 if units == "imperial" else 1
    if round(d.rain, places):
        parts.append(f"{d.rain:.{places}f} {amount} in all")
    wind, gusts = WINDY.get(units, WINDY["metric"])
    if d.wind >= wind or d.gusts >= gusts:
        parts.append(f"windy, gusts up to {round(max(d.gusts, d.wind))} {speed}")
    return ", ".join(p for p in parts if p)


def _short(d: DayWeather, units: str) -> str:
    degree = UNITS.get(units, UNITS["metric"])[0]
    parts = [f"{_deg(d.low)}–{_deg(d.high)}{degree}", SKY.get(d.code, "")]
    if d.rain_chance >= RAIN_WORTH:
        parts.append(f"rain chance {d.rain_chance}%")
    return ", ".join(p for p in parts if p)


def _deg(value: float) -> str:
    return str(round(value))


def city_of_zone(zone: str) -> str:
    """The city an IANA time zone is named after: "Europe/Berlin" → "Berlin", "America/New_York" → "New York",
    "America/Argentina/Buenos_Aires" → "Buenos Aires". "" for a zone that names no city ("UTC", "Etc/GMT+1")."""
    zone = zone.strip()
    if "/" not in zone or zone.split("/")[0] in ("Etc", "SystemV", "US", "Canada", "Brazil", "Chile", "Mexico"):
        return ""
    return zone.rsplit("/", 1)[1].replace("_", " ")
