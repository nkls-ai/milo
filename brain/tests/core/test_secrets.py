"""Secret files (API keys, bot tokens): one reader with the same checks for every key."""

import logging
import os
import stat

import pytest

from milo.adapters.stt.elevenlabs_scribe import ScribeRealtime
from milo.adapters.tts.elevenlabs import ElevenLabsVoice
from milo.core.secrets import SecretError, read_secret
from milo.core.types import VoiceUnavailable


def mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def secrets(tmp_path):
    folder = tmp_path / "secrets"
    folder.mkdir(mode=0o700)
    return folder


def test_a_private_key_is_read_and_left_alone(secrets, caplog):
    key = secrets / "elevenlabs.key"
    key.write_text("sk-123\n")
    os.chmod(key, 0o600)
    assert read_secret(key, "The ElevenLabs key") == "sk-123"
    assert mode(key) == 0o600 and mode(secrets) == 0o700 and "made it" not in caplog.text


def test_a_key_others_could_read_is_made_private_and_the_log_says_so(secrets, caplog):
    caplog.set_level(logging.WARNING, logger="milo.secrets")
    os.chmod(secrets, 0o755)
    key = secrets / "elevenlabs.key"
    key.write_text("sk-123")
    os.chmod(key, 0o644)
    assert read_secret(key, "The ElevenLabs key") == "sk-123"
    assert mode(key) == 0o600 and mode(secrets) == 0o700
    assert "others on this Mac could read" in caplog.text and "sk-123" not in caplog.text


def test_links_folders_and_empty_files_are_refused(secrets):
    key = secrets / "key"
    key.write_text("sk-123")
    link = secrets / "link"
    link.symlink_to(key)
    with pytest.raises(SecretError, match="plain file"):
        read_secret(link, "The key")
    with pytest.raises(SecretError, match="plain file"):
        read_secret(secrets, "The key")
    (secrets / "empty").write_text("\n")
    with pytest.raises(SecretError, match="is empty"):
        read_secret(secrets / "empty", "The key")
    with pytest.raises(SecretError, match="put it alone in"):
        read_secret(secrets / "missing", "The key")


def test_both_elevenlabs_engines_go_through_the_same_checks(secrets):
    key = secrets / "elevenlabs.key"
    key.write_text("sk-123")
    os.chmod(key, 0o644)
    ElevenLabsVoice(key).warm()
    assert mode(key) == 0o600
    link = secrets / "link.key"
    link.symlink_to(key)
    with pytest.raises(VoiceUnavailable, match="plain file"):
        ElevenLabsVoice(link).warm()
    session = ScribeRealtime(link).session()
    assert session._error is not None and "plain file" in session._error


def test_the_file_is_checked_and_read_through_one_handle(secrets, monkeypatch):
    # Checks on the path and a second open for the read would let a link be swapped in between.
    key = secrets / "key"
    key.write_text("sk-123")
    fifo = secrets / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(SecretError, match="plain file"):
        read_secret(fifo, "The key")  # refused at once, not left waiting for a writer
    opened = []
    real_open = os.open
    monkeypatch.setattr(os, "open", lambda p, flags, *a: opened.append(flags) or real_open(p, flags, *a))
    assert read_secret(key, "The key") == "sk-123"
    assert len(opened) == 1 and opened[0] & os.O_NOFOLLOW
