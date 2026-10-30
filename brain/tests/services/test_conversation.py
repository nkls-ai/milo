import asyncio

import pytest

from milo.core.types import HarnessError
from milo.services.conversation import Conversation
from tests.fakes import FakeClock, FakeHarness, MemoryLedger


def make(*script, idle_reset_s=600):
    harness, ledger, clock = FakeHarness(*script), MemoryLedger(), FakeClock()
    return Conversation(harness, ledger, clock, idle_reset_s), harness, ledger, clock


def test_prompt_carries_time_and_frontmost_app():
    conv, *_ = make()
    assert conv.prompt("hi", "Xcode") == "[Thursday 2026-10-29 09:00, frontmost app: Xcode]\nhi"
    assert conv.prompt("hi", None) == "[Thursday 2026-10-29 09:00]\nhi"


def test_keeps_the_session_and_records_usage():
    conv, harness, ledger, _ = make("one", "two")
    asyncio.run(conv.chat("a", None))
    asyncio.run(conv.chat("b", None))
    assert [sid for _, sid in harness.calls] == [None, "s1"]
    assert [(src, name) for src, name, _ in ledger.entries] == [("chat", "fake"), ("chat", "fake")]
    assert ledger.entries[0][2].input_tokens == 100


def test_session_resets_after_idle():
    conv, harness, _, clock = make("one", "two", "three", idle_reset_s=600)
    asyncio.run(conv.chat("a", None))
    clock.advance(seconds=599)
    asyncio.run(conv.chat("b", None))
    clock.advance(seconds=601)
    asyncio.run(conv.chat("c", None))
    assert [sid for _, sid in harness.calls] == [None, "s1", None]


def test_resume_failure_retries_with_a_fresh_session():
    conv, harness, ledger, _ = make("one", HarnessError("session gone", transient=False), "fresh")
    asyncio.run(conv.chat("a", None))
    reply = asyncio.run(conv.chat("b", "Mail"))
    assert reply.say == "fresh"
    assert [sid for _, sid in harness.calls] == [None, "s1", None]
    assert harness.calls[1][0] == harness.calls[2][0]
    assert conv.session_id == "s3"
    assert len(ledger.entries) == 2


def test_failure_without_a_session_raises():
    conv, harness, ledger, _ = make(HarnessError("down", transient=True))
    with pytest.raises(HarnessError):
        asyncio.run(conv.chat("a", None))
    assert len(harness.calls) == 1 and ledger.entries == []


def test_proactive_calls_never_touch_the_chat_session():
    conv, harness, ledger, _ = make("chat", "nudge", "chat again")
    asyncio.run(conv.chat("a", None))
    asyncio.run(conv.proactive("word this nicely", None))
    asyncio.run(conv.chat("b", None))
    assert [sid for _, sid in harness.calls] == [None, None, "s1"]
    assert [src for src, _, _ in ledger.entries] == ["chat", "proactive", "chat"]
