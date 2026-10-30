"""Milo's brain process. The macOS app connects over a Unix socket; see protocol/messages.json."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from pathlib import Path
from typing import TYPE_CHECKING

from .core.registry import ConfigError

if TYPE_CHECKING:
    from .compose import Runtime

log = logging.getLogger("milo")

DEFAULT_HOME = "~/Milo"
NOISY_LOGGERS = ("httpx", "httpx2", "huggingface_hub")
CLOSE_TIMEOUT_S = 3.0

Warmup = tuple[Executor, Callable[[], None]] | Callable[[], Awaitable[None]]
"""A blocking warm() and the executor it must run on, or a coroutine function run on the loop."""


def main() -> None:
    from .memory.workspace import Workspace

    home = Path(os.environ.get("MILO_HOME", DEFAULT_HOME)).expanduser()
    workspace = Workspace(home)
    workspace.ensure()
    _setup_logging(workspace.log_dir / "brain.log")

    from . import compose

    try:
        runtime = compose.build(home)
    except ConfigError as e:
        log.error("config error: %s", e)
        raise SystemExit(f"config error: {e}") from None
    try:
        asyncio.run(_serve(runtime))
    except KeyboardInterrupt:
        pass


def _setup_logging(log_file: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file)],
    )
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)


async def _serve(runtime: Runtime) -> None:
    await runtime.server.start()
    log.info("brain up (chat=%s, harness=%s)", runtime.live_model.name, runtime.harness.name)
    warming = asyncio.create_task(_warm_all({
        "stt": (runtime.stt_executor, runtime.transcriber.warm),
        "tts": (runtime.tts_executor, runtime.voice.warm),
        # Starts the chat model's process with the system prompt now, saving 1-2 s on the first turn.
        "chat": runtime.live_talk.warm,
    }))
    tasks = [warming] + ([asyncio.create_task(runtime.heartbeat.run())] if runtime.heartbeat else [])
    try:
        await runtime.server.serve_forever()
    finally:
        for task in tasks:
            task.cancel()
        runtime.stt_executor.shutdown(wait=False, cancel_futures=True)
        runtime.tts_executor.shutdown(wait=False, cancel_futures=True)
        await _close(runtime)


async def _close(runtime: Runtime) -> None:
    try:
        await asyncio.wait_for(runtime.live_model.close(), CLOSE_TIMEOUT_S)
    except Exception:
        log.exception("closing the chat model failed")


async def _warm_all(engines: dict[str, Warmup]) -> None:
    """Load models in parallel, each blocking one on its engine's own thread, so the socket is up immediately.

    Readiness is logged only after all of them finish: OmniVoice calls logging.disable(INFO)
    process-wide while it loads, which silently swallows INFO lines from the other threads.
    """
    loop = asyncio.get_running_loop()
    names = list(engines)

    def start(warmup: Warmup) -> Awaitable[None]:
        return loop.run_in_executor(*warmup) if isinstance(warmup, tuple) else warmup()

    results = await asyncio.gather(*(start(w) for w in engines.values()), return_exceptions=True)
    for name, result in zip(names, results):
        if isinstance(result, BaseException):
            log.error("%s engine failed to load", name, exc_info=result)
        else:
            log.info("%s engine ready", name)


if __name__ == "__main__":
    main()
