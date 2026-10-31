"""Stop for what can't be undone, not for everything (ADR 0023).

The user's rule: "He should stop before buying or anything involving money or destructive, and ask. Maybe
irreversibly destructive he has to ask, otherwise it can be annoying." And later, live: "when I asked him to make the
whole Excel red it takes a couple of permissions still, which is annoying. Maybe have no ask except for payment and
destructive the default mode."

So the line is whether it can be undone. Replacing cells, moving a file to the Trash and deleting a note (Notes keeps
Recently Deleted) are part of the work. Emptying the Trash, Don't Save, buying and a bank transfer stop and ask every
time, in every mode, and only a click answers a question about money.
"""

import asyncio

import pytest

from milo.core.events import Bubble, Confirm, ConfirmDone
from milo.core.types import ScreenCapture
from milo.services.approvals import ActionPolicy, MONEY_YES
from milo.services.permits import AppRef, Scope
from milo.services.risk import Risk, classify, normalize_combo
from tests.fakes import FakeChannel, FakeEyes, FakeHarness, FakeLiveModel
from tests.services.stack import Stack, settle
from tests.services.test_permits import EXCEL, EXCEL_WORK, ExcelApp, Worker, user, work

FINDER = {"app": "Finder", "bundle": "com.apple.finder"}
NOTES = {"app": "Notes", "bundle": "com.apple.Notes"}
SAFARI = {"app": "Safari", "bundle": "com.apple.Safari"}

# Things Milo can press, by element id (ax_press), and what a key combo touches.
ELEMENTS = {
    "note-delete": {**NOTES, "title": "Delete", "role": "button"},
    "dont-save": {**EXCEL, "title": "Don't Save", "role": "button"},
    "buy": {**SAFARI, "title": "Buy Now", "role": "button"},
    "transfer": {**SAFARI, "title": "Send transfer", "role": "button"},
    "replace-file": {**EXCEL, "title": "Replace", "role": "button"},
}
KEYS = {"cmd+delete": {**FINDER, "title": "Budget 2025 old.xlsx", "role": "file"},
        "shift+cmd+delete": FINDER, "option+cmd+delete": {**FINDER, "title": "Budget 2024.xlsx", "role": "file"}}


class Desk(ExcelApp):
    """The budget in Excel, with Finder, Notes and a shop and a bank in Safari next to it."""

    async def act(self, tool: str, args: dict) -> dict:
        if tool == "describe" and args["tool"] == "ax_press" and args.get("element") in ELEMENTS:
            self.calls.append((tool, args))
            return dict(ELEMENTS[args["element"]])
        if tool == "describe" and args["tool"] == "key" and normalize_combo(args["combo"]) in KEYS:
            self.calls.append((tool, args))
            return dict(KEYS[normalize_combo(args["combo"])])
        return await super().act(tool, args)


TIDY = [("key", {"combo": "cmd+delete"}),  # last year's copy to the Trash, in Finder
        ("ax_press", {"element": "note-delete"})]  # the old budget note, to Recently Deleted
"""What can be undone."""

FOR_GOOD = [("key", {"combo": "shift+cmd+delete"}), ("ax_press", {"element": "dont-save"}),
            ("ax_press", {"element": "buy"}), ("ax_press", {"element": "transfer"})]
"""Emptying the Trash, Don't Save, buying, a bank transfer."""


def desk(ask: str | None, *turns) -> tuple[Stack, Worker]:
    worker = Worker(*turns)
    s = Stack(harness=worker, background=FakeHarness(), hands_port=Desk(), **({"ask": ask} if ask else {}))
    return s, worker


# ---- the story


@pytest.mark.parametrize("ask, user_asked, questions", [
    ("step", False, 8),  # ADR 0022's six, plus the Trash and the note
    ("task", False, 1),  # ADR 0022's first one: "Replace 8 filled cells"
    ("auto", True, 0),
])
def test_the_excel_helper_trashes_a_file_and_deletes_a_note_without_extra_questions(ask, user_asked, questions):
    s, worker = desk(ask, [*EXCEL_WORK, *TIDY])
    [asked] = work(s, worker, "yes", user_asked=user_asked)
    assert len(asked) == questions, [c.question for c in asked]
    assert worker.errors == []
    assert s.hands_port.actions.count("key") == 2 and s.hands_port.actions.count("ax_press") == 1, "both done"
    if ask == "step":
        assert asked[-2].question == "I'm about to press ⌘Delete in Finder, which may move to the Trash. Go ahead?"
        assert asked[-1].question == "I'm about to click “Delete” in Notes. Go ahead?"


