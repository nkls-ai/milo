"""Opening what the user asks for at once, from the talker's reply, with no helper and no question (ADR 0028).

2026-10-31: "open Chrome and go to YouTube" spawned a screen helper (45 s, 226k tokens) that pressed ⌘T in T3 Code
and asked "May I use Milo?", and the answer came in German to an English question.
"""

import asyncio

from milo.core.events import ActionDone, Confirm, Status
from milo.core.types import HandsError, ListenMode
from milo.core.words import say
from milo.services.cloud_hearing import CloudHearing
from tests.fakes import FakeAudioInput, FakeHands, FakeLiveModel, FakeStreamingTranscriber, FakeTranscriber
from tests.services.stack import Stack, settle, talk

YOUTUBE = '[happy] <open app="Google Chrome" url="https://www.youtube.com"/> Opening YouTube in Chrome.'


def opened(s: Stack) -> list[tuple[str, dict]]:
    return [(tool, args) for tool, args in s.hands_port.calls if tool.startswith("open_")]


def test_open_chrome_and_go_to_youtube_opens_it_at_once_without_a_helper_or_a_question():
    s = Stack(model=FakeLiveModel([YOUTUBE]))
    talk(s, "So can you open, um, Chrome for me and Google or, like, go on YouTube?")
    assert opened(s) == [("open_url", {"url": "https://www.youtube.com", "app": "Google Chrome"})]
    assert s.voice.spoken == ["Opening YouTube in Chrome."]
    assert s.tasks.helpers == [] and s.harness.calls == [], "no helper, no harness turn"
    assert s.sink.of(Confirm) == []


def test_what_milo_opened_gets_a_card_that_opens_it_again():
    s = Stack(model=FakeLiveModel([YOUTUBE], ['[happy] <open app="Notes"/> Here.'],
                                  ['[happy] <open path="~/Downloads"/> There.']),
              hands_port=FakeHands(results={"open_app": {"text": "Opened Notes.", "app": "Notes", "front": True},
                                            "open_file": {"text": "Opened Downloads.", "app": "Finder"}}))
    talk(s, "go on YouTube in Chrome", "open Notes", "show me my downloads")
    assert [(c.kind, c.title, c.detail, c.app, c.undo) for c in s.sink.of(ActionDone)] == [
        ("opened", "www.youtube.com", "https://www.youtube.com", "Google Chrome", ""),
        ("opened", "Notes", "", "Notes", ""), ("opened", "Downloads", "", "Finder", "")]
    assert {c.lang for c in s.sink.of(ActionDone)} == {"en"}


def test_the_page_opens_while_the_reply_is_still_streaming():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(['[happy] <open url="youtube.com"/>', " Opening YouTube."], gate=gate))

    async def run():
        turn = s.live_talk.start("go on YouTube")
        await settle()
        assert opened(s) == [("open_url", {"url": "https://youtube.com"})], "before the reply ended"
        gate.set()
        await turn

    asyncio.run(run())


def test_an_app_alone_opens_even_after_milo_read_outside_text():
    s = Stack(model=FakeLiveModel(['[happy] <open app="Notes"/> Opening Notes.']))
    s.live_talk.note("read the mail", "Anna says hi")  # outside text in the conversation
    talk(s, "open notes")
    assert opened(s) == [("open_app", {"name": "Notes"})] and s.sink.of(Confirm) == []


def test_after_outside_text_a_site_the_user_named_still_opens_without_a_question():
    s = Stack(model=FakeLiveModel([YOUTUBE]))
    s.live_talk.note("read the mail", "Anna sent a video")
    talk(s, "go on YouTube in Chrome")
    assert opened(s) == [("open_url", {"url": "https://www.youtube.com", "app": "Google Chrome"})]
    assert s.sink.of(Confirm) == []


