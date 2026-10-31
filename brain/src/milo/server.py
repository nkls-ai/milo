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
MESSAGES_TICK_S = 30.0

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


def _log_tasks() -> None:
    """Every running task and where it waits, into brain.log."""
    import io

    tasks = asyncio.all_tasks()
    out = io.StringIO()
    for task in sorted(tasks, key=lambda t: t.get_name()):
        task.print_stack(limit=8, file=out)
    log.warning("%d tasks, on SIGUSR1:\n%s", len(tasks), out.getvalue())


async def _serve(runtime: Runtime) -> None:
    # The app stops its brain with SIGTERM (uv passes that on, not SIGINT). Shut down as for Ctrl-C.
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)
    # `kill -USR1 <brain>` logs what every task is waiting on: a stuck turn can be read without a debugger,
    # which needs root on macOS. Only where the signal exists.
    if (dump := getattr(signal, "SIGUSR1", None)) is not None:  # Windows has none
        asyncio.get_running_loop().add_signal_handler(dump, _log_tasks)
    for notice in runtime.notices:
        notice.loop = asyncio.get_running_loop()
    if runtime.meetings is not None:
        # Before the socket opens: the app says first thing whether it still records a meeting a crash left open.
        runtime.meetings.start()
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
    loops: dict[str, Callable[[], Awaitable[None]]] = {}
    if runtime.heartbeat is not None:
        loops["the heartbeat"] = runtime.heartbeat.run
    if memory is not None and memory.sleep is not None:
        loops["the nightly consolidation"] = memory.sleep.run
    if runtime.barge_in is not None:
        loops["barge-in"] = runtime.barge_in.run
    if runtime.messages is not None:
        loops["messages"] = runtime.messages.run
        if runtime.heartbeat is None:  # the brief and the settings guard still need their tick
            messages = runtime.messages
            loops["the messages tick"] = lambda: _every(MESSAGES_TICK_S, messages.tick)
    tasks = [warming, *(asyncio.create_task(supervised(name, run)) for name, run in loops.items())]
    try:
        await runtime.server.serve_forever()
    finally:
        for task in tasks:
            task.cancel()
        runtime.stt_executor.shutdown(wait=False, cancel_futures=True)
        runtime.tts_executor.shutdown(wait=False, cancel_futures=True)
        if runtime.diarize_executor is not None:
            runtime.diarize_executor.shutdown(wait=False, cancel_futures=True)
        if runtime.meetings is not None:
            await runtime.meetings.close()
        if memory is not None:
            memory.memory.close()  # queued behind whatever the memory thread is doing
            memory.executor.shutdown(wait=False)
        await runtime.tool_server.close()
        await _close(runtime)


RESTART_S = (1.0, 5.0, 30.0, 60.0)
"""How long a crashed background loop waits before it starts again, growing with each crash in a row."""
STEADY_S = 600.0
"""A loop that ran this long before it crashed starts from the shortest wait again."""


async def supervised(name: str, run: Callable[[], Awaitable[None]], restart_s: tuple[float, ...] = RESTART_S) -> None:
    """Run a background loop for the brain's whole life. One that crashes is logged and started again, so one
    bad tick doesn't end the heartbeat (or the brief, or the settings guard) until the next restart."""
    loop = asyncio.get_running_loop()
    crashes = 0
    while True:
        started = loop.time()
        try:
            await run()
        except asyncio.CancelledError:
            raise
        except Exception:
            crashes = 1 if loop.time() - started >= STEADY_S else crashes + 1
            wait = restart_s[min(crashes, len(restart_s)) - 1]
            log.exception("%s crashed; starting it again in %.0f s", name, wait)
            await asyncio.sleep(wait)
        else:
            log.warning("%s stopped by itself", name)
            return


async def _every(seconds: float, check: Callable[[], Awaitable[None]]) -> None:
    while True:
        await asyncio.sleep(seconds)
        try:
            await check()
        except Exception:
            log.exception("a background check failed; trying again in %.0f s", seconds)


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