@pytest.mark.parametrize("ask, user_asked", [("step", False), ("task", False), ("auto", True)])
def test_emptying_the_trash_dont_save_buying_and_a_transfer_ask_every_time_in_every_mode(ask, user_asked):
    s, worker = desk(ask, [*EXCEL_WORK, *FOR_GOOD, *FOR_GOOD])
    [asked] = work(s, worker, "always", user_asked=user_asked)
    tail = [(c.question, c.always, c.money) for c in asked][-8:]
    expected = [
        ("I'm about to press ⇧⌘Delete in Finder, which may empty the Trash. Go ahead?", False, False),
        ("I'm about to click “Don't Save” in Microsoft Excel. Go ahead?", False, False),
        ("I'm about to click “Buy Now” in Safari. Go ahead?", False, True),
        ("I'm about to click “Send transfer” in Safari. Go ahead?", False, True),
    ] * 2
    assert tail == expected
    assert worker.errors == []
    # Allow always was clicked on the first Excel question, and wherever else it was offered: none of these offered it.
    assert all(a.label == "Microsoft Excel" for a in s.approvals.permits.always)


def test_a_money_question_offers_no_always_and_a_spoken_yes_doesnt_answer_it():
    s, worker = desk("auto", [("ax_press", {"element": "buy"})])
    worker.hands = s.hands

    async def run():
        s.tasks.submit("buy the budget template", screen=True, user_asked=True)
        await settle()
        [c] = s.sink.of(Confirm)
        assert c.money and not c.always
        await s.live_talk.start("yes")  # spoken: taken, but it isn't the yes
        await settle()
        assert s.sink.of(ConfirmDone) == [] and s.approvals.pending
        assert not s.approvals.answer(c.id, True, via="typed")
        assert not s.approvals.answer(c.id, True, via="message")
        s.approvals.answer(c.id, True, always=True)  # the button; always isn't offered, so it's a plain yes
        await s.tasks.idle()

    asyncio.run(run())
    assert [d.answer for d in s.sink.of(ConfirmDone)] == ["yes"]
    assert s.hands_port.actions.count("ax_press") == 1, "bought after the click"
    assert any(b.text == MONEY_YES for b in s.sink.of(Bubble)), "Milo says the button has to answer"
    assert s.approvals.permits.always == ()


def test_a_spoken_no_still_stops_a_money_question():
    s, worker = desk("auto", [("ax_press", {"element": "buy"})])
    worker.hands = s.hands

    async def run():
        s.tasks.submit("buy the budget template", screen=True, user_asked=True)
        await settle()
        await s.live_talk.start("no")
        await s.tasks.idle()

    asyncio.run(run())
    assert [d.answer for d in s.sink.of(ConfirmDone)] == ["no"]
    assert "ax_press" not in s.hands_port.actions


def test_password_and_card_fields_are_still_refused_in_auto_mode():
    card = {**SAFARI, "title": "Card number", "role": "text field"}
    cvv = {**SAFARI, "title": "CVV", "role": "text field"}
    turn = [("type", {"text": "hunter2"}), ("ax_set_value", {"element": "e1", "text": "4111 1111 1111 1111"}),
            ("ax_set_value", {"element": "e2", "text": "123"})]
    hands = Desk({"type": {**SAFARI, "secure": True}, "ax_set_value": card})
    s = Stack(harness=Worker(turn), background=FakeHarness(), hands_port=hands)
    s.harness.hands = s.hands
    targets = iter([card, cvv])
    real = hands.act

    async def act(tool, args):
        if tool == "describe" and args["tool"] == "ax_set_value":
            hands.calls.append((tool, args))
            return dict(next(targets))
        return await real(tool, args)

    hands.act = act
    [asked] = work(s, s.harness, "yes", user_asked=True)
    assert asked == []
    assert ["never touches a password field" in e for e in s.harness.errors] == [True, False, False]
    assert all("never touches a card number or security code field" in e for e in s.harness.errors[1:])