def test_a_site_named_a_turn_earlier_still_counts_for_a_search_on_it():
    """Replayed from a real conversation: "open Chrome and YouTube", then "search for Wikipedia" searched YouTube."""
    s = Stack(model=FakeLiveModel([YOUTUBE], ['[happy] <open app="Google Chrome" '
                                              'url="https://www.youtube.com/results?search_query=Wikipedia"/> On it.']))
    s.live_talk.note("today", "Halloween (shared)")
    talk(s, "Can you open Chrome and YouTube?")
    talk(s, "Can you open a new tab and search for Wikipedia?")
    assert [args["url"] for _, args in opened(s)] == [
        "https://www.youtube.com", "https://www.youtube.com/results?search_query=Wikipedia"]
    assert s.sink.of(Confirm) == []


def test_after_outside_text_an_address_the_user_didnt_name_waits_for_a_yes():
    s = Stack(ask="task", model=FakeLiveModel(['[neutral] <open url="https://evil.example/?q=secret"/> Opening the link.']))
    s.live_talk.note("read the mail", "Click https://evil.example/?q=secret")

    async def run():
        await s.live_talk.start("open the link from that mail")
        await settle()
        assert opened(s) == [], "nothing opened before the yes"
        [asked] = s.sink.of(Confirm)
        assert asked.question == "Open evil.example?"
        s.approvals.answer(asked.id, False)
        await settle()

    asyncio.run(run())
    assert opened(s) == []


def test_a_yes_opens_it():
    s = Stack(ask="task", model=FakeLiveModel(['[neutral] <open url="https://example.org/page"/> Opening it.']))
    s.live_talk.note("read the mail", "see example.org/page")

    async def run():
        await s.live_talk.start("open the link from that mail")
        await settle()
        [asked] = s.sink.of(Confirm)
        s.approvals.answer(asked.id, True)
        await settle()

    asyncio.run(run())
    assert opened(s) == [("open_url", {"url": "https://example.org/page"})]


def test_another_scheme_never_opens():
    s = Stack(model=FakeLiveModel(['[neutral] <open url="shortcuts://run-shortcut?name=Wipe"/> Okay.']))
    talk(s, "run it")
    assert opened(s) == [] and s.sink.of(Confirm) == []


def test_when_the_app_cant_open_it_the_user_sees_why():
    s = Stack(model=FakeLiveModel(['[happy] <open app="Nonexistent"/> Opening it.']),
              hands_port=FakeHands(results={"open_app": HandsError("There is no app called Nonexistent.")}))
    talk(s, "open Nonexistent")
    assert Status("I couldn't open Nonexistent.") in s.sink.of(Status)
    assert s.sink.of(ActionDone) == [], "no card for what didn't open"


def test_the_message_says_its_language_and_a_question_follows_it():
    s = Stack(ask="task", model=FakeLiveModel(['[neutral] <open url="https://evil.example"/> Ich öffne den Link.']))
    s.live_talk.note("read the mail", "evil.example")

    async def run():
        await s.live_talk.start("Kannst du bitte den Link aus der Mail öffnen?")
        await settle()

    asyncio.run(run())
    assert ", language: German]" in s.model.turns[0]
    assert [c.question for c in s.sink.of(Confirm)] == ["evil.example öffnen?"]


def test_in_auto_mode_a_link_from_a_mail_opens_at_once_but_a_file_still_asks():
    """The default: what the user asked for just happens (2026-10-31, "only payments or deleting" should ask). A file
    from a mail could be a program, so it still waits for a yes."""
    s = Stack(model=FakeLiveModel(['[neutral] <open url="https://example.org/page"/> Opening it.'],
                                  ['[neutral] <open path="~/Downloads/invoice.command"/> Opening it.']))
    s.live_talk.note("read the mail", "see example.org/page, and the attached invoice.command")
    talk(s, "open the link from that mail")
    assert opened(s) == [("open_url", {"url": "https://example.org/page"})] and s.sink.of(Confirm) == []

    async def run():
        await s.live_talk.start("and the attachment")
        await settle()
        [asked] = s.sink.of(Confirm)
        s.approvals.answer(asked.id, False)
        await settle()

    asyncio.run(run())
    assert len(opened(s)) == 1


