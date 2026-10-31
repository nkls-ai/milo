"""Who Milo is signed in as at each service it is set up to use, for the Usage page.

Claude Code says it with `claude auth status` (JSON: loggedIn, authMethod, email, subscriptionType). Codex says only
how it is signed in, with `codex login status`. ElevenLabs tells its plan to a key with the `user_read` permission;
a key without it gets a plain "can't see" instead. Everything else runs on this Mac and needs no account.

Each check is bounded (a few seconds) and failures become an "unknown" row with the reason, never an exception.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from milo.config import Config
from milo.core.registry import ConfigError
from milo.core.secrets import SecretError, read_secret
from milo.core.usage import Account, merge

from .harness._binary import find_binary
from .harness.codex import BUNDLED_CODEX, user_codex_home

log = logging.getLogger("milo.accounts")

TIMEOUT_S = 5.0
SUBSCRIPTION_URL = "https://api.elevenlabs.io/v1/user/subscription"

Run = Callable[[list[str], dict[str, str]], tuple[int, str]]
"""Runs a command with extra environment and returns (exit code, stdout). Tests pass a fake."""

Fetch = Callable[[str, dict[str, str]], tuple[int, str]]
"""GETs a URL with headers and returns (status, body). Tests pass a fake."""

TALKING, TASKS, VOICE, HEARING, DICTATION = "Talking", "Tasks", "Milo's voice", "Hearing you", "Dictation"

CLAUDE_PLANS = {"max": "Max", "pro": "Pro", "team": "Team", "enterprise": "Enterprise", "free": "Free"}
LOCAL_VOICES = {"omnivoice": "OmniVoice", "say": "macOS voice"}


class CliAccounts:
    """AccountProbe for the parts config.toml picks: [chat], [harness], [tts] and [stt]."""

    def __init__(self, config: Config, home: Path, *, run: Run | None = None, fetch: Fetch | None = None):
        self._config = config
        self._home = home
        self._run = run or _run
        self._fetch = fetch or _fetch

    def accounts(self) -> list[Account]:
        self._asked: dict[str, tuple[int, str]] = {}
        found: list[Account] = []
        for part, uses in (("chat", TALKING), ("harness", TASKS)):
            try:
                name, options = self._config.pluggable(part)
            except ConfigError:
                continue
            if name in ("claude", "claude_live"):
                found.append(self._claude(options, uses))
            elif name == "codex":
                found.append(self._codex(options, uses))
            elif name == "openai_compat":
                found.append(_chat_api(options, uses))
        found += self._voice_and_hearing()
        return merge(found)

    # ---- the services

    def _claude(self, options: dict, uses: str) -> Account:
        try:
            binary = find_binary(str(options.get("binary") or ""), "claude", section="harness.claude")
        except ConfigError:
            return Account("Claude", (uses,), "unknown", detail="Claude Code isn't installed.")
        code, out = self._run([binary, "auth", "status"], {})
        try:
            status = json.loads(out)
        except ValueError:
            return Account("Claude", (uses,), "unknown", detail="Claude Code didn't say who is signed in.")
        if not status.get("loggedIn"):
            return Account("Claude", (uses,), "signed_out", detail="Run `claude` once and sign in.")
        method = str(status.get("authMethod") or "")
        plan = CLAUDE_PLANS.get(str(status.get("subscriptionType") or "").lower(), "")
        if not plan and method and method != "claude.ai":
            plan = "API key"
        return Account("Claude", (uses,), plan=plan, who=str(status.get("email") or ""),
                       detail=str(options.get("model") or ""))

    def _codex(self, options: dict, uses: str) -> Account:
        try:
            binary = find_binary(str(options.get("binary") or ""), "codex", (BUNDLED_CODEX,), section="harness.codex")
        except ConfigError:
            return Account("ChatGPT", (uses,), "unknown", detail="Codex isn't installed.")
        code, out = self._run([binary, "login", "status"], {"CODEX_HOME": str(user_codex_home())})
        text = out.strip().lower()
        if code != 0 or "not logged in" in text:
            return Account("ChatGPT", (uses,), "signed_out", detail="Run `codex login` and sign in.")
        if "api key" in text:
            return Account("OpenAI", (uses,), plan="API key", detail=str(options.get("model") or ""))
        return Account("ChatGPT", (uses,), detail=str(options.get("model") or "Signed in with ChatGPT"))

    def _voice_and_hearing(self) -> list[Account]:
        out: list[Account] = []
        tts, tts_options = self._pluggable("tts")
        if tts == "elevenlabs":
            out.append(self._elevenlabs(VOICE, tts_options))
        elif tts:
            out.append(Account("This Mac", (VOICE,), "local", detail=LOCAL_VOICES.get(tts, tts)))
        stt = self._config.stt
        if stt.talk == "elevenlabs":
            out.append(self._elevenlabs(HEARING, self._config.section("stt").get("elevenlabs", {})))
        cloud_dictation = stt.cloud_dictation and stt.talk == "elevenlabs"
        if cloud_dictation:
            out.append(Account("ElevenLabs", (DICTATION,)))
        local = tuple(u for u, here in ((HEARING, not stt.talk), (DICTATION, not cloud_dictation)) if here)
        if local:
            out.append(Account("This Mac", local, "local", detail="Whisper, nothing leaves the Mac"))
        return out

    def _elevenlabs(self, uses: str, options: dict) -> Account:
        key_file = Path(str(options.get("key_file") or "")).expanduser() if options.get("key_file") \
            else self._home / "secrets" / "elevenlabs.key"
        try:
            key = read_secret(key_file, "The ElevenLabs key")
        except SecretError as e:
            return Account("ElevenLabs", (uses,), "signed_out", detail=str(e))
        if key not in self._asked:  # the voice and Scribe share one account: ask once per check
            self._asked[key] = self._fetch(SUBSCRIPTION_URL, {"xi-api-key": key})
        status, body = self._asked[key]
        if status == 200:
            try:
                sub = json.loads(body)
                used, limit = int(sub.get("character_count") or 0), int(sub.get("character_limit") or 0)
            except (ValueError, TypeError, AttributeError):
                return Account("ElevenLabs", (uses,), detail="Signed in")
            plan = str(sub.get("tier") or "").replace("_", " ").title()
            detail = f"{used:,} of {limit:,} credits used this month" if limit else ""
            return Account("ElevenLabs", (uses,), plan=plan, detail=detail)
        if status == 401 and "user_read" in body:
            return Account("ElevenLabs", (uses,), "unknown",
                           detail="Can't see the plan: the API key lacks the user_read permission.")
        if status == 401:
            return Account("ElevenLabs", (uses,), "signed_out", detail="ElevenLabs refused the API key.")
        return Account("ElevenLabs", (uses,), "unknown", detail="Couldn't reach ElevenLabs.")

    def _pluggable(self, section: str) -> tuple[str, dict]:
        try:
            return self._config.pluggable(section)
        except ConfigError:
            return "", {}


def _run(cmd: list[str], env: dict[str, str]) -> tuple[int, str]:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, env={**os.environ, **env},
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.info("account check %s failed: %s", Path(cmd[0]).name, type(e).__name__)
        return -1, ""
    # codex prints its status on stderr
    return done.returncode, done.stdout or done.stderr


def _fetch(url: str, headers: dict[str, str]) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 - fixed https URL
            return response.status, response.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(65536).decode("utf-8", "replace")
    except (OSError, ValueError) as e:
        log.info("ElevenLabs account check failed: %s", type(e).__name__)
        return 0, ""


def _chat_api(options: dict, uses: str) -> Account:
    """[chat] openai_compat: the provider by its host, with a key or local. Asking who the key belongs to differs
    from provider to provider, so it isn't asked."""
    url = urlsplit(str(options.get("base_url") or "https://api.openai.com/v1"))
    host = url.hostname or "?"
    local = host in ("localhost", "127.0.0.1", "::1")
    return Account(host, (uses,), "local" if local else "ok", plan="" if local else "API key" if options.get("key_ref")
                   else "", detail=str(options.get("model") or ""))
