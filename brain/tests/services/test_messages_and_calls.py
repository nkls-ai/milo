"""Texting and calling someone from the talker (ADR 0039).

"Text Anna I'm late" and "call Mum" used to go to a helper, which could only say Messages can't be drafted. Now the
talker writes <message> or <call>, Milo finds the person in the user's contacts, and asks every time, naming who
(with the number) and the whole text, in every mode and from the phone too: nothing takes a message or a call back.
Everything here runs on the made-up connections: no message leaves and nothing rings.
"""

import asyncio
from pathlib import Path

from milo.adapters.connect.fake import World
from milo.core.access import Access, Need
from milo.core.events import AccessNote, ActionDone, Confirm, ConfirmAnswer
from milo.services import people
from milo.services.approvals import ActionPolicy, fit_bubble
from milo.services.reply_stream import ReplyParser
from tests.fakes import FakeAccess, FakeLiveModel
from tests.services.stack import Stack, settle

ANNA = {"name": "Anna Berg", "phones": [{"label": "home", "value": "+49 30 111"},
                                        {"label": "mobile", "value": "+49 170 1234567"}]}
ANNA_KIM = {"name": "Anna Kim", "phones": [{"label": "iPhone", "value": "+49 171 7654321"}]}
ANNABEL = {"name": "Annabel Ross", "phones": [{"label": "mobile", "value": "+49 172 5555555"}]}
MUM = {"name": "Jane Doe", "relation": "mother", "phones": [{"label": "mobile", "value": "+49 160 2222222"}],
       "emails": [{"label": "home", "value": "jane@example.com"}]}
LANDLINE = {"name": "Grandpa Joe", "phones": [{"label": "home", "value": "+49 89 333"}]}
MAIL_ONLY = {"name": "Kai Lee", "emails": [{"label": "work", "value": "kai@example.com"}]}


def stack(tmp_path: Path, *turns, contacts=(ANNA, MUM), **kw) -> Stack:
    World(tmp_path / "world").save({"events": [], "reminders": [], "contacts": list(contacts)})
    return Stack(model=FakeLiveModel(*turns), world=tmp_path / "world", home=tmp_path / "home", **kw)


def world(s: Stack) -> dict:
    return World(s.world).load()


def said(s: Stack) -> str:
    return " ".join(s.voice.spoken)


async def ask_and_answer(s: Stack, text: str, yes: bool | None, via: str = "voice") -> list[Confirm]:
    """The user says `text`; Milo's question, if he asks one, gets `yes` (None: no question is expected)."""
    s.live_talk.start(text, via=via)
    for _ in range(200):
        await asyncio.sleep(0.005)
        if s.approvals.pending or (not s.quick._running and s.live_talk._turn is None):
            break
    asks = s.sink.of(Confirm)
    if yes is not None and asks:
        await s.brain.handle(ConfirmAnswer(asks[-1].id, yes))
    await s.quick.idle()
    await settle()
    return asks


def test_a_message_asks_with_the_name_the_number_and_the_whole_text_then_sends(tmp_path):
    s = stack(tmp_path, ['[happy] <message to="Anna">I\'m running ten minutes late</message>'])
    asks = asyncio.run(ask_and_answer(s, "text Anna I'm running ten minutes late", True))
    [ask] = asks
    assert ask.question == "Send this to Anna Berg (+49 170 1234567)? “I'm running ten minutes late”", \
        "the mobile number, not the landline, and every word that goes"
    assert not ask.always, "no Allow always: the next message asks again"
    assert world(s)["messages_sent"] == [{"to": "+49 170 1234567", "text": "I'm running ten minutes late"}]
    assert said(s).endswith("Sent to Anna.")
    [card] = s.sink.of(ActionDone)
    assert (card.kind, card.title, card.detail, card.app, card.undo) == (
        "message", "Anna Berg", "I'm running ten minutes late", "Messages", ""), "the card says what went; no Undo"


def test_no_sends_nothing(tmp_path):
    s = stack(tmp_path, ['[happy] <message to="Anna">I\'m late</message>'])
    asyncio.run(ask_and_answer(s, "text Anna I'm late", False))
    assert world(s)["messages_sent"] == []
    assert said(s).endswith("Okay, I left it.")


