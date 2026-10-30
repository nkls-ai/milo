import asyncio

import pytest

from milo.core.events import AppRequest, AppResponse, HandsRequest, LookRequest
from milo.core.types import HandsError
from milo.services.app_bridge import APP_LEFT_WORDS, NO_APP, NOT_RUNNING, AppBridge, AppError, AppEyes, AppHands
from tests.fakes import RecordingSink


def test_a_look_nobody_answers_comes_back_as_an_error():
    sink = RecordingSink()
    capture = asyncio.run(AppEyes(AppBridge(sink), timeout_s=0.01).look())
    assert sink.events == [LookRequest("look-1", "window")]
    assert capture.empty and "too long" in capture.error


def test_without_an_app_nothing_is_sent():
    sink = RecordingSink(app=None)
    bridge = AppBridge(sink)
    assert asyncio.run(AppEyes(bridge).look()).error == NO_APP
    with pytest.raises(HandsError, match="isn't connected"):
        asyncio.run(AppHands(bridge).act("list_apps", {}))
    with pytest.raises(AppError, match=NOT_RUNNING):
        asyncio.run(bridge.call("reminders.list", {}))
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


def test_app_work_and_mac_actions_wait_side_by_side_without_crossing():
    sink = RecordingSink()
    bridge = AppBridge(sink)

    async def run():
        acting = asyncio.create_task(AppHands(bridge).act("list_apps", {}))
        listing = asyncio.create_task(bridge.call("reminders.list", {}))
        await asyncio.sleep(0)
        bridge.resolve(AppResponse("app-2", True, [{"title": "Milk"}]))
        bridge.answer("hands-1", (True, {"text": "Mail"}, ""))
        return await acting, await listing

    assert asyncio.run(run()) == ({"text": "Mail"}, [{"title": "Milk"}])
    assert sink.events == [HandsRequest("hands-1", "list_apps", {}), AppRequest("app-2", "reminders.list", {})]


def test_late_or_unknown_answers_are_dropped():
    AppBridge(RecordingSink()).answer("look-7", None)


def test_an_app_that_hangs_up_fails_what_it_owed_at_once_and_only_that():
    # M3 in docs/review/2026-10-30.md: requests waited out their whole timeout (up to 90 s) after the app left.
    sink = RecordingSink(app=1)
    bridge = AppBridge(sink, timeout_s=60)

    async def run():
        acting = asyncio.create_task(AppHands(bridge, timeout_s=60).act("list_apps", {}))
        listing = asyncio.create_task(bridge.call("reminders.list", {}))
        await asyncio.sleep(0)
        sink.app = 2  # a new app connected; requests from now on go to it
        looking = asyncio.create_task(AppEyes(bridge, timeout_s=60).look())
        await asyncio.sleep(0)
        bridge.app_gone(1)
        results = await asyncio.gather(acting, listing, return_exceptions=True)
        assert not looking.done(), "the new app still owes its look"
        bridge.answer("look-3", None)
        return results, await looking

    loop_started = asyncio.new_event_loop()
    try:
        (hands, app), look = loop_started.run_until_complete(asyncio.wait_for(run(), 2))
    finally:
        loop_started.close()
    assert isinstance(hands, HandsError) and "closed" in str(hands)
    assert isinstance(app, AppError) and str(app) == APP_LEFT_WORDS
