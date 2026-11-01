"""Explicit provider setup, independent of widgets, network calls and model loading."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from milo.adapters.harness._binary import executable_command, find_binary
from milo.config_file import TomlConfigFile
from milo.core.registry import ConfigError
from milo.core.secrets import SecretError, write_secret
from milo.core.types import HarnessError


@dataclass(frozen=True)
class CliStatus:
    available: bool
    path: str = ""
    detail: str = ""


@dataclass(frozen=True)
class ProviderSelection:
    chat: str = "claude_live"
    helper: str = "codex"
    endpoint: str = ""
    model: str = ""
    key_ref: str = ""


def detect_cli(name: str, configured: str, section: str) -> CliStatus:
    """Inspect executable paths only. Never execute logins, auth checks or network commands."""
    try:
        from milo.adapters.harness.codex import BUNDLED_CODEX
        path = find_binary(configured, name, (BUNDLED_CODEX,) if name == "codex" else (), section=section)
        if not Path(path).is_file() and not shutil.which(path):
            return CliStatus(False, detail="Not installed or the configured path is missing")
        command = executable_command(path)
        if not Path(command[0]).is_file() and not shutil.which(command[0]):
            return CliStatus(False, detail="The CLI's runtime was not found")
        return CliStatus(True, path=path, detail="Installed; account sign-in is checked when you use it")
    except (ConfigError, HarnessError, OSError) as error:
        return CliStatus(False, detail=str(error))


class ProviderSetup:
    """Reads current choices without changing them. Only save() commits a user's choice."""
    def __init__(self, config_file: TomlConfigFile, *, detector=detect_cli):
        self.file = config_file
        self._detect = detector
        self.error = ""
        self.selection = ProviderSelection()
        self.clis: dict[str, CliStatus] = {}
        self.reload()

    def reload(self):
        self.error = ""
        try:
            config = self.file.read()
            chat, _ = config.pluggable("chat")
            helper, _ = config.pluggable("harness")
            raw_chat, raw_helper = config.section("chat"), config.section("harness")
            api = raw_chat.get("openai_compat", {})
            self.selection = ProviderSelection(chat, helper, str(api.get("base_url", "")),
                                               str(api.get("model", "")), str(api.get("key_ref", "")))
            self.clis = {
                "chat_claude": self._detect("claude", raw_chat.get("claude_live", {}).get("binary", ""), "chat.claude_live"),
                "chat_codex": self._detect("codex", raw_chat.get("codex_live", {}).get("binary", ""), "chat.codex_live"),
                "helper_codex": self._detect("codex", raw_helper.get("codex", {}).get("binary", ""), "harness.codex"),
                "helper_claude": self._detect("claude", raw_helper.get("claude", {}).get("binary", ""), "harness.claude"),
            }
        except (ConfigError, OSError) as error:
            self.error = f"Couldn't read config.toml: {error}. Fix that file before saving provider settings."

    @property
    def needs_setup(self) -> bool:
        if self.error:
            return True
        try:
            self.validate(self.selection)
        except ConfigError:
            return True
        return False

    def secret_path(self, key_ref: str) -> Path:
        """Where `[chat.openai_compat] key_ref` points: a file in the Milo folder's secrets."""
        return self.file.path.parent / "secrets" / key_ref

    def validate(self, choice: ProviderSelection, *, key: str = ""):
        """`key`: one the user pasted and save() will write, so the secret file needn't be there yet."""
        if self.error:
            raise ConfigError(self.error)
        if choice.chat == "claude_live" and not self.clis.get("chat_claude", CliStatus(False)).available:
            raise ConfigError("Claude CLI wasn't found. Install and sign in to it, check again, or choose another talking provider.")
        if choice.chat == "codex_live" and not self.clis.get("chat_codex", CliStatus(False)).available:
            raise ConfigError("Codex CLI wasn't found. Install it, run codex login, and check again, or choose another talking provider.")
        required = {"codex": "helper_codex", "claude": "helper_claude"}.get(choice.helper)
        if required and not self.clis.get(required, CliStatus(False)).available:
            raise ConfigError("The selected helper CLI wasn't found. Install it and check again, or choose Disabled.")
        if choice.chat == "openai_compat":
            try:
                url = urlsplit(choice.endpoint.strip())
                valid_url = (url.scheme in ("http", "https") and bool(url.hostname) and
                             not url.username and not url.password and not url.query and not url.fragment)
                url.port  # Validate a malformed port without making a connection.
            except ValueError:
                valid_url = False
            if not valid_url:
                raise ConfigError("Enter an http:// or https:// API base URL without a password, API key or query string.")
            if not choice.model.strip() or len(choice.model) > 200 or any(c in choice.model for c in "\r\n\0"):
                raise ConfigError("Enter the model name your API server or provider supplies.")
            if choice.key_ref and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", choice.key_ref):
                raise ConfigError("Enter only a secret file name, such as provider.key. Put the API key in that file yourself.")
            if key.strip() and not choice.key_ref:
                raise ConfigError("Name the file the key goes in, such as provider.key.")

    def save(self, choice: ProviderSelection, *, key: str = ""):
        """Writes the choice; a pasted `key` goes alone into its secret file first, never into config.toml."""
        self.validate(choice, key=key)
        if choice.chat == "openai_compat" and key.strip():
            try:
                write_secret(self.secret_path(choice.key_ref), key, "The API key")
            except SecretError as e:
                raise ConfigError(str(e)) from None
        changes = [("chat", "use", choice.chat), ("harness", "use", choice.helper)]
        if choice.chat == "openai_compat":
            changes += [("chat.openai_compat", "base_url", choice.endpoint.strip()),
                        ("chat.openai_compat", "model", choice.model.strip()),
                        ("chat.openai_compat", "key_ref", choice.key_ref)]
        result = self.file.write_many(changes)
        self.selection = choice
        return result