def test_a_message_asks_every_time_even_in_auto_mode_and_when_config_lowered_send(tmp_path):
    s = stack(tmp_path, ['[happy] <message to="Anna">one</message>'], ['[happy] <message to="Anna">two</message>'])
    assert s.permits.ask == "auto"
    s.approvals.policy = ActionPolicy({"send": "change"})
    asyncio.run(ask_and_answer(s, "text Anna one", True))
    asyncio.run(ask_and_answer(s, "text Anna two", True))
    assert len(s.sink.of(Confirm)) == 2
    assert [m["text"] for m in world(s)["messages_sent"]] == ["one", "two"]


def test_send_set_to_never_refuses_without_asking(tmp_path):
    s = stack(tmp_path, ['[happy] <message to="Anna">hi</message>'])
    s.approvals.policy = ActionPolicy({"send": "never"})
    asyncio.run(ask_and_answer(s, "text Anna hi", None))
    assert not s.sink.of(Confirm) and world(s)["messages_sent"] == []
    assert "isn't allowed" in said(s)


def test_a_call_to_mum_finds_her_through_the_users_own_card(tmp_path):
    s = stack(tmp_path, ['[happy] <call to="Mum"/>'])
    [ask] = asyncio.run(ask_and_answer(s, "call Mum", True))
    assert ask.question == "Call Mum (Jane Doe, +49 160 2222222)?"
    assert world(s)["calls"] == [{"to": "+49 160 2222222", "how": "phone"}]
    assert said(s).endswith("Calling Mum.")
    [card] = s.sink.of(ActionDone)
    assert (card.kind, card.title, card.detail, card.undo) == ("call", "Jane Doe", "+49 160 2222222", "")


def test_a_video_call_and_an_internet_call_say_so(tmp_path):
    s = stack(tmp_path, ['[happy] <call to="Mama" video="yes"/>'], ['[happy] <call to="Kai" facetime="yes"/>'],
              contacts=(MUM, MAIL_ONLY))
    [ask] = asyncio.run(ask_and_answer(s, "ruf Mama per Video an", True))
    assert ask.question == "Video call Mama (Jane Doe, +49 160 2222222)?"
    asyncio.run(ask_and_answer(s, "facetime Kai", True))
    assert s.sink.of(Confirm)[-1].question == "Call Kai Lee (kai@example.com) over the internet, audio only?"
    assert world(s)["calls"] == [{"to": "+49 160 2222222", "how": "video"}, {"to": "kai@example.com", "how": "audio"}]
    assert "Video call to Mama." in said(s) and said(s).endswith("Calling Kai.")


def test_several_people_with_that_name_get_a_question_not_a_guess(tmp_path):
    s = stack(tmp_path, ['[thinking] <message to="Anna">Running late</message>'],
              ['[happy] <message to="Anna Kim">Running late</message>'], contacts=(ANNA, ANNA_KIM, ANNABEL))
    asyncio.run(ask_and_answer(s, "text Anna running late", None))
    assert said(s) == "Which Anna: “Anna Berg” or “Anna Kim”?", "Annabel only starts like it"
    assert not s.sink.of(Confirm) and world(s)["messages_sent"] == []
    asyncio.run(ask_and_answer(s, "Anna Kim", True))
    assert s.sink.of(Confirm)[-1].question == "Send this to Anna Kim (+49 171 7654321)? “Running late”"
    assert world(s)["messages_sent"] == [{"to": "+49 171 7654321", "text": "Running late"}]


def test_nobody_by_that_name_is_said_plainly(tmp_path):
    s = stack(tmp_path, ['[happy] <call to="Bob"/>'], ['[happy] <call to="Nobody"/>'],
              contacts=(ANNA, {"name": "Nobody Home"}))
    asyncio.run(ask_and_answer(s, "call Bob", None))
    assert said(s) == "I can't find Bob in your contacts."
    asyncio.run(ask_and_answer(s, "call Nobody", None))
    assert said(s).endswith("I have no number or address for Nobody Home.")
    assert world(s)["calls"] == [] and not s.sink.of(Confirm)


