import asyncio

import pytest

from milo.core.events import ConfirmEnd, ConfirmRequest, HandsRequest, LookRequest
from milo.core.types import HandsError
from milo.services.app_bridge import NO_APP, AppBridge, AppEyes, AppHands, BubbleConfirm
from tests.fakes import RecordingSink


def test_a_look_nobody_answers_comes_back_as_an_error():
    sink = RecordingSink()
    capture = asyncio.run(AppEyes(AppBridge(sink), timeout_s=0.01).look())
    assert sink.events == [LookRequest("look-1", "window")]
    assert capture.empty and "too long" in capture.error


def test_without_an_app_nothing_is_sent():
    sink = RecordingSink()
    bridge = AppBridge(sink, connected=lambda: False)
    assert asyncio.run(AppEyes(bridge).look()).error == NO_APP
    with pytest.raises(HandsError, match="isn't connected"):
        asyncio.run(AppHands(bridge).act("list_apps", {}))
    assert asyncio.run(BubbleConfirm(bridge, sink).confirm("Send it?")) is False
    assert sink.events == []


def test_a_failed_action_raises_with_the_apps_words():
    sink = RecordingSink()
    bridge = AppBridge(sink)

    async def run():
        acting = asyncio.create_task(AppHands(bridge).act("ax_press", {"element": "e9"}))
        await asyncio.sleep(0)
        bridge.answer("hands-1", (False, {}, "There is no element e9."))
        await acting

    with pytest.raises(HandsError, match="no element e9"):
        asyncio.run(run())
    assert sink.events == [HandsRequest("hands-1", "ax_press", {"element": "e9"})]


def test_cancel_ends_waiting_actions_with_an_error():
    bridge = AppBridge(RecordingSink())

    async def run():
        acting = asyncio.create_task(AppHands(bridge).act("click", {"x": 1, "y": 1}))
        await asyncio.sleep(0)
        bridge.cancel("hands")
        await acting

    with pytest.raises(HandsError, match="stopped"):
        asyncio.run(run())


def test_an_unanswered_question_is_a_no_and_its_buttons_go_away():
    sink = RecordingSink()
    assert asyncio.run(BubbleConfirm(AppBridge(sink), sink, timeout_s=0.01).confirm("Send it?")) is False
    assert sink.events == [ConfirmRequest("confirm-1", "Send it?"), ConfirmEnd("confirm-1")]


def test_late_or_unknown_answers_are_dropped():
    AppBridge(RecordingSink()).answer("look-7", None)
