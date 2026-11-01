"""Which engines a computer gets when config.toml doesn't name one (ADR 0027).

A `Platform` is plain data: adapter names by config section. The values for each OS live in
`milo.adapters.platform`, which is the one place that asks what OS this is; compose passes the result to Config.
config.toml still overrides every name with `use = "..."`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    name: str
    """"macos", "linux" or "windows": for logs and for what an app says it is."""
    stt: str
    """[stt] use: the transcriber for dictation and for talking to Milo."""
    tts: str
    """[tts] use: his voice."""
    tts_fallback: str
    """[tts] fallback: the voice that takes over when `tts` fails. "": none."""
    embedder: str
    """[memory] embedder: what turns text into numbers for recall."""
    connections: str
    """[connections] use: calendar, reminders, mail, notes and files. "none" where Milo has none yet."""
    chat: str = "claude_live"
    """[chat] use: the talker's model. The Claude CLI runs everywhere."""
    messages: str = "telegram"
    """[messages] use: the phone channel. Telegram's bot API runs everywhere."""
    weather: str = "open_meteo"
    """[weather] use: the forecast in <today>. Open-Meteo needs no key and runs everywhere."""
    computer: str = "computer"
    """What Milo calls the machine he runs on in what he says ("while the computer was asleep")."""
    home: str = "auto"
    """[home] use: the home system. "auto" finds Home Assistant when it is configured, else this computer's own."""
    decide: str = "none"
    """[decide] use: the small model that reads what the user asked for (ADR 0040). "none": nothing counts as asked,
    so after outside text Milo asks first."""
    tool_dirs: tuple[str, ...] = ()
    """Where package managers live besides PATH, which is bare when the app starts the brain (install_package)."""

    def use(self, section: str) -> str | None:
        """The default `use` for a pluggable config section, None for sections that must name one."""
        return {"chat": self.chat, "stt": self.stt, "tts": self.tts, "connections": self.connections,
                "messages": self.messages, "weather": self.weather, "home": self.home,
                "decide": self.decide}.get(section)


ANYWHERE = Platform("other", stt="elevenlabs", tts="elevenlabs", tts_fallback="", embedder="hash",
                    connections="none")
"""Engines that need nothing from the OS: cloud hearing and voice (keys in ~/Milo/secrets), the hashing embedder,
no connections. What Linux and Windows get until they have local engines of their own."""