def test_someone_with_only_an_address_gets_an_internet_call_and_a_landline_still_a_message(tmp_path):
    s = stack(tmp_path, ['[happy] <call to="Kai"/>'], contacts=(MAIL_ONLY,))
    [ask] = asyncio.run(ask_and_answer(s, "call Kai", True))
    assert ask.question == "Call Kai Lee (kai@example.com) over the internet, audio only?", \
        "an address takes no phone call, so it becomes an internet one, and the question says so"
    s = stack(tmp_path / "landline", ['[happy] <message to="Grandpa Joe">hi</message>'], contacts=(LANDLINE,))
    asyncio.run(ask_and_answer(s, "text grandpa joe hi", True))
    assert world(s)["messages_sent"] == [{"to": "+49 89 333", "text": "hi"}], "a landline is still a number"


def test_a_number_said_outright_needs_no_contacts(tmp_path):
    s = stack(tmp_path, ['[happy] <message to="+49 151 999 888">On my way</message>'], contacts=(),
              access=FakeAccess(contacts="no"))
    [ask] = asyncio.run(ask_and_answer(s, "text plus 49 151 999 888 on my way", True))
    assert ask.question == "Send this to +49 151 999 888? “On my way”"
    assert world(s)["messages_sent"] == [{"to": "+49 151 999 888", "text": "On my way"}]
    assert ("check", "contacts", "") not in s.access.calls


def test_the_system_asks_about_contacts_once_and_milo_says_so_first(tmp_path):
    access = FakeAccess(contacts="ask")
    s = stack(tmp_path, ['[happy] <call to="Anna"/>'], ['[happy] <call to="Mum"/>'], access=access)
    access.sink = s.sink
    asyncio.run(ask_and_answer(s, "call Anna", True))
    [shown] = access.shown
    assert [(e.need, e.state, e.text) for e in shown if isinstance(e, AccessNote)] == [
        ("contacts", "ask", "macOS will ask once whether I may look in your contacts. Please allow it.")]
    assert [c[0] for c in access.calls if c[1] == "contacts"][:2] == ["check", "request"]
    asked = len(access.calls)
    asyncio.run(ask_and_answer(s, "call Mum", True))
    assert len(access.calls) == asked, "a yes is kept: the second call checks nothing"
    assert len(world(s)["calls"]) == 2


def test_contacts_turned_down_says_who_milo_couldnt_find_and_shows_fix_it(tmp_path):
    s = stack(tmp_path, ['[happy] <message to="Anna">hi</message>'], access=FakeAccess(contacts="no"))
    asyncio.run(ask_and_answer(s, "text Anna hi", None))
    assert said(s) == "I can't look in your contacts, so I don't know who Anna is. A number works."
    assert [(n.need, n.state) for n in s.sink.of(AccessNote)] == [("contacts", "no")]
    assert world(s)["messages_sent"] == [] and not s.sink.of(Confirm)


def test_messages_needs_the_systems_yes_to_control_messages_before_it_sends(tmp_path):
    """The made-up connections never ask the system; this one scripts Messages, like the real one."""
    import dataclasses

    from milo.adapters.connect.fake import FakeMessages

    class Scripted(FakeMessages):
        controls = "Messages"

    s = stack(tmp_path, ['[happy] <message to="Anna">hi</message>'],
              access=FakeAccess(apps={"Messages": "ask"}, clicks={"Messages": "no"}))
    s.quick._connections = dataclasses.replace(s.quick._connections, messages=Scripted(World(s.world)))
    asyncio.run(ask_and_answer(s, "text Anna hi", True))
    assert ("request", "control", "Messages") in s.access.calls, "after the user's yes, before the send"
    assert world(s)["messages_sent"] == []


def test_switched_off_messages_say_so(tmp_path):
    s = stack(tmp_path, ['[happy] <message to="Anna">hi</message>'])
    import dataclasses
    s.quick._connections = dataclasses.replace(s.quick._connections, messages=None)
    asyncio.run(ask_and_answer(s, "text Anna hi", None))
    assert "switched off" in said(s)


def test_the_question_and_the_line_come_in_german(tmp_path):
    s = stack(tmp_path, ['[happy] <message to="Mama">Bin gleich da</message>'])
    [ask] = asyncio.run(ask_and_answer(s, "schreib Mama, dass ich gleich da bin", True))
    assert ask.question == "Das an Mama (Jane Doe, +49 160 2222222) schicken? „Bin gleich da“"
    assert said(s).endswith("An Mama geschickt.")