def test_money_kinds_ask_with_the_money_flag_and_password_and_security_stay_refused():
    s = Stack(allowed_apps=[{"name": "Notes", "bundle": ""}])
    scope = Scope((AppRef("Notes"),), "t1")

    async def run():
        refused = [(await s.approvals.approve(k, "x?", careful=True, scope=scope)).answer
                   for k in ("password", "security")]
        bot = asyncio.create_task(user(s, "always"))
        bought = await s.approvals.approve("buy", "Order the printer paper?", scope=scope)
        paid = await s.approvals.approve("money", "Pay the invoice?", scope=scope)
        bot.cancel()
        return refused, bought, paid

    refused, bought, paid = asyncio.run(run())
    assert refused == ["refused", "refused"]
    assert bought.answer == paid.answer == "yes", "a click on the (only) Yes"
    assert [(c.money, c.always) for c in s.sink.of(Confirm)] == [(True, False), (True, False)]


def test_money_never_asks_while_the_owner_is_away():
    s = Stack(channel=FakeChannel())
    if s.messages is None:
        pytest.skip("no message stack")
    s.messages.away = lambda: True
    s.messages._reachable = lambda: True

    async def run():
        return await s.approvals.confirm("I'm about to click “Buy Now” in Safari. Go ahead?", money=True)

    assert asyncio.run(run()) is False
    assert s.sink.of(Confirm) == [], "nobody at the Mac can say yes for the owner"


# ---- the default: auto


def test_by_default_make_the_whole_excel_red_asks_nothing_and_the_work_runs():
    # 2026-10-31 01:12: after "What's this?", "make it completely red" asked twice: whether to start the task from a
    # look, then "May I use Microsoft Excel for this?". In the default mode now neither asks.
    paint = ('tell application "Microsoft Excel"\n'
             '  set color of interior object of used range of active sheet to {255, 0, 0}\nend tell')
    screen = ScreenCapture(app="Microsoft Excel", window="Budget.xlsx", text="Rent 900", image="/tmp/x/look.png")
    worker = Worker([("run_applescript", {"script": paint})])
    s = Stack(harness=worker, background=FakeHarness(), hands_port=ExcelApp(), eyes=FakeEyes(screen),
              model=FakeLiveModel(["[thinking] Let me look. <look/>"],
                                  ['[happy] On it. <task screen="yes">Make the open Excel sheet completely red'
                                   '</task>']))
    worker.hands = s.hands

    async def run():
        await s.live_talk.start("in the Excel, make it completely red")
        await settle()
        await s.tasks.idle()

    asyncio.run(run())
    assert s.permits.ask == "auto"
    assert s.sink.of(Confirm) == [] and worker.errors == []
    assert ("run_applescript", {"script": paint}) in s.hands_port.calls
    [helper] = s.tasks.helpers
    assert helper.user_asked and not helper.careful, "the user asked for the work: it runs as theirs (ADR 0023)"


@pytest.mark.parametrize("step, question", [
    (("key", {"combo": "shift+cmd+delete"}), "I'm about to press ⇧⌘Delete in Finder, which may empty the Trash. Go ahead?"),
    (("ax_press", {"element": "buy"}), "I'm about to click “Buy Now” in Safari. Go ahead?"),
])
def test_by_default_the_same_task_still_stops_before_emptying_the_trash_or_buying(step, question):
    s, worker = desk(None, [*EXCEL_WORK, step])
    [asked] = work(s, worker, "no", careful=True, user_asked=True)
    assert [c.question for c in asked] == [question]


def test_can_you_see_my_screen_never_asks_in_the_default_mode():
    screen = ScreenCapture(app="Safari", window="News", text="Headline", image="/tmp/x/look.png")
    s = Stack(eyes=FakeEyes(screen), model=FakeLiveModel(["[thinking] <look/>"], ["[happy] A news page."]))

    async def run():
        await s.live_talk.start("can you see my screen")
        await settle()

    asyncio.run(run())
    assert s.eyes.modes == ["window"] and s.sink.of(Confirm) == []


# ---- the parts


