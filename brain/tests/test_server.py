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
