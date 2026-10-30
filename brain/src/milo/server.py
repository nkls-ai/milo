"""Milo's brain process. The macOS app connects over a Unix socket; see protocol/messages.json."""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from pathlib import Path
from typing import TYPE_CHECKING

from .config import Config, LoggingSettings
from .core.logtext import log_content
from .core.registry import ConfigError
from .transport import instance_lock

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
    try:
        settings = Config.load(workspace.config_path).logging
    except (ConfigError, OSError):
        settings = LoggingSettings()  # compose.build reports the error once logging is up
    _setup_logging(workspace.log_dir / "brain.log", settings)
    # Before anything heavy loads. Held until the process is gone, models and all.
    try:
        instance_lock.acquire(workspace.lock_path)
    except instance_lock.AlreadyRunning as e:
        log.error("%s", e)
        raise SystemExit(str(e)) from None

    from . import compose

    try:
        runtime = compose.build(home)
    except ConfigError as e:
        log.error("config error: %s", e)
        raise SystemExit(f"config error: {e}") from None
    try:
        asyncio.run(_serve(runtime))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    log.info("brain stopped")
    # Skip joining the STT and TTS threads: one may be loading a model for another 30 s, and the app
    # waits for this process to end before it starts the next brain.
    logging.shutdown()
    os._exit(0)


def _setup_logging(log_file: Path, settings: LoggingSettings) -> None:
    """brain.log rotates at max_mb. A terminal also gets the lines; the app's stdout log only gets crashes."""
    handlers: list[logging.Handler] = [logging.handlers.RotatingFileHandler(
        log_file, maxBytes=int(settings.max_mb * 1024 * 1024), backupCount=max(0, settings.keep), encoding="utf-8")]
    if sys.stderr.isatty():
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=handlers)
    log_content(settings.content)
    if settings.content:
        log.warning("content logging is on: brain.log keeps what you say ([logging] content in config.toml)")
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)


async def _serve(runtime: Runtime) -> None:
    # The app stops its brain with SIGTERM (uv passes that on, not SIGINT). Shut down as for Ctrl-C.
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)
    for notice in runtime.notices:
        notice.loop = asyncio.get_running_loop()
    await runtime.server.start()
    await runtime.tool_server.start()
    if runtime.hands_server is not None:
        await runtime.hands_server.start()
    log.info("brain up (chat=%s, harness=%s)", runtime.live_model.name, runtime.harness.name)
    engines: dict[str, Warmup] = {
        "stt": (runtime.stt_executor, runtime.transcriber.warm),
        "tts": (runtime.tts_executor, runtime.voice.warm),
        # Queued behind the voice on the one TTS thread: the "Hm." clips for slow replies, in his voice.
        **({"backchannels": (runtime.tts_executor, runtime.backchannel.warm)} if runtime.backchannel else {}),
        # Starts the chat model's process with the system prompt now, saving 1-2 s on the first turn.
        "chat": runtime.live_talk.warm,
    }
    memory = runtime.memory
    if memory is not None:
        engines["memory"] = memory.memory.warm  # the embedder on its own thread, then the index catches up
    warming = asyncio.create_task(_warm_all(engines))
    tasks = [warming] + ([asyncio.create_task(runtime.heartbeat.run())] if runtime.heartbeat else [])
    if memory is not None and memory.sleep is not None:
        tasks.append(asyncio.create_task(memory.sleep.run()))
    if runtime.barge_in is not None:
        tasks.append(asyncio.create_task(runtime.barge_in.run()))
    try:
        await runtime.server.serve_forever()
    finally:
        for task in tasks:
            task.cancel()
        runtime.stt_executor.shutdown(wait=False, cancel_futures=True)
        runtime.tts_executor.shutdown(wait=False, cancel_futures=True)
        if memory is not None:
            memory.memory.close()  # queued behind whatever the memory thread is doing
            memory.executor.shutdown(wait=False)
        await runtime.tool_server.close()
        await _close(runtime)


async def _close(runtime: Runtime) -> None:
    if runtime.helpers is not None:
        try:
            # Workers run in their own process groups, so they would outlive the brain.
            await asyncio.wait_for(runtime.helpers.close(), CLOSE_TIMEOUT_S)
        except Exception:
            log.exception("stopping the helpers failed")
    if runtime.hands_server is not None:
        await runtime.hands_server.close()
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
