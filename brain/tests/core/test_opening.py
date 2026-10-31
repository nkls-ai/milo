"""What an <open> tag opens, and which language a message is in (ADR 0028)."""

import pytest

from milo.core.language import SpokenLanguage, detect, name, normalize
from milo.core.opening import OpenRequest, named_by, resolve_url


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


def test_the_users_words_name_the_site_the_file_or_any_app():
    youtube = OpenRequest("Google Chrome", "https://www.youtube.com")
    assert named_by(youtube, "So can you open, um, Chrome for me and go on YouTube?")
    assert not named_by(youtube, "open the link from the mail")
    assert not named_by(OpenRequest(url="https://evil.example/?q=secret"), "open the link from the mail")
    assert not named_by(OpenRequest(url="https://youtube.com.evil.example"), "go on YouTube")
    assert not named_by(OpenRequest(path="~/Downloads"), "open my downloads folder"), "after outside text a path asks"
    assert named_by(OpenRequest(app="Notes"), "anything")


def test_after_outside_text_only_the_sites_own_address_counts_as_named():
    """Outside text can make the talker write any address; the user's word "YouTube" must not carry it."""
    assert not named_by(OpenRequest(url="https://youtube.evil"), "go on YouTube"), "another top-level domain"
    assert not named_by(OpenRequest(url="https://www.youtube.xyz"), "go on YouTube")
    assert not named_by(OpenRequest(url="https://youtube.evil/?d=secret"), "go on YouTube")
    assert not named_by(OpenRequest(url="https://www.youtube.com/watch?v=x&d=secret"), "go on YouTube"), \
        "a path or query could carry what Milo read"
    assert named_by(OpenRequest(url="https://youtube.com/"), "go on YouTube")
    assert not named_by(OpenRequest(url="https://www.attachment.com"), "open the attachment"), \
        "a word in passing isn't an address"
    assert named_by(OpenRequest(url="https://www.figma.com"), "open figma.com")
    assert not named_by(OpenRequest(url="https://evil.example@www.youtube.com"), "go on YouTube"), "a user part"
    assert not named_by(OpenRequest(url="https://www.youtube.com\\@evil.example"), "go on YouTube")
    assert not named_by(OpenRequest(url="https://www.youtube.com:8443"), "go on YouTube"), "a port"
    assert named_by(OpenRequest(url="https://www.bbc.co.uk"), "open bbc.co.uk"), "the address the user said"
    assert not named_by(OpenRequest(url="https://www.bbc.co.uk"), "open the BBC"), "only its address names it"
    assert named_by(OpenRequest(url="https://mail.google.com"), "check my gmail")


def test_a_page_the_user_asked_for_opens_with_its_search_or_language_site():
    """After outside text, the user's own request still opens without a question when every word in the address is
    theirs: a site's language edition, a search for their words. A word they didn't say still asks."""
    words = "Can you open a new tab and search for Wikipedia?"
    assert named_by(OpenRequest(url="https://de.wikipedia.org"), words), "a site's own subdomain"
    assert named_by(OpenRequest(url="https://www.google.com/search?q=wikipedia&hl=en"), words), "a search for it"
    assert named_by(OpenRequest(url="https://www.youtube.com/results?search_query=lofi+beats"),
                    "search YouTube for lofi beats")
    assert named_by(OpenRequest(url="https://de.wikipedia.org/wiki/Katze"), "zeig mir Katze auf Wikipedia")
    assert not named_by(OpenRequest(url="https://www.google.com/search?q=wikipedia+hunter2"), words), \
        "a word the user didn't say could be what Milo read"
    assert not named_by(OpenRequest(url="https://www.google.com/search?q=cats"), "open YouTube"), \
        "a search engine counts only when they asked to search"
    assert not named_by(OpenRequest(url="https://wikipedia.evil.example"), words)
    assert not named_by(OpenRequest(url="https://sites.google.com/view/evil"), "search google for cats")


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
    assert language.hear("Can you open a new tab and search for Wikipedia?", reported="deu") == "en", \
        "clear English words win over a transcriber that heard an accent as German"
    assert language.hear("Kannst du Chrome öffnen?", reported="eng") == "de"


def test_a_greeting_says_its_language_and_the_last_language_outlives_a_restart(tmp_path):
    """2026-10-31: after a restart "hi" got "Hallo! Ich bin Milo": too short to tell, and nothing to keep."""
    from milo.core.language import SpokenLanguage, detect

    assert detect("hi") == "en" and detect("hello") == "en" and detect("moin") == "de"
    kept = []
    language = SpokenLanguage(changed=kept.append)
    language.hear("Can you open Chrome and YouTube?")
    language.hear("okay")
    assert kept == ["en"], "told once, when it changed"
    assert SpokenLanguage(kept[-1]).hear("mhm") == "en"


def test_everyday_commands_say_their_language():
    """On the real Milo "cancel the pasta timer" after a German turn got a German answer: one known word in four."""
    from milo.core.language import detect

    for text, code in [("cancel the pasta timer", "en"), ("Okay, take it back", "en"), ("spiel Musik", "de"),
                       ("nimm das zurück", "de"), ("set a timer for 10 minutes", "en"),
                       ("stell einen Timer auf zehn Minuten", "de"), ("Spiel the Beatles", ""), ("nice", "")]:
        assert detect(text) == code, text
