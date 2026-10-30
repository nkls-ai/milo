"""What may go to the owner's phone, and the guard over Milo's settings while the owner is away."""

import os

import pytest

from milo.services.settings_guard import PUT_BACK, SettingsGuard
from milo.services.sharing import NotShareable, read, shareable


@pytest.fixture
def home(tmp_path):
    (tmp_path / "Milo").mkdir()
    (tmp_path / "Documents").mkdir()
    return tmp_path


def share(home, path, **kw):
    return shareable(str(path), home=home, milo=home / "Milo", **kw)


def test_an_ordinary_file_is_shareable_and_read_whole(home):
    f = home / "Documents" / "slides.key"
    f.write_bytes(b"deck")
    out = share(home, f)
    assert out.name == "slides.key" and out.size == 4
    assert read(out, home=home, milo=home / "Milo") == b"deck"
    made = home / "Milo" / "report.xlsx"  # something a helper made in Milo's folder
    made.write_bytes(b"x")
    assert share(home, "report.xlsx").path == made.resolve()


@pytest.mark.parametrize("where", [".SSH/id_rsa", ".Ssh/config", "library/keychains/login.keychain-db",
                                   "Milo/Config.toml", "Milo/SECRETS/telegram-token", "Milo/State/messages.json",
                                   "Documents/.ENV.local", "Milo/.codex/auth.json", "Milo/AGENTS.md"])
def test_private_places_are_refused_whatever_the_case(home, where):
    f = home / where
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("secret")
    with pytest.raises(NotShareable):
        share(home, f)


def test_folders_missing_files_and_big_files_are_refused(home):
    with pytest.raises(NotShareable, match="isn't a file"):
        share(home, home / "Documents")
    with pytest.raises(NotShareable, match="no file"):
        share(home, home / "nope.pdf")
    big = home / "Documents" / "big.mov"
    big.write_bytes(b"x" * 2 * 1024 * 1024)
    with pytest.raises(NotShareable, match="2 MB, more than the 1 MB"):
        share(home, big, max_mb=1)


def test_a_file_swapped_while_the_question_waited_is_not_sent(home):
    f = home / "Documents" / "notes.txt"
    f.write_text("harmless")
    out = share(home, f)
    secret = home / ".ssh" / "id_rsa"
    secret.parent.mkdir()
    secret.write_text("KEY")
    f.unlink()
    f.symlink_to(secret)  # swapped for a link to a key after the yes
    with pytest.raises(NotShareable):
        read(out, home=home, milo=home / "Milo")
    f.unlink()
    f.write_text("other text")  # or for another file
    with pytest.raises(NotShareable, match="changed while I asked"):
        read(out, home=home, milo=home / "Milo")


def test_the_guard_puts_settings_back_only_while_away(tmp_path):
    config, state, secrets = tmp_path / "config.toml", tmp_path / "messages.json", tmp_path / "secrets"
    config.write_text("[approvals.levels]\nsend = \"ask_first\"\n")
    state.write_text('{"owner": {"chat": "42"}}')
    secrets.mkdir()
    token = secrets / "telegram-token"
    token.write_text("1:abc")
    os.chmod(token, 0o600)
    told = []
    guard = SettingsGuard([config, state], [secrets], told.append)

    config.write_text("[approvals.levels]\nsend = \"change\"\n")
    assert guard.check(False) is False and not guard.on, "at the Mac nothing is guarded"
    assert guard.check(True) is False and guard.on, "the guard keeps what is there when it comes on"
    config.write_text("[approvals.levels]\nsend = \"read\"\n")
    state.write_text('{"owner": {"chat": "666"}}')
    token.write_text("2:evil")
    (secrets / "extra").write_text("new")
    assert guard.check(True) is True
    assert config.read_text() == "[approvals.levels]\nsend = \"change\"\n"
    assert state.read_text() == '{"owner": {"chat": "42"}}'
    assert token.read_text() == "1:abc" and token.stat().st_mode & 0o777 == 0o600
    assert not (secrets / "extra").exists() and told == [PUT_BACK]

    state.write_text('{"owner": {"chat": "42"}, "paused": true}')  # Milo's own save
    guard.refresh(state)
    assert guard.check(True) is False and "paused" in state.read_text()
    guard.check(False)
    config.write_text("changed at the Mac")
    assert guard.check(True) is False and config.read_text() == "changed at the Mac"
