import json

import pytest

from milo.adapters.accounts import SUBSCRIPTION_URL, CliAccounts
from milo.config import Config
from milo.core.usage import Account

CLAUDE_MAX = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": "you@example.com",
                         "subscriptionType": "max"})
NO_USER_READ = json.dumps({"detail": {"status": "missing_permissions",
                                      "message": "The API key you used is missing the permission user_read"}})


class Fakes:
    def __init__(self, claude=CLAUDE_MAX, codex=(0, "Logged in using ChatGPT"), eleven=(401, NO_USER_READ)):
        self.claude, self.codex, self.eleven = claude, codex, eleven
        self.runs: list[tuple[list[str], dict]] = []
        self.fetches: list[tuple[str, dict]] = []

    def run(self, cmd, env):
        self.runs.append((cmd, env))
        return (0, self.claude) if cmd[1:] == ["auth", "status"] else self.codex

    def fetch(self, url, headers):
        self.fetches.append((url, headers))
        return self.eleven


@pytest.fixture
def home(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir(mode=0o700)
    (secrets / "elevenlabs.key").write_text("sk_test\n")
    (secrets / "elevenlabs.key").chmod(0o600)
    return tmp_path


def config(**stt) -> Config:
    return Config({"chat": {"use": "claude_live", "claude_live": {"binary": "/bin/claude"}},
                   "harness": {"use": "codex", "codex": {"binary": "/bin/codex"}},
                   "tts": {"use": "elevenlabs", "elevenlabs": {"voice_id": "v"}},
                   "stt": {"use": "mlx_whisper", **stt}})


def test_one_row_per_service_with_plan_and_what_it_is_for(home):
    fakes = Fakes()
    rows = CliAccounts(config(talk="elevenlabs"), home, run=fakes.run, fetch=fakes.fetch).accounts()
    assert rows == [
        Account("Claude", ("Talking",), plan="Max", who="you@example.com"),
        Account("ChatGPT", ("Tasks",), detail="Signed in with ChatGPT"),
        Account("ElevenLabs", ("Milo's voice", "Hearing you"), "unknown",
                detail="Can't see the plan: the API key lacks the user_read permission."),
        Account("This Mac", ("Dictation",), "local", detail="Whisper, nothing leaves the Mac")]
    assert fakes.fetches == [(SUBSCRIPTION_URL, {"xi-api-key": "sk_test"})], "one request, the key in a header"
    assert all("sk_test" not in " ".join(cmd) for cmd, _ in fakes.runs)


def test_a_key_that_may_read_the_plan_shows_it_and_the_credits(home):
    fakes = Fakes(eleven=(200, json.dumps({"tier": "starter", "character_count": 1200, "character_limit": 30000})))
    rows = CliAccounts(config(), home, run=fakes.run, fetch=fakes.fetch).accounts()
    eleven = next(r for r in rows if r.service == "ElevenLabs")
    assert eleven == Account("ElevenLabs", ("Milo's voice",), plan="Starter",
                             detail="1,200 of 30,000 credits used this month")
    assert next(r for r in rows if r.service == "This Mac").uses == ("Hearing you", "Dictation")


def test_signed_out_and_broken_answers_become_rows_not_errors(home):
    fakes = Fakes(claude=json.dumps({"loggedIn": False}), codex=(1, "Not logged in"), eleven=(0, ""))
    rows = {r.service: r for r in CliAccounts(config(), home, run=fakes.run, fetch=fakes.fetch).accounts()}
    assert rows["Claude"].state == rows["ChatGPT"].state == "signed_out"
    assert rows["ElevenLabs"] == Account("ElevenLabs", ("Milo's voice",), "unknown",
                                         detail="Couldn't reach ElevenLabs.")
    fakes = Fakes(claude="garbage")
    rows = {r.service: r for r in CliAccounts(config(), home, run=fakes.run, fetch=fakes.fetch).accounts()}
    assert rows["Claude"].state == "unknown"


def test_a_missing_key_is_signed_out_and_nothing_is_fetched(tmp_path):
    fakes = Fakes()
    rows = {r.service: r for r in CliAccounts(config(), tmp_path, run=fakes.run, fetch=fakes.fetch).accounts()}
    assert rows["ElevenLabs"].state == "signed_out" and fakes.fetches == []


def test_local_voice_needs_no_account(home):
    fakes = Fakes()
    raw = config()._raw | {"tts": {"use": "say"}}
    rows = CliAccounts(Config(raw), home, run=fakes.run, fetch=fakes.fetch).accounts()
    assert rows[-1] == Account("This Mac", ("Milo's voice", "Hearing you", "Dictation"), "local", detail="macOS voice")
    assert fakes.fetches == []
