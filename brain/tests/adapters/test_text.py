import pytest

from milo.core.registry import TEXT_CLEANERS, ConfigError


@pytest.fixture
def fillers(ctx):
    return TEXT_CLEANERS.create("fillers", {"languages": ["en", "de"]}, ctx)


@pytest.mark.parametrize("raw, expected", [
    ("um so I think, uh, we should ship it", "So I think, we should ship it"),
    ("ähm ich glaube äh das passt", "Ich glaube das passt"),
    ("Hmm. Let's go.", "Let's go."),
    ("erm, öhm, okay", "Okay"),
    ("the umbrella is here", "The umbrella is here"),  # "um" inside a word stays
    ("  hello   world  ", "Hello world"),
])
def test_fillers_cleaner(fillers, raw, expected):
    assert fillers.clean(raw) == expected


def test_fillers_only_for_configured_languages(ctx):
    english = TEXT_CLEANERS.create("fillers", {"languages": ["en"]}, ctx)
    assert english.clean("äh um yes") == "Äh yes"
    german = TEXT_CLEANERS.create("fillers", {"languages": ["de"]}, ctx)
    assert german.clean("äh um ja") == "Um ja"


def test_fillers_default_languages(ctx):
    assert TEXT_CLEANERS.create("fillers", {}, ctx).clean("uh, ähm hi") == "Hi"


def test_fillers_rejects_unknown_language(ctx):
    with pytest.raises(ConfigError, match="xx"):
        TEXT_CLEANERS.create("fillers", {"languages": ["en", "xx"]}, ctx)
    with pytest.raises(ConfigError, match="list"):
        TEXT_CLEANERS.create("fillers", {"languages": "en"}, ctx)


@pytest.mark.parametrize("raw, expected", [
    ("um yes", "Um yes"),  # keeps fillers
    ("hello , world .", "Hello, world."),
    (", so  then", "So then"),
    ("", ""),
])
def test_plain_cleaner(ctx, raw, expected):
    assert TEXT_CLEANERS.create("plain", {}, ctx).clean(raw) == expected