def test_from_the_phone_the_question_goes_to_the_chat_first(tmp_path):
    from tests.fakes import FakeChannel, MemoryRemoteState
    from tests.services.test_messages import OWNER, me

    s = stack(tmp_path, ['[happy] <message to="Anna">Late, sorry</message>'], channel=FakeChannel(),
              remote=MemoryRemoteState(OWNER))
    s.quick.message_wait_s = 0.05

    async def run():
        work = asyncio.create_task(s.messages.run())
        s.channel.push(me("text anna late sorry"))
        for _ in range(400):
            await asyncio.sleep(0.005)
            if s.channel.questions:
                break
        [(_, id, question)] = s.channel.questions
        assert question.startswith("Send this to Anna Berg (+49 170 1234567)? “Late, sorry”")
        assert world(s)["messages_sent"] == [], "nothing went before the yes"
        s.channel.push(me(answer=f"yes:{id}", ref="cb1"))
        await s.quick.idle()
        await settle(200)
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)

    asyncio.run(run())
    assert world(s)["messages_sent"] == [{"to": "+49 170 1234567", "text": "Late, sorry"}]
    assert s.channel.texts("42")[-1] == "Sent to Anna."


# ---- the parts


def test_message_and_call_tags_are_parsed_and_never_spoken():
    p = ReplyParser()
    out = "".join(p.feed(d) for d in ['[happy] <message to="An', 'na">Running\n late</mess', 'age><call to="Mum" ',
                                      'video="yes"/>'])
    out += p.finish()
    assert out == ""
    assert [(a.kind, a.attrs, a.text) for a in p.acts] == [
        ("message", {"to": "Anna"}, "Running\nlate"), ("call", {"to": "Mum", "video": "yes"}, "")]


def test_numbers_and_addresses_said_outright():
    assert people.address_in("+49 (170) 123-4567") == "+49 (170) 123-4567"
    assert people.address_in("anna@example.com") == "anna@example.com"
    assert people.address_in("Anna") == people.address_in("12") == ""


def test_family_words_in_both_languages():
    assert [people.relation_of(w) for w in ("Mum", "my mom", "Mama", "meine Mutti", "Papa", "my sister", "Anna")] \
        == ["mother", "mother", "mother", "mother", "father", "sister", ""]


def test_the_number_for_each_way_of_reaching_someone():
    assert people.pick_address(MUM, "message") == "+49 160 2222222", "a mobile number first"
    assert people.pick_address(MAIL_ONLY, "message") == "kai@example.com"
    assert people.pick_address(MAIL_ONLY, "phone") == "kai@example.com", "the call goes over the internet then"
    assert people.pick_address({"name": "Nobody"}, "phone") == ""
    assert people.pick_address(LANDLINE, "phone") == "+49 89 333"


def test_the_same_person_on_two_cards_is_one(tmp_path):
    World(tmp_path).save({"contacts": [{"name": "Anna Berg", "phones": [{"label": "home", "value": "1"}]},
                                       {"name": "anna berg", "phones": [{"label": "mobile", "value": "+49 170 1"}]}]})
    from milo.adapters.connect.fake import FakeContacts
    person = asyncio.run(people.find(FakeContacts(World(tmp_path)), "Anna", "message"))
    assert (person.name, person.address, person.short) == ("Anna Berg", "+49 170 1", "Anna")


def test_access_need_reads_from_the_wire():
    from milo.core.access import AccessAnswer
    assert Need("contacts") is Need.CONTACTS
    assert AccessAnswer.from_wire({"access": "ask", "system": "macOS", "label": "Contacts"}).access is Access.ASK


def test_the_brain_reaches_the_apps_address_book_directly():
    from milo.core.app_connections import AppContacts
    from milo.core.ports import Connections
    from milo.services.connections import in_brain

    asked = []

    async def app(op, args):
        asked.append((op, args))
        return [MUM]

    worker = Connections(contacts=AppContacts(lambda op, args: []))  # through the tool socket: blocking
    contacts = in_brain(worker, app, music=False).contacts
    assert contacts.awaits
    person = asyncio.run(people.find(contacts, "my mum", "phone"))
    assert asked == [("contacts.find", {"name": "mum", "relation": "mother"})]
    assert (person.name, person.said, person.short) == ("Jane Doe", "mum", "Mum")