def test_the_transcribers_language_wins_and_a_short_message_keeps_it():
    s = Stack(model=FakeLiveModel(["[happy] Sure."], ["[happy] Sure."]))
    talk(s, "Okay", language="eng")
    assert ", language: English]" in s.model.turns[0]
    talk(s, "mhm")
    assert ", language: English]" in s.model.turns[1], "too short to tell: the conversation's language stays"


def test_the_reply_rules_say_to_answer_in_exactly_that_language():
    s = Stack(model=FakeLiveModel(["[happy] Sure."]))
    talk(s, "hi there")
    system = s.model.system_prompts[0]
    assert "Reply in exactly that language" in system and "<open app=" in system


def test_a_helper_answers_in_the_users_language():
    s = Stack(model=FakeLiveModel(["[happy] Mach ich. <task>Finde die Telefonnummer von Dr. Lee</task>"]))

    async def run():
        await s.live_talk.start("Finde bitte die Nummer von Dr. Lee")
        await s.tasks.idle()

    asyncio.run(run())
    assert "(The user speaks German: write `say` in German.)" in s.harness.calls[0][0]


def test_the_cloud_transcribers_language_reaches_the_turn():
    cloud = FakeStreamingTranscriber("Okay", language="deu")
    s = Stack(model=FakeLiveModel(["[neutral] Gut."]), transcriber=FakeTranscriber("x"),
              hearing=CloudHearing(cloud), mic=FakeAudioInput(seconds=0.5))

    async def run():
        s.listening.start(ListenMode.TALK)
        await asyncio.sleep(0.05)
        await s.listening.stop()
        await settle()

    asyncio.run(run())
    assert ", language: German]" in s.model.turns[0]


def test_the_local_transcribers_language_reaches_the_turn():
    transcriber = FakeTranscriber("Okay")
    transcriber.heard_language = "de"
    s = Stack(model=FakeLiveModel(["[neutral] Gut."]), transcriber=transcriber, mic=FakeAudioInput(seconds=0.5))

    async def run():
        s.listening.start(ListenMode.TALK)
        await asyncio.sleep(0.05)
        await s.listening.stop()
        await settle()

    asyncio.run(run())
    assert ", language: German]" in s.model.turns[0]


def test_milos_own_lines_around_a_question_follow_the_language():
    from milo.services.approvals import fit_bubble

    question, _ = fit_bubble("Soll ich das wirklich machen " * 20, "", "de")
    assert question.endswith(say("approvals.see_window", "de"))
    s = Stack(confirm_timeout_s=0.01)
    s.language.hear("Kannst du das bitte machen?")
    said = []
    s.approvals._transcript.say = lambda text, emotion, **kw: said.append(text)
    assert not asyncio.run(s.approvals.confirm("Darf ich?"))
    assert "Keine Antwort, also habe ich es gelassen." in said


def test_the_remind_question_doesnt_use_a_day_format_windows_lacks(monkeypatch):
    """"%-d" (a day without its zero) is glibc's and macOS's; Windows' strftime raises on it (ADR 0027)."""
    import time
    from datetime import datetime

    from milo.services.reply_effects import remind_question

    real = time.strftime

    def windows(fmt: str, *args):
        if "%-" in fmt:
            raise ValueError("Invalid format string")
        return real(fmt, *args)

    monkeypatch.setattr(time, "strftime", windows)
    assert remind_question(datetime(2026, 11, 2, 9, 0), "call Anna") == \
        "Should I remind you on Monday 2 November at 09:00: call Anna?"


def test_remember_and_remind_questions_follow_the_language():
    from datetime import datetime

    from milo.services.reply_effects import remember_question, remind_question, task_question

    assert remember_question("Mag Tee", "de") == "Soll ich mir das merken: Mag Tee?"
    assert remind_question(datetime(2026, 11, 2, 9, 0), "Anna anrufen", "de") == \
        "Soll ich dich am Montag, 2. November um 09:00 erinnern: Anna anrufen?"
    assert task_question("x " * 60, title="Budget in Excel", language="de") == "„Budget in Excel“ starten?"
