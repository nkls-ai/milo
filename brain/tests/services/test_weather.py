"""The weather in <today> (ADR 0038).

The user's story: "Do I need an umbrella tomorrow?" and "how warm is it on Saturday?" should be answered at once,
like "what's on today", not by a helper looking it up for 20 s. So a short forecast rides in the <today> block,
read from Open-Meteo at most every 45 minutes, and quietly left out when the service can't be reached. No network
here: a fake service and a stubbed HTTP fetch.
"""

import asyncio
import logging
from datetime import date, datetime
from pathlib import Path

import pytest

from milo.adapters.connect.fake import World
from milo.adapters.weather.open_meteo import OpenMeteo
from milo.config import Config
from milo.core.registry import ConfigError
from milo.core.types import ToolError
from milo.core.weather import DayWeather, Forecast, city_of_zone, lines
from milo.services.today import Today
from milo.services.weather import WeatherReport
from tests.fakes import FakeClock, FakeLiveModel
from tests.services.stack import Stack, settle

NOW = datetime(2026, 10, 29, 9, 0)  # FakeClock's start, a Thursday
RAINY_AFTERNOON = tuple([0] * 14 + [60, 80, 80, 50] + [10] * 6)


def forecast(**kw) -> Forecast:
    days = (DayWeather(date(2026, 10, 29), 3, 4.6, 11.2, 20, 0.0, 12, 25, (5,) * 24),
            DayWeather(date(2026, 10, 30), 63, 6, 9.4, 80, 4.2, 35, 62, RAINY_AFTERNOON),
            DayWeather(date(2026, 10, 31), 1, 2, 12, 5),
            DayWeather(date(2026, 11, 1), 80, 3, 8, 55))
    return Forecast(**{"place": "Berlin", "units": "metric", "days": days, "now": 7.4, "now_code": 2, **kw})


