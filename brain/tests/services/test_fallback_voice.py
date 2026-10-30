import pytest

from milo.core.ports import Voice
from milo.services.fallback_voice import FallbackVoice
from tests.fakes import FakeVoice


class BrokenVoice(FakeVoice):
    sample_rate = 24000

    def warm(self) -> None:
        raise RuntimeError("no torch")


def test_uses_primary_when_it_loads():
    primary = FakeVoice()
    voice = FallbackVoice(primary, lambda: pytest.fail("fallback must not be built"))
    voice.warm()
    voice.synthesize("hi")
    assert isinstance(voice, Voice)
    assert primary.warmed and primary.spoken == ["hi"]


def test_switches_to_fallback_when_primary_fails_to_load():
    fallback = FakeVoice()
    voice = FallbackVoice(BrokenVoice(), lambda: fallback)
    assert voice.sample_rate == 24000
    voice.warm()
    voice.synthesize("hi")
    assert voice.current is fallback and fallback.warmed and fallback.spoken == ["hi"]
    assert voice.sample_rate == FakeVoice.sample_rate


def test_without_fallback_the_error_surfaces():
    with pytest.raises(RuntimeError, match="no torch"):
        FallbackVoice(BrokenVoice(), None).warm()