@pytest.mark.parametrize("tool, args, target, risk, reason", [
    ("key", {"combo": "cmd+delete"}, {**FINDER, "role": "file"}, Risk.UNDO, "move to the Trash"),
    ("key", {"combo": "cmd+backspace"}, {**FINDER, "role": "row"}, Risk.UNDO, "move to the Trash"),
    ("key", {"combo": "option+cmd+delete"}, FINDER, Risk.ASK, "delete it for good"),
    ("key", {"combo": "shift+cmd+delete"}, FINDER, Risk.ASK, "empty the Trash"),
    ("key", {"combo": "cmd+w"}, EXCEL, Risk.OK, ""),
    ("key", {"combo": "cmd+delete"}, {**EXCEL, "role": "cell"}, Risk.UNDO, "move to the Trash"),
    ("key", {"combo": "cmd+delete"}, {"app": "Reminders", "role": "row"}, Risk.ASK, "delete"),
    ("key", {"combo": "cmd+delete"}, SAFARI, Risk.ASK, "delete"),
    ("key", {"combo": "delete"}, {"app": "Calendar", "bundle": "com.apple.iCal", "role": "Event"}, Risk.ASK, "delete"),
    ("key", {"combo": "delete"}, {"app": "Calendar", "role": "text field"}, Risk.OK, ""),
    ("key", {"combo": "delete"}, {"app": "Mail", "role": "row"}, Risk.UNDO, "delete"),
    ("key", {"combo": "delete"}, {**EXCEL, "role": "cell"}, Risk.OK, ""),
    ("ax_press", {}, {**SAFARI, "title": "Move to Trash"}, Risk.ASK, "delete"),
    # The sheet "Do you want to keep this new document?" deletes it for good, by its button or by ⌘⌫.
    ("ax_press", {}, {"app": "TextEdit", "title": "Delete", "role": "button"}, Risk.ASK, "delete"),
    ("ax_press", {}, {"app": "TextEdit", "title": "Delete", "role": "menu item"}, Risk.ASK, "change the document"),
    ("key", {"combo": "cmd+delete"}, {"app": "TextEdit", "title": "Delete", "role": "button"}, Risk.ASK, "delete"),
    ("key", {"combo": "cmd+delete"}, {"app": "TextEdit"}, Risk.ASK, "delete"),
    ("key", {"combo": "cmd+delete"}, {"app": "TextEdit", "role": "text area"}, Risk.UNDO, "move to the Trash"),
    ("key", {"combo": "cmd+delete"}, FINDER, Risk.ASK, "delete"),
    ("ax_press", {}, {**FINDER, "title": "Move to Trash"}, Risk.UNDO, "move to the Trash"),
    ("ax_press", {}, {**FINDER, "title": "Delete Immediately…"}, Risk.ASK, "delete immediately"),
    ("ax_press", {}, {**FINDER, "title": "Empty Trash"}, Risk.ASK, "empty trash"),
    ("ax_press", {}, {**NOTES, "title": "Delete"}, Risk.UNDO, "delete a note"),
    ("ax_press", {}, {"app": "Mail", "bundle": "com.apple.mail", "title": "Delete"}, Risk.UNDO, "delete"),
    ("ax_press", {}, {"app": "Mail", "bundle": "com.apple.mail", "title": "Delete Mailbox…"}, Risk.ASK, "delete"),
    ("ax_press", {}, {"app": "Reminders", "bundle": "com.apple.reminders", "title": "Delete"}, Risk.ASK, "delete"),
    ("ax_press", {}, {"app": "Calendar", "bundle": "com.apple.iCal", "title": "Delete Event"}, Risk.ASK, "delete"),
    ("ax_press", {}, {"app": "Contacts", "bundle": "com.apple.AddressBook", "title": "Delete Card"}, Risk.ASK, "delete"),
    ("ax_press", {}, {"app": "Some App", "title": "Delete"}, Risk.ASK, "delete"),
    ("ax_press", {}, {**SAFARI, "title": "Delete"}, Risk.ASK, "delete"),
    ("ax_press", {}, {**EXCEL, "title": "Delete", "role": "menu item"}, Risk.ASK, "change the document"),
    ("ax_press", {}, {**EXCEL, "title": "Delete Sheet"}, Risk.ASK, "delete"),
    ("ax_press", {}, {**EXCEL, "title": "Replace All"}, Risk.ASK, "change the document"),
    ("ax_press", {}, {**EXCEL, "title": "Replace"}, Risk.ASK, "replace"),
    ("ax_press", {}, {**EXCEL, "title": "Don't Save"}, Risk.ASK, "don't save"),
    ("ax_press", {}, {"app": "TextEdit", "title": "Nicht sichern"}, Risk.ASK, "nicht sichern"),
    ("ax_press", {}, {**SAFARI, "title": "Buy Now"}, Risk.MONEY, "buy now"),
    ("ax_press", {}, {**SAFARI, "title": "Jetzt kaufen"}, Risk.MONEY, "jetzt kaufen"),
    ("ax_press", {}, {**SAFARI, "title": "Confirm purchase"}, Risk.MONEY, "purchase"),
    ("ax_press", {}, {**SAFARI, "title": "Überweisung absenden"}, Risk.MONEY, "überweisung"),
    ("ax_press", {}, {**SAFARI, "title": "Cancel subscription"}, Risk.ASK, "cancel subscription"),
    ("ax_press", {}, {**SAFARI, "title": "Unsubscribe"}, Risk.ASK, "unsubscribe"),
    ("ax_press", {}, {**SAFARI, "title": "Delete account"}, Risk.ASK, "delete account"),
    ("ax_press", {}, {"app": "Finder", "title": "Uninstall"}, Risk.ASK, "uninstall"),
    ("run_applescript", {"script": 'tell application "Finder" to delete file "x"'}, {}, Risk.ASK, "delete"),
    ("run_applescript", {"script": 'tell application "Safari" to do JavaScript "pay()"'}, {}, Risk.ASK,
     "run other programs or type for you"),
])
def test_what_can_be_undone_and_what_cant(tool, args, target, risk, reason):
    verdict = classify(tool, args, target)
    assert (verdict.risk, verdict.reason) == (risk, reason)


