"""Name -> factory registries for every swappable part.

An implementation registers itself where it is defined:

    @HARNESSES.register("codex")
    def _codex(options: Mapping[str, Any], ctx: AdapterContext) -> Harness:
        return CodexHarness(..., **options_from(CodexOptions, options, "harness.codex"))

config.toml picks one by name (`[harness] use = "codex"`) and passes the matching table
(`[harness.codex]`) as `options`. Adding an engine means adding a module, not editing a switch.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from .control import WORK_FOLDER

if TYPE_CHECKING:
    from .ports import (AudioInput, AudioOutput, CallDiarizer, Channel, Clock, Connections, Diarizer, Embedder, Harness,
                        Home, LiveModel, ProactiveRule, StreamingTranscriber, TextCleaner, Transcriber, Voice)
    from .ports import Weather
    from .types import ToolServer

T = TypeVar("T")
O = TypeVar("O")


class ConfigError(ValueError):
    """config.toml names something that does not exist or has a bad value. Tell the user which key."""


@dataclass(frozen=True)
class AdapterContext:
    """What every factory may use besides its own options."""

    home: Path
    state_dir: Path
    clock: Clock
    mac_tools: tuple[str, ...] = ()
    """The command that starts the milo-mac MCP server for the worker harness. Empty: no Mac tools."""
    tool_servers: tuple[ToolServer, ...] = ()
    """MCP servers the worker harness gives its agent (Milo's app connections)."""

    @property
    def worker_dir(self) -> Path:
        """Where a worker harness runs: the only folder of the workspace its sandbox may write (ADR 0020)."""
        return self.home / WORK_FOLDER


Factory = Callable[[Mapping[str, Any], AdapterContext], T]


class Registry(Generic[T]):
    def __init__(self, kind: str):
        self.kind = kind
        self._factories: dict[str, Factory[T]] = {}

    def register(self, name: str) -> Callable[[Factory[T]], Factory[T]]:
        def decorator(factory: Factory[T]) -> Factory[T]:
            if name in self._factories:
                raise ValueError(f"{self.kind} {name!r} registered twice")
            self._factories[name] = factory
            return factory

        return decorator

    def create(self, name: str, options: Mapping[str, Any], ctx: AdapterContext) -> T:
        try:
            factory = self._factories[name]
        except KeyError:
            raise ConfigError(f"unknown {self.kind} {name!r}; available: {', '.join(self.names())}") from None
        return factory(options, ctx)

    def names(self) -> list[str]:
        return sorted(self._factories)


def options_from(cls: type[O], options: Mapping[str, Any], section: str) -> O:
    """Build an options dataclass from a TOML table, rejecting unknown keys (typos fail loudly)."""
    fields = {f.name: f for f in dataclasses.fields(cls)}
    unknown = sorted(set(options) - set(fields))
    if unknown:
        raise ConfigError(f"unknown key(s) in [{section}]: {', '.join(unknown)}")
    values = {k: tuple(v) if isinstance(v, list) else v for k, v in options.items()}
    try:
        return cls(**values)
    except TypeError as e:
        raise ConfigError(f"bad value in [{section}]: {e}") from None


HARNESSES: Registry[Harness] = Registry("harness")
LIVE_MODELS: Registry[LiveModel] = Registry("chat model")
TRANSCRIBERS: Registry[Transcriber] = Registry("stt engine")
STREAMING_TRANSCRIBERS: Registry[StreamingTranscriber] = Registry("streaming stt engine")
VOICES: Registry[Voice] = Registry("tts engine")
AUDIO_INPUTS: Registry[AudioInput] = Registry("audio input")
AUDIO_OUTPUTS: Registry[AudioOutput] = Registry("audio output")
TEXT_CLEANERS: Registry[TextCleaner] = Registry("dictation cleaner")
RULES: Registry[ProactiveRule] = Registry("heartbeat rule")
CONNECTIONS: Registry[Connections] = Registry("connections")
HOMES: Registry[Home] = Registry("home")
EMBEDDERS: Registry[Embedder] = Registry("embedder")
CHANNELS: Registry[Channel] = Registry("message channel")
DIARIZERS: Registry[Diarizer] = Registry("diarizer")
CALL_DIARIZERS: Registry[CallDiarizer] = Registry("call diarizer")
WEATHER: Registry[Weather] = Registry("weather service")
