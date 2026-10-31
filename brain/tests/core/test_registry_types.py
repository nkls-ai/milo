from dataclasses import dataclass
from pathlib import Path

import pytest

from milo.core.registry import AdapterContext, ConfigError, Registry, options_from
from milo.core.types import Emotion, Reply, Usage
from tests.fakes import FakeClock

CTX = AdapterContext(home=Path("/tmp/milo"), state_dir=Path("/tmp/milo/state"), clock=FakeClock())


@dataclass(frozen=True)
class Opts:
    voice: str = ""
    speed: float = 1.0
    tags: tuple[str, ...] = ()


def test_registry_creates_by_name_with_options():
    reg: Registry[str] = Registry("thing")

    @reg.register("echo")
    def _echo(options, ctx):
        return f"{options_from(Opts, options, 'thing.echo').voice}@{ctx.home}"

    assert reg.create("echo", {"voice": "flo"}, CTX) == "flo@/tmp/milo"
    assert reg.names() == ["echo"]


def test_registry_rejects_unknown_name_and_duplicates():
    reg: Registry[str] = Registry("thing")
    reg.register("a")(lambda o, c: "a")
    with pytest.raises(ConfigError, match="unknown thing 'b'; available: a"):
        reg.create("b", {}, CTX)
    with pytest.raises(ValueError, match="twice"):
        reg.register("a")(lambda o, c: "again")


def test_options_from_rejects_typos_and_converts_lists():
    assert options_from(Opts, {"tags": ["x", "y"]}, "s").tags == ("x", "y")
    with pytest.raises(ConfigError, match=r"unknown key\(s\) in \[tts.say\]: vocie"):
        options_from(Opts, {"vocie": "x"}, "tts.say")


def test_reply_parsing():
    r = Reply.from_model_text('{"emotion": "excited", "say": " On it! "}', Usage(), "s")
    assert (r.emotion, r.say, r.session_id) == (Emotion.EXCITED, "On it!", "s")
    assert Reply.from_model_text("plain words", Usage(), None).emotion is Emotion.NEUTRAL
    assert Reply.from_model_text('{"emotion": "furious", "say": "hi"}', Usage(), None).emotion is Emotion.NEUTRAL
    found = Reply.from_model_text('{"emotion": "happy", "say": "It\'s on your clipboard.", "copy": " https://x.y/z "}',
                                  Usage(), None)
    assert (found.say, found.copy) == ("It's on your clipboard.", "https://x.y/z")
    assert r.copy == "" and Reply.from_model_text('{"say": "hi", "copy": null}', Usage(), None).copy == ""