def test_old_configs_keep_working_and_money_never_goes_below_ask_first():
    from milo.core.types import ActionLevel

    assert ActionPolicy({"delete": "never"}).level("trash") is ActionLevel.NEVER, "delete = never still covers trash"
    assert ActionPolicy({"delete": "read"}).level("trash") is ActionLevel.CHANGE
    assert ActionPolicy({"delete": "ask_first"}).level("trash") is ActionLevel.CHANGE, "the old template's line"
    assert ActionPolicy({"money": "never"}).level("money") is ActionLevel.NEVER
    assert ActionPolicy({"buy": "read", "money": "change"}).level("buy") is ActionLevel.ASK_FIRST
    assert ActionPolicy({"buy": "read", "money": "change"}).level("money") is ActionLevel.ASK_FIRST
    assert ActionPolicy().level("money") is ActionLevel.ASK_FIRST


@pytest.mark.parametrize("ask, careful, asked", [("step", False, 2), ("task", False, 0), ("auto", False, 0),
                                                  ("task", True, 1)])
def test_the_trash_kind_asks_only_every_step_or_once_for_a_careful_helper(ask, careful, asked):
    s = Stack(ask=ask)
    scope = Scope((AppRef("Finder", "com.apple.finder"),), "t1")

    async def run():
        bot = asyncio.create_task(user(s, "yes"))
        out = [await s.approvals.approve("trash", "Move “old.xlsx” to the Trash?", careful=careful, scope=scope)
               for _ in range(2)]
        bot.cancel()
        return out

    assert all(d.allowed for d in asyncio.run(run()))
    assert len(s.sink.of(Confirm)) == asked


def test_nothing_acts_on_the_screen_while_a_money_question_waits():
    # Milo's own windows aren't in the worker's screenshots, but a blind click could still land on the bubble's Yes.
    s, worker = desk("auto")

    async def run():
        s.hands.begin("t1")
        asking = asyncio.create_task(s.approvals.approve("buy", "Order the printer paper?"))
        await settle()
        try:
            await s.hands.call("click", {"x": 1200, "y": 800})
        except Exception as e:
            error = str(e)
        [c] = s.sink.of(Confirm)
        s.approvals.answer(c.id, False)
        await asking
        return error

    assert "question about money" in asyncio.run(run())
    assert "click" not in s.hands_port.actions


@pytest.mark.parametrize("trash, ask, asked, done", [("change", "auto", 0, True), ("ask_first", "auto", 1, True),
                                                     ("never", "auto", 0, False)])
def test_a_stricter_trash_level_in_config_counts_on_the_screen_too(trash, ask, asked, done):
    worker = Worker(TIDY[:1])
    s = Stack(harness=worker, background=FakeHarness(), hands_port=Desk(), ask=ask)
    s.approvals.policy = ActionPolicy({"trash": trash})
    [questions] = work(s, worker, "yes", user_asked=True)
    assert len(questions) == asked and (s.hands_port.actions.count("key") == 1) is done
