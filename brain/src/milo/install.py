"""Getting Milo ready on a new computer: his speech models downloaded, and the subscription he thinks with chosen.

install.sh runs these after `uv sync`, so the first start doesn't sit for minutes downloading models:

    uv run python -m milo.install models
    uv run python -m milo.install configure --chat claude_live --harness codex

Nothing here knows which OS it runs on: `models` gets ready whatever this computer's engines are
(adapters/platform.py), built the way compose builds them, and `configure` changes keys in config.toml through
TomlConfigFile, comments kept.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Config
from .config_file import TomlConfigFile
from .core.clock import SystemClock
from .core.registry import EMBEDDERS, HARNESSES, LIVE_MODELS, TRANSCRIBERS, VOICES, AdapterContext, ConfigError
from .memory.workspace import Workspace

DEFAULT_HOME = "~/Milo"


@dataclass(frozen=True)
class Part:
    label: str
    """What the person installing reads: "Hearing", "Voice", "Memory"."""
    engine: str
    make: Callable[[], Any]


def parts(config: Config, ctx: AdapterContext) -> list[Part]:
    """The engines that download models, in the order install.sh shows them."""
    stt, stt_options = config.pluggable("stt")
    tts, tts_options = config.pluggable("tts")
    embedder, embedder_options = config.embedder()
    return [
        Part("Hearing", stt, lambda: TRANSCRIBERS.create(stt, stt_options, ctx)),
        Part("Voice", tts, lambda: VOICES.create(tts, tts_options, ctx)),
        Part("Memory", embedder, lambda: EMBEDDERS.create(embedder, embedder_options, ctx)),
    ]


def _setup(home: Path) -> tuple[Workspace, Config, AdapterContext]:
    from . import adapters
    from .adapters import platform

    workspace = Workspace(home)
    workspace.ensure()
    config = Config.load(workspace.config_path, platform.current())
    adapters.load_builtin()
    return workspace, config, AdapterContext(home, workspace.state_dir, SystemClock())


def models(home: Path, out=sys.stdout) -> int:
    """Create each engine and warm it, which downloads and loads its model. 1 if any failed, after trying all."""
    _, config, ctx = _setup(home)
    failed = 0
    for part in parts(config, ctx):
        print(f"{part.label} ({part.engine}): getting ready…", file=out, flush=True)
        started = time.monotonic()
        try:
            engine = part.make()
            warm = getattr(engine, "warm", None)
            if callable(warm):
                warm()
        except Exception as e:  # one engine failing shouldn't stop the others downloading
            failed += 1
            print(f"{part.label} ({part.engine}): failed: {e}", file=out, flush=True)
            continue
        print(f"{part.label} ({part.engine}): ready in {time.monotonic() - started:.0f} s", file=out, flush=True)
    return 1 if failed else 0


def configure(home: Path, *, chat: str = "", harness: str = "") -> Config:
    """Set `[chat] use` and `[harness] use`. An unknown name raises ConfigError and writes nothing."""
    from .adapters import platform

    workspace, _, _ = _setup(home)
    for name, registry in ((chat, LIVE_MODELS), (harness, HARNESSES)):
        if name and name not in registry.names():
            raise ConfigError(f"unknown {registry.kind} {name!r}; available: {', '.join(registry.names())}")
    file = TomlConfigFile(workspace.config_path, platform.current())
    config = file.read()
    if chat:
        config = file.write("chat", "use", chat)
    if harness:
        config = file.write("harness", "use", harness)
    return config


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m milo.install", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("models", help="download and load the speech and memory models")
    conf = sub.add_parser("configure", help="pick the chat model and the helpers' agent")
    conf.add_argument("--chat", default="", help="[chat] use: claude_live, openai_compat or none")
    conf.add_argument("--harness", default="", help="[harness] use: codex or claude")
    args = parser.parse_args(argv)
    # The models' own progress bars say enough; the engines' info lines would bury them.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    home = Path(os.environ.get("MILO_HOME", DEFAULT_HOME)).expanduser()
    if args.command == "models":
        return models(home)
    try:
        config = configure(home, chat=args.chat, harness=args.harness)
    except ConfigError as e:
        print(f"config: {e}", file=sys.stderr)
        return 2
    print(f"Milo talks with {config.pluggable('chat')[0]} and works with {config.pluggable('harness')[0]}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
