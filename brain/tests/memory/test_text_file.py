"""persona.md and profile.md go into the chat model's system prompt, which LiveTalk builds on every press of the talk
key to see whether the conversation is still fresh. They are read again only when they changed."""

import os
from pathlib import Path

from milo.memory.profile import MarkdownProfile
from milo.memory.text_file import TextFile


def counting(monkeypatch) -> list[str]:
    reads: list[str] = []
    real = Path.read_text

    def read_text(self, *args, **kw):
        reads.append(self.name)
        return real(self, *args, **kw)

    monkeypatch.setattr(Path, "read_text", read_text)
    return reads


def test_a_file_is_read_again_only_when_it_changed(tmp_path, monkeypatch):
    persona = tmp_path / "persona.md"
    persona.write_text("You are Milo.", encoding="utf-8")
    text = TextFile(persona)
    reads = counting(monkeypatch)
    assert [text.read() for _ in range(5)] == ["You are Milo."] * 5
    assert reads == ["persona.md"]
    persona.write_text("You are Milo, a wren.", encoding="utf-8")
    os.utime(persona, ns=(1, 1))  # even an edit within the same mtime tick: the size changed
    assert text.read() == "You are Milo, a wren."
    persona.unlink()
    assert text.read() == ""


def test_the_profile_is_read_once_until_milo_or_the_user_changes_it(tmp_path, monkeypatch):
    profile = MarkdownProfile(tmp_path / "profile.md")
    profile.remember("Likes tea")
    reads = counting(monkeypatch)
    assert profile.read() == profile.read()
    assert reads.count("profile.md") == 1
    profile.remember("Lives in Hamburg")
    assert "Lives in Hamburg" in profile.read()
