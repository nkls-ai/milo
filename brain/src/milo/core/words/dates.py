"""Days, dates, clock times and spans in words, the same on every platform and in every locale.

`%-d` (a day without its leading zero) is a glibc and BSD extension: Windows' strftime raises on it. `%A` and `%B`
follow the process's locale, so a library that calls setlocale would turn "Thursday" into "Donnerstag" in the
middle of a prompt. These spell days and months themselves, in English unless a caller asks for German. Times
(`%H:%M`) and ISO dates are fine as they are.
"""

from __future__ import annotations

from datetime import date, datetime

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
_DAYS = {"en": WEEKDAYS, "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")}
_MONTHS = {"en": MONTHS, "de": ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
                                "Oktober", "November", "Dezember")}
_NEAR = {"en": ("today", "tomorrow", "the day after tomorrow"), "de": ("heute", "morgen", "übermorgen")}
_SPANS = {"en": (("hour", "hours"), ("minute", "minutes"), ("second", "seconds")),
          "de": (("Stunde", "Stunden"), ("Minute", "Minuten"), ("Sekunde", "Sekunden"))}


def _lang(lang: str) -> str:
    return lang if lang in _DAYS else "en"


def weekday(day: date, lang: str = "en", *, short: bool = False) -> str:
    """"Thursday", or "Thu"; "Donnerstag"."""
    name = _DAYS[_lang(lang)][day.weekday()]
    return name[:3] if short else name


def month(day: date, lang: str = "en", *, short: bool = False) -> str:
    """"November", or "Nov"; "November"."""
    name = _MONTHS[_lang(lang)][day.month - 1]
    return name[:3] if short else name


def long_date(day: date, lang: str = "en", *, year: bool = False, short: bool = False) -> str:
    """"Thursday 5 November", with " 2026" if `year`; "Thu 5 Nov" if `short`; "Donnerstag, 5. November"."""
    if _lang(lang) == "de":
        text = f"{weekday(day, lang, short=short)}, {day.day}. {month(day, lang, short=short)}"
    else:
        text = f"{weekday(day, short=short)} {day.day} {month(day, short=short)}"
    return f"{text} {day.year}" if year else text


def date_time(t: datetime, lang: str = "en", *, midnight: bool = True) -> str:
    """"Thursday 5 November at 15:00"; "Donnerstag, 5. November um 15:00". `midnight=False` leaves a 00:00 out."""
    if not midnight and (t.hour, t.minute) == (0, 0):
        return long_date(t, lang)
    return f"{long_date(t, lang)} {'um' if _lang(lang) == 'de' else 'at'} {t:%H:%M}"


def day(d: date, today: date, lang: str) -> str:
    """"today", "tomorrow", "Thursday" within a week, else "Thursday 12 November"."""
    lang = _lang(lang)
    ahead = (d - today).days
    if 0 <= ahead < 3:
        return _NEAR[lang][ahead]
    if 0 < ahead < 7:
        return weekday(d, lang)
    return long_date(d, lang)


def clock(t: datetime, lang: str) -> str:
    """"at 3 pm", "at 3:30 pm"; "um 15 Uhr", "um 15:30"."""
    if lang == "de":
        return f"um {t.hour} Uhr" if t.minute == 0 else f"um {t:%H:%M}"
    hour = t.hour % 12 or 12
    half = "am" if t.hour < 12 else "pm"
    return f"at {hour} {half}" if t.minute == 0 else f"at {hour}:{t:%M} {half}"


def when(t: datetime, today: date, lang: str, *, all_day: bool = False) -> str:
    """"Thursday at 3 pm", "morgen um 9 Uhr"; a whole day says only the day."""
    d = day(t.date(), today, lang)
    return d if all_day else f"{d} {clock(t, lang)}"


def span(seconds: float, lang: str) -> str:
    """"10 minutes", "1 hour 30 minutes", "90 seconds"; "10 Minuten"."""
    seconds = max(1, round(seconds))
    words = _SPANS[_lang(lang)]
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if seconds < 120 and not hours:
        minutes, secs = (0, seconds) if seconds % 60 else (seconds // 60, 0)
    parts = [(n, w) for n, w in zip((hours, minutes, secs), words) if n]
    return " ".join(f"{n} {w[0] if n == 1 else w[1]}" for n, w in parts) or f"0 {words[2][1]}"