def test_the_question_shows_exactly_the_text_that_goes_lines_and_all(tmp_path):
    """Security review, 2026-11-01: the question cut the text at 1000 characters and folded its lines, so a yes could
    send words the user never saw. Now it shows every character that goes, and nothing else goes."""
    s = stack(tmp_path, ['[happy] <message to="Anna">See you at 5\n  bring the cake ->\n</message>'])
    [ask] = asyncio.run(ask_and_answer(s, "text Anna see you at five, bring the cake", True))
    [sent] = world(s)["messages_sent"]
    assert sent["text"] == "See you at 5\nbring the cake -›"
    assert ask.question == f"Send this to Anna Berg (+49 170 1234567)? “{sent['text']}”"


def test_a_long_message_goes_whole_into_the_question_and_a_longer_one_not_at_all(tmp_path):
    long = "word " * 150  # 750 characters: more than the bubble shows, all of it in the window's detail
    s = stack(tmp_path, [f'[happy] <message to="Anna">{long}</message>'],
              [f'[happy] <message to="Anna">{"x" * 1001}</message>'])
    asyncio.run(ask_and_answer(s, "text Anna the long one", True))
    assert world(s)["messages_sent"][0]["text"] == long.strip()
    shown = s.sink.of(Confirm)[-1].question
    assert shown.endswith("… (all of it is in the Milo window)"), "the bubble cuts it where everyone sees it was cut"
    whole = f"Send this to Anna Berg (+49 170 1234567)? “{long.strip()}”"
    assert fit_bubble(whole, "") == (shown, whole), "and the window shows every word of it"
    asyncio.run(ask_and_answer(s, "text Anna the longer one", None))
    assert len(world(s)["messages_sent"]) == 1 and said(s).endswith("that message is too long to send from here.")


def test_a_number_or_address_too_long_to_show_whole_is_refused(tmp_path):
    odd = {"name": "Odd One", "emails": [{"label": "home", "value": "a" * 90 + "@example.com"}]}
    s = stack(tmp_path, ['[happy] <call to="Odd One"/>'], contacts=(odd,))
    asyncio.run(ask_and_answer(s, "call Odd One", None))
    assert not s.sink.of(Confirm) and world(s)["calls"] == []
    assert said(s).endswith("that number or address is too long to check.")


def test_nothing_invisible_goes_that_the_question_doesnt_show(tmp_path):
    """Security review, 2026-11-01: a bidi override or a zero-width space would go out in the text and the number,
    showing in the question as something else. They are dropped from both, and the joiners emoji need stay."""
    hidden = "Pay ‮etal‬ at 5​ ok 👨‍👩‍👧"
    s = stack(tmp_path, [f'[happy] <message to="Anna">{hidden}</message>'])
    [ask] = asyncio.run(ask_and_answer(s, "text Anna", True))
    [sent] = world(s)["messages_sent"]
    assert sent["text"] == "Pay etal at 5\nok 👨\u200d👩\u200d👧", "a line separator is a line break, shown as one"
    assert ask.question == f"Send this to Anna Berg (+49 170 1234567)? “{sent['text']}”"


def test_a_number_the_address_book_wraps_in_direction_marks_is_used_plain(tmp_path):
    wrapped = {"name": "Lea Wolf", "phones": [{"label": "mobile", "value": "‪+49 170 999‬"}]}
    s = stack(tmp_path, ['[happy] <call to="Lea"/>'], contacts=(wrapped,))
    [ask] = asyncio.run(ask_and_answer(s, "call Lea", True))
    assert ask.question == "Call Lea Wolf (+49 170 999)?"
    assert world(s)["calls"] == [{"to": "+49 170 999", "how": "phone"}], "the number shown is the number called"


def test_an_address_with_characters_that_dont_show_plainly_is_refused(tmp_path):
    odd = {"name": "Odd One", "emails": [{"label": "home", "value": "аnna@example.com"}]}  # a Cyrillic "а"
    s = stack(tmp_path, ['[happy] <message to="Odd One">hi</message>'], contacts=(odd,))
    asyncio.run(ask_and_answer(s, "text Odd One hi", None))
    assert not s.sink.of(Confirm) and world(s)["messages_sent"] == []
