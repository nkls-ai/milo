"""What an <open> tag opens, and which language a message is in (ADR 0028)."""

import pytest

from milo.core.language import SpokenLanguage, detect, name, normalize
from milo.core.opening import OpenRequest, named_by, resolve_url, site_names


@pytest.mark.parametrize("text, url", [
    ("YouTube", "https://www.youtube.com"),
    ("youtube", "https://www.youtube.com"),
    ("Gmail", "https://mail.google.com"),
    ("youtube.com", "https://youtube.com"),
    ("www.spiegel.de/politik", "https://www.spiegel.de/politik"),
    ("https://www.youtube.com/results?search_query=cats", "https://www.youtube.com/results?search_query=cats"),
    ("http://localhost:8080", "http://localhost:8080"),
    ("figma", "https://www.figma.com"),
])
def test_a_site_the_user_names_becomes_its_address(text, url):
    assert resolve_url(text) == url


@pytest.mark.parametrize("text", ["javascript:alert(1)", "file:///etc/passwd", "shortcuts://run-shortcut?name=x",
                                  "mailto:anna@example.com", "x-apple.systempreferences:com.apple.x", "", "two words",
                                  "ftp://example.com"])
def test_only_web_pages_open_as_addresses(text):
    assert resolve_url(text) is None


def test_the_words_for_a_site_are_its_domains_name_not_any_label():
    assert site_names("https://www.youtube.com") == ["youtube"]
    assert site_names("https://www.bbc.co.uk/news") == ["bbc"]
    assert set(site_names("https://maps.google.com")) == {"maps", "google maps"}
    assert site_names("https://youtube.com.evil.example/") == [], "a lookalike host has no name"
    assert site_names("https://youtube.github.io") == [], "anyone's page under someone else's domain has no name"
    assert site_names("https://evil.blogspot.com") == []
    assert site_names("https://mail.google.com") == ["gmail"], "a subdomain only by its exact SITES address"


def test_the_users_words_name_the_site_the_file_or_any_app():
    youtube = OpenRequest("Google Chrome", "https://www.youtube.com")
    assert named_by(youtube, "So can you open, um, Chrome for me and go on YouTube?")
    assert not named_by(youtube, "open the link from the mail")
    assert not named_by(OpenRequest(url="https://evil.example/?q=secret"), "open the link from the mail")
    assert not named_by(OpenRequest(url="https://youtube.com.evil.example"), "go on YouTube")
    assert not named_by(OpenRequest(path="~/Downloads"), "open my downloads folder"), "after outside text a path asks"
    assert named_by(OpenRequest(app="Notes"), "anything")


def test_what_is_opened_reads_as_the_host_the_file_or_the_app():
    assert OpenRequest("Google Chrome", "https://www.youtube.com/watch?v=1").what == "www.youtube.com"
    assert OpenRequest(path="~/Documents/Budget.xlsx").what == "Budget.xlsx"
    assert OpenRequest(app="Notes").what == "Notes"


@pytest.mark.parametrize("text, code", [
    ("Yeah, it's now much smoother, and you feel more, um, alive, I would say. So can you open, um, Chrome for me "
     "and Google or, like, go on YouTube?", "en"),
    ("Kannst du bitte Chrome öffnen und auf YouTube gehen?", "de"),
    ("Mach die Mappe rot", "de"),
    ("open Chrome", "en"),
    ("okay", ""),
    ("YouTube", ""),
])
def test_german_and_english_are_told_apart_from_the_words(text, code):
    assert detect(text) == code


def test_codes_from_the_engines_become_two_letters():
    assert normalize("eng") == "en" and normalize("deu") == "de" and normalize("en-US") == "en"
    assert normalize("German") == "de" and normalize("") == "" and normalize("xyz") == ""
    assert name("deu") == "German" and name("en") == "English"


def test_a_short_message_keeps_the_conversations_language():
    language = SpokenLanguage()
    assert language.hear("Kannst du bitte Chrome öffnen?") == "de"
    assert language.hear("okay") == "de", "nothing to tell it by: stays German"
    assert language.hear("Okay", reported="eng") == "en", "what the transcriber heard wins"
    assert language.hear("open YouTube in Chrome") == "en"