class FakeWeather:
    def __init__(self, *answers):
        self.answers = list(answers) or [forecast()]
        self.calls: list[tuple[str, int, str]] = []

    def forecast(self, place: str, days: int, units: str) -> Forecast:
        self.calls.append((place, days, units))
        answer = self.answers[min(len(self.calls), len(self.answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_the_forecast_is_a_few_short_lines_today_and_tomorrow_with_the_rains_hours():
    assert lines(forecast(), NOW) == [
        "Weather in Berlin (°C, km/h):",
        "- Now: 7°C, partly cloudy.",
        "- Today: 5–11°C, overcast, rain chance 5%.",
        "- Tomorrow, Fri 30 Oct: 6–9°C, rain, rain chance 80%, mostly 14–18h, 4.2 mm in all, windy, gusts up to 62 "
        "km/h.",
        "- Sat 31 Oct: 2–12°C, mostly clear.",
        "- Sun 1 Nov: 3–8°C, light showers, rain chance 55%.",
    ]


def test_todays_rain_counts_from_now_on_and_past_days_drop_out():
    morning_rain = DayWeather(date(2026, 10, 29), 61, 4, 11, 90, 3.0, 0, 0, tuple([90] * 10 + [0] * 14))
    told = lines(forecast(days=(morning_rain,)), datetime(2026, 10, 29, 15, 0))
    assert told[-1] == "- Today: 4–11°C, light rain, rain chance 0%, 3.0 mm in all.", \
        "the morning's rain is over; the rest of the day is what an umbrella is for"
    assert lines(forecast(), datetime(2026, 11, 2, 9, 0)) == [], "nothing left from that forecast"
    later = lines(forecast(), datetime(2026, 10, 31, 9, 0))
    assert later[1] == "- Today: 2–12°C, mostly clear, rain chance 5%.", "no \"Now\" from an older day either"


def test_imperial_units_come_with_their_own_signs():
    us = forecast(units="imperial", place="Portland", now=48.0, days=(
        DayWeather(date(2026, 10, 29), 0, 39, 53, 0, 0.0, 22, 35, (0,) * 24),))
    assert lines(us, NOW) == ["Weather in Portland (°F, mph):", "- Now: 48°F, partly cloudy.",
                              "- Today: 39–53°F, clear, rain chance 0%, windy, gusts up to 35 mph."]


def test_the_place_comes_from_the_time_zone_when_none_is_set():
    assert city_of_zone("Europe/Berlin") == "Berlin"
    assert city_of_zone("America/New_York") == "New York"
    assert city_of_zone("America/Argentina/Buenos_Aires") == "Buenos Aires"
    assert city_of_zone("UTC") == city_of_zone("Etc/GMT+1") == city_of_zone("") == ""


def test_the_weather_section_of_config_toml():
    config = Config({})
    assert (config.weather.enabled, config.weather.place, config.weather.units, config.weather.by_ip) == \
        (True, "", "metric", True)
    assert config.pluggable("weather") == ("open_meteo", {})
    assert Config({"weather": {"place": "Portland, Oregon", "units": "imperial"}}).weather.place == "Portland, Oregon"
    with pytest.raises(ConfigError, match="units"):
        Config({"weather": {"units": "kelvin"}})


# ---- Open-Meteo, with the HTTP stubbed


GEO = {"results": [
    {"name": "Portland", "latitude": 43.66, "longitude": -70.25, "country": "United States", "admin1": "Maine"},
    {"name": "Portland", "latitude": 45.52, "longitude": -122.68, "country": "United States", "admin1": "Oregon"}]}
FORECAST = {
    "daily": {"time": ["2026-10-29", "2026-10-30", "2026-10-31"], "weather_code": [3, 63, None],
              "temperature_2m_max": [11.2, 9.4, None], "temperature_2m_min": [4.6, 6.0, None],
              "precipitation_probability_max": [20, 80, None], "precipitation_sum": [0.0, 4.2, None],
              "wind_speed_10m_max": [12.0, 35.0, None], "wind_gusts_10m_max": [25.0, 62.0, None]},
    "hourly": {"time": [f"2026-10-{d}T{h:02d}:00" for d in (29, 30) for h in range(24)],
               "precipitation_probability": [5] * 24 + list(RAINY_AFTERNOON)},
    "current": {"temperature_2m": 7.4, "weather_code": 2},
}


class StubHttp:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.urls: list[str] = []

    def __call__(self, url: str, timeout_s: float):
        self.urls.append(url)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_open_meteo_finds_the_place_once_and_reads_the_forecast():
    http = StubHttp(GEO, FORECAST, FORECAST)
    service = OpenMeteo(fetch=http)
    got = service.forecast("Portland, Oregon", 7, "metric")
    assert "name=Portland" in http.urls[0] and "Oregon" not in http.urls[0], "the search knows names only"
    assert "latitude=45.5200" in http.urls[1] and "longitude=-122.6800" in http.urls[1], "the comma picked Oregon"
    assert "forecast_days=7" in http.urls[1] and "temperature_unit=celsius" in http.urls[1]
    assert got.place == "Portland" and got.now == 7.4 and got.now_code == 2
    assert [d.day for d in got.days] == [date(2026, 10, 29), date(2026, 10, 30)], "a day with no numbers is left out"
    assert got.days[1] == DayWeather(date(2026, 10, 30), 63, 6.0, 9.4, 80, 4.2, 35.0, 62.0, RAINY_AFTERNOON)
    service.forecast("portland,  oregon", 7, "imperial")
    assert len(http.urls) == 3, "the place is looked up once"
    assert "temperature_unit=fahrenheit" in http.urls[2] and "wind_speed_unit=mph" in http.urls[2]


def test_open_meteo_takes_a_position_and_says_plainly_what_went_wrong():
    http = StubHttp(FORECAST)
    OpenMeteo(fetch=http).forecast("52.52, 13.41", 3, "metric")
    assert len(http.urls) == 1 and "latitude=52.5200" in http.urls[0], "no search for a position"
    with pytest.raises(ToolError, match="doesn't know the place"):
        OpenMeteo(fetch=StubHttp({})).forecast("Atlantis", 3, "metric")
    with pytest.raises(ToolError, match="can't be reached"):
        OpenMeteo(fetch=StubHttp(OSError("offline"))).forecast("52.5,13.4", 3, "metric")
    with pytest.raises(ToolError, match="can't read"):
        OpenMeteo(fetch=StubHttp({"daily": {"time": ["2026-10-29"]}})).forecast("52.5,13.4", 3, "metric")


# ---- the report and <today>


def test_the_report_reads_at_most_every_45_minutes_and_keeps_the_last_one():
    clock = FakeClock()
    service = FakeWeather(forecast(), ToolError("offline"), forecast(now=12.0))
    report = WeatherReport(service, clock, place="Berlin")

    async def run():
        report.soon()
        await report.pending
        assert service.calls == [("Berlin", 7, "metric")]
        report.soon()
        assert report.pending.done(), "fresh: no second read"
        clock.advance(minutes=46)
        report.soon()
        await report.pending
        assert report.lines()[1] == "- Now: 7°C, partly cloudy.", "the read failed: the last forecast stays"
        clock.advance(minutes=5)
        report.soon()
        assert len(service.calls) == 2, "a failed read waits 10 minutes before it tries again"
        clock.advance(minutes=6)
        report.soon()
        await report.pending
        assert report.lines()[1] == "- Now: 12°C, partly cloudy."
        clock.advance(hours=7)
        assert report.lines() == [], "too old to tell as if it were new"

    asyncio.run(run())


def test_the_weather_closes_the_today_block_and_isnt_other_peoples_text(tmp_path):
    clock = FakeClock()
    report = WeatherReport(FakeWeather(), clock, place="Berlin")
    today = Today(None, clock, weather=report)

    async def run():
        return await today.note()

    text, outside = asyncio.run(run())
    assert text.endswith("- Sun 1 Nov: 3–8°C, light showers, rain chance 55%.\n</today>")
    assert "Weather in Berlin (°C, km/h):" in text and not outside


def test_without_the_service_the_block_goes_without_the_weather_quietly(tmp_path, caplog):
    caplog.set_level(logging.INFO, "milo.weather")
    clock = FakeClock()
    today = Today(None, clock, weather=WeatherReport(FakeWeather(ToolError("Open-Meteo can't be reached")), clock,
                                                    place="Berlin"))
    assert asyncio.run(today.note()) == ("", False)
    assert "no weather for <today>: Open-Meteo can't be reached" in caplog.text


def test_the_talker_answers_the_umbrella_question_from_the_block(tmp_path):
    World(tmp_path / "world").save({"events": [], "reminders": []})
    s = Stack(model=FakeLiveModel(["[neutral] Yes, take one: rain is likely tomorrow afternoon."]),
              world=tmp_path / "world", home=tmp_path / "home")
    s.quick.today.weather = WeatherReport(FakeWeather(), s.clock, place="Berlin")

    async def run():
        await s.live_talk.start("do I need an umbrella tomorrow?")
        await settle()

    asyncio.run(run())
    [turn] = s.model.turns
    assert "- Tomorrow, Fri 30 Oct: 6–9°C, rain, rain chance 80%, mostly 14–18h" in turn
    assert "Answer weather questions from it" in s.model.system_prompts[-1]
    assert not s.tasks.helpers, "no helper for the weather"


# ---- where the weather is for, without a place in config.toml


def test_without_a_place_the_internet_address_tells_where_and_the_time_zone_is_the_last_resort():
    """The user, 2026-11-01: "it didn't use my correct location?" The time zone said Berlin; they were near
    Osnabrück. The address says Münster, 50 km off: close enough for rain."""
    clock = FakeClock()
    service = FakeWeather(forecast(), forecast(), forecast())
    found = iter([("Münster", "51.9624,7.6257"), ("", "")])
    report = WeatherReport(service, clock, place="", locate=lambda: next(found), fallback="Berlin")
    configured = WeatherReport(FakeWeather(forecast()), clock, place="Osnabrück", locate=lambda: 1 / 0)

    async def run():
        report.soon()
        await report.pending
        assert service.calls[-1][0] == "51.9624,7.6257", "the position, not a name: there are several Münsters"
        assert report.lines()[0].startswith("Weather in Münster")
        clock.advance(minutes=46)
        report.soon()
        await report.pending
        assert service.calls[-1][0] == "Berlin" and report.lines()[0].startswith("Weather in Berlin")
        configured.soon()
        await configured.pending
        assert configured.lines()[0].startswith("Weather in Osnabrück"), "a place in config.toml wins, unasked"

    asyncio.run(run())


def test_the_address_lookup_reads_ipinfo_and_never_raises():
    from milo.adapters.weather.ip_location import ip_place
    asked = []

    def fetch(url, timeout_s):
        asked.append(url)
        return {"city": "Münster", "region": "North Rhine-Westphalia", "loc": "51.9624,7.6257"}

    assert ip_place(fetch=fetch) == ("Münster", "51.9624,7.6257") and asked == ["https://ipinfo.io/json"]
    assert ip_place(fetch=lambda u, t: {"city": "X", "loc": "<b>"}) == ("", "")
    assert ip_place(fetch=lambda u, t: (_ for _ in ()).throw(OSError("offline"))) == ("", "")
