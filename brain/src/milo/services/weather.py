"""The forecast for <today> (ADR 0038), read from the weather service at most every `refresh_s` and kept.

"Do I need an umbrella tomorrow?" is answered by the talker from the block, with no tool call. `Today` asks for a
refresh when the user starts talking (`soon`) and renders `lines()`; the fetch runs on a thread, so a slow service
never holds a turn up for more than the block's own wait. When it fails Milo logs it, keeps the last forecast for
a while (`STALE_S`), tries again after `retry_s`, and otherwise leaves the weather out without a word.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from milo.core.ports import Clock, Weather
from milo.core.types import ToolError
from milo.core.weather import DAYS, Forecast, lines

log = logging.getLogger("milo.weather")

REFRESH_S = 45 * 60.0
RETRY_S = 10 * 60.0
STALE_S = 6 * 3600.0
"""A forecast older than this is left out rather than told as if it were new."""


class WeatherReport:
    """`weather` is the service, `place` the config's place, `units` "metric" or "imperial". Without a place,
    `locate` tells roughly where the computer is at each read ((name, "lat,lon"), from its internet address, so a
    laptop that travels gets its own weather), and `fallback` (the time zone's city) is for when it can't."""

    def __init__(self, weather: Weather, clock: Clock, *, place: str, units: str = "metric", days: int = DAYS,
                 refresh_s: float = REFRESH_S, retry_s: float = RETRY_S, stale_s: float = STALE_S,
                 locate: Callable[[], tuple[str, str]] | None = None, fallback: str = ""):
        self._weather = weather
        self._clock = clock
        self.place = place
        """The place the forecast is for, as the block names it."""
        self._configured = place
        self._locate = locate
        self._fallback = fallback
        self._units = units
        self._days = days
        self._refresh_s = refresh_s
        self._retry_s = retry_s
        self._stale_s = stale_s
        self._forecast: Forecast | None = None
        self._read_at: float | None = None
        """When the forecast was read (monotonic)."""
        self._tried_at: float | None = None
        self.pending: asyncio.Task | None = None
        """The fetch running now, if one is."""

    def soon(self) -> None:
        """Fetch now, in the background, if the forecast is older than `refresh_s` (or the last try failed more
        than `retry_s` ago)."""
        if self.pending is not None and not self.pending.done():
            return
        now = self._clock.monotonic()
        if self._read_at is not None and now - self._read_at < self._refresh_s:
            return
        if self._tried_at is not None and now - self._tried_at < self._retry_s:
            return
        self._tried_at = now
        self.pending = asyncio.create_task(self._fetch())

    def lines(self) -> list[str]:
        """The forecast for the block, [] when there is none fresh enough."""
        if self._forecast is None or self._read_at is None:
            return []
        if self._clock.monotonic() - self._read_at > self._stale_s:
            return []
        return lines(self._forecast, self._clock.now(), place=self.place)

    async def _fetch(self) -> None:
        started = self._clock.monotonic()
        try:
            name, query = await asyncio.to_thread(self._where)
            if not query:
                log.info("no weather for <today>: no place; set [weather] place")
                return
            forecast = await asyncio.to_thread(self._weather.forecast, query, self._days, self._units)
        except ToolError as e:
            log.info("no weather for <today>: %s", e)
            return
        except Exception:
            log.exception("reading the weather failed")
            return
        self._forecast, self._read_at, self.place = forecast, self._clock.monotonic(), name
        log.info("weather read in %.2fs: %d days", self._read_at - started, len(forecast.days))

    def _where(self) -> tuple[str, str]:
        """(the name for the block, what the service looks up), on a thread: the config's place, else where the
        internet address is, else the time zone's city."""
        if self._configured:
            return self._configured, self._configured
        if self._locate is not None:
            name, at = self._locate()
            if at:
                return name or at, at
        return self._fallback, self._fallback
