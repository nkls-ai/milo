import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from milo.adapters.stt.mlx_whisper import is_hallucination
from milo.server import _warm_all


def test_readiness_is_logged_even_if_another_engine_disables_logging_while_loading(caplog):
    """OmniVoice calls logging.disable(INFO) process-wide while loading; that once hid 'stt ready'."""
    loading = threading.Event()
    stt_done = threading.Event()

    def tts_warm():
        logging.disable(logging.INFO)
        loading.set()
        stt_done.wait(2)
        logging.disable(logging.NOTSET)

    def stt_warm():
        loading.wait(2)
        stt_done.set()

    def broken_warm():
        raise RuntimeError("no model")

    caplog.set_level(logging.INFO, logger="milo")
    pools = [ThreadPoolExecutor(1) for _ in range(3)]
    asyncio.run(_warm_all({"tts": (pools[0], tts_warm), "stt": (pools[1], stt_warm), "x": (pools[2], broken_warm)}))
    messages = [r.getMessage() for r in caplog.records]
    assert "stt engine ready" in messages and "tts engine ready" in messages
    assert "x engine failed to load" in messages


def test_whisper_silence_hallucination_seen_on_this_mac():
    assert is_hallucination("Closed Captioning by www.microsoft.com")


def test_an_async_warmup_runs_on_the_loop_and_is_logged_with_the_others(caplog):
    started = []

    async def chat_warm():
        started.append("chat")

    async def broken_chat():
        raise RuntimeError("claude missing")

    caplog.set_level(logging.INFO, logger="milo")
    pool = ThreadPoolExecutor(1)
    asyncio.run(_warm_all({"stt": (pool, lambda: None), "chat": chat_warm, "other": broken_chat}))
    messages = [r.getMessage() for r in caplog.records]
    assert started == ["chat"]
    assert messages == ["stt engine ready", "chat engine ready", "other engine failed to load"]


def test_a_background_loop_that_crashes_is_logged_and_started_again(caplog):
    # M10: one bad tick used to end the loop for the brain's life, with nothing in the log until exit.
    from milo.server import supervised

    runs = []

    async def flaky():
        runs.append(len(runs))
        if len(runs) < 3:
            raise RuntimeError(f"bad tick {len(runs)}")
        await asyncio.sleep(10)

    async def main():
        task = asyncio.create_task(supervised("the heartbeat", flaky, restart_s=(0.01, 0.02)))
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "cancelled"

    assert asyncio.run(main()) == "cancelled", "cancelling still stops it"
    assert runs == [0, 1, 2]
    assert caplog.text.count("the heartbeat crashed; starting it again") == 2 and "bad tick 1" in caplog.text


def test_a_failing_check_doesnt_end_the_every_loop(caplog):
    from milo import server

    calls = []

    async def check():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the guard broke once")

    async def main():
        task = asyncio.create_task(server._every(0.01, check))
        await asyncio.sleep(0.1)
        task.cancel()

    asyncio.run(main())
    assert len(calls) >= 3 and "the guard broke once" in caplog.text


def test_a_loop_that_stops_turning_logs_where_it_is(caplog):
    """A blocking call on the loop froze Milo with nothing in the log: no message was read until it returned."""
    import time

    from milo.server import _watch_loop

    def scanning_another_apps_folder():
        time.sleep(2.5)

    async def run():
        _watch_loop(asyncio.get_running_loop(), after_s=1.0)
        await asyncio.sleep(0)
        scanning_another_apps_folder()

    with caplog.at_level(logging.WARNING, logger="milo"):
        asyncio.run(run())
    assert any("not turned" in r.getMessage() and "scanning_another_apps_folder" in r.getMessage()
               for r in caplog.records)
