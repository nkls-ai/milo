import locale
from datetime import date, datetime

from milo.core.words import dates


def test_dates_are_english_words_without_platform_flags():
    day = date(2026, 11, 5)
    assert dates.long_date(day) == "Thursday 5 November"
    assert dates.long_date(day, year=True) == "Thursday 5 November 2026"
    assert dates.long_date(datetime(2026, 1, 4, 9, 30), short=True) == "Sun 4 Jan"


def test_dates_ignore_the_process_locale():
    old = locale.setlocale(locale.LC_TIME)
    try:
        for name in ("de_DE.UTF-8", "de_DE", "fr_FR.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, name)
                break
            except locale.Error:
                continue
        assert dates.weekday(date(2026, 11, 5)) == "Thursday" and dates.month(date(2026, 3, 1)) == "March"
    finally:
        locale.setlocale(locale.LC_TIME, old)


def test_every_key_has_english_and_its_other_languages_fill_the_same_blanks():
    from string import Formatter

    from milo.core import words

    def blanks(template: str) -> set[str]:
        return {name for _, name, _, _ in Formatter().parse(template) if name}

    for key, templates in words.CATALOGUE.items():
        assert "en" in templates, f"{key} has no English"
        for lang, template in templates.items():
            assert blanks(template) <= blanks(templates["en"]), f"{key} in {lang} needs a value English doesn't"


def test_a_language_without_a_template_says_it_in_english():
    from milo.core import words

    assert words.say("acts.ask.play", "fr") == words.say("acts.ask.play", "en") == "Play the music?"
    assert words.say("acts.ask.play", "de") == "Musik abspielen?"


def test_german_dates():
    assert dates.long_date(date(2026, 11, 5), "de") == "Donnerstag, 5. November"
    assert dates.date_time(datetime(2026, 11, 5, 15), "de") == "Donnerstag, 5. November um 15:00"
    assert dates.date_time(datetime(2026, 11, 5, 15)) == "Thursday 5 November at 15:00"
    assert dates.date_time(datetime(2026, 11, 5), midnight=False) == "Thursday 5 November"
