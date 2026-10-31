"""Home and Focus from the talker (ADR 0037).

The user's wish: "connect to home stuff", any home system that is connected, or the default. Lights, plugs, scenes and
heating just happen, with a card and Undo back to how they were; locks, garage doors and the alarm ask first, every
time. "Do Not Disturb on" just happens too. The home here is the fake one over world.json, never a real one.
"""

import asyncio
from pathlib import Path

from milo.adapters.connect.fake import World
from milo.core.events import ActionDone, Confirm, ConfirmAnswer
from tests.fakes import FakeLiveModel
from tests.services.stack import Stack, settle

KITCHEN = [
    {"id": "light.ceiling", "name": "Kitchen ceiling light", "kind": "light", "room": "Kitchen", "state": "on",
     "level": 80},
    {"id": "light.counter", "name": "Kitchen counter light", "kind": "light", "room": "Kitchen", "state": "off"},
]
HOME = [
    *KITCHEN,
    {"id": "light.floor", "name": "Stehlampe", "kind": "light", "room": "Wohnzimmer", "state": "off"},
    {"id": "climate.living", "name": "Heizung", "kind": "climate", "room": "Wohnzimmer", "state": "heat",
     "level": 20},
    {"id": "lock.front", "name": "Front door", "kind": "lock", "state": "locked"},
    {"id": "cover.garage", "name": "Garage door", "kind": "garage", "state": "closed"},
    {"id": "scene.movie", "name": "Movie night", "kind": "scene", "members": ["light.ceiling", "light.floor"]},
]


def stack(tmp_path: Path, *turns, world: dict | None = None, **kw) -> Stack:
    World(tmp_path / "world").save({"events": [], "reminders": [], "home": HOME, **(world or {})})
    return Stack(model=FakeLiveModel(*turns), world=tmp_path / "world", home=tmp_path / "home", **kw)


def world(s: Stack) -> dict:
    return World(s.world).load()


def device(s: Stack, id: str) -> dict:
    return next(d for d in world(s)["home"] if d["id"] == id)


async def say(s: Stack, *texts: str) -> None:
    for text in texts:
        await s.live_talk.start(text)
        await settle()
        await s.quick.idle()
        if s.undo is not None:
            await s.undo.idle()
        await settle()


async def answer(s: Stack, text: str, yes: bool) -> Confirm:
    s.live_talk.start(text)
    for _ in range(200):
        await asyncio.sleep(0.005)
        if s.approvals.pending:
            break
    ask = s.sink.of(Confirm)[-1]
    await s.brain.handle(ConfirmAnswer(ask.id, yes))
    await s.quick.idle()
    await settle()
    return ask


def said(s: Stack) -> str:
    return " ".join(s.voice.spoken)


def cards(s: Stack) -> list[ActionDone]:
    return s.sink.of(ActionDone)


def test_a_light_goes_on_at_once_with_a_card_and_undo_puts_it_back(tmp_path):
    s = stack(tmp_path, ['[happy] <home device="Stehlampe" do="on"/>'], ["[happy] <undo/>"])
    asyncio.run(say(s, "mach bitte die Stehlampe im Wohnzimmer an"))
    assert device(s, "light.floor")["state"] == "on"
    assert not s.sink.of(Confirm), "a light just happens"
    assert said(s) == "Stehlampe: an."
    [card] = cards(s)
    assert (card.kind, card.title, card.detail, card.app) == ("home", "Stehlampe", "Wohnzimmer", "Fake home")
    assert card.undo
    asyncio.run(say(s, "undo that"))
    assert device(s, "light.floor")["state"] == "off", "back to how it was"


def test_the_kitchen_lights_are_all_of_them_and_undo_puts_each_back_as_it_was(tmp_path):
    s = stack(tmp_path, ['[happy] <home device="the kitchen lights" do="off"/>'], ["[happy] <undo/>"])
    asyncio.run(say(s, "turn off the kitchen lights"))
    assert [device(s, d["id"])["state"] for d in KITCHEN] == ["off", "off"]
    assert said(s) == "Kitchen lights: off."
    asyncio.run(say(s, "undo that"))
    assert (device(s, "light.ceiling")["state"], device(s, "light.counter")["state"]) == ("on", "off")
    assert sorted(r["id"] + " " + r["do"] for r in world(s)["home_runs"][-2:]) == [
        "light.ceiling on", "light.counter off"], "each one back as it was, not all on or all off"


def test_one_light_said_where_two_match_gets_a_question_which(tmp_path):
    s = stack(tmp_path, ['[happy] <home device="kitchen light" do="on"/>'])
    asyncio.run(say(s, "turn on the kitchen light"))
    assert world(s)["home_runs"] == []
    assert said(s) == "Which one: “Kitchen ceiling light” or “Kitchen counter light”?"


def test_a_brightness_and_a_temperature(tmp_path):
    s = stack(tmp_path, ['[happy] <home device="Stehlampe" do="set" value="40%"/>'],
              ['[happy] <home device="Heizung" do="set" value="21,5"/>'], ["[happy] <undo/>"])
    asyncio.run(say(s, "stell bitte die Stehlampe auf vierzig Prozent", "und die Heizung im Wohnzimmer auf 21,5 Grad"))
    assert device(s, "light.floor")["level"] == 40 and device(s, "climate.living")["level"] == 21.5
    assert said(s) == "Stehlampe: 40 Prozent. Heizung: 21.5 Grad."
    asyncio.run(say(s, "undo that"))
    assert device(s, "climate.living")["level"] == 20


def test_dimming_a_light_that_was_on_comes_back_at_its_brightness(tmp_path):
    s = stack(tmp_path, ['[happy] <home device="Kitchen ceiling light" do="set" value="20"/>'], ["[happy] <undo/>"])
    asyncio.run(say(s, "dim the kitchen ceiling light to 20", "undo that"))
    assert device(s, "light.ceiling")["level"] == 80


def test_a_scene_runs_and_undo_puts_what_it_set_back(tmp_path):
    s = stack(tmp_path, ['[happy] <home scene="Movie night"/>'], ["[happy] <undo/>"])
    asyncio.run(say(s, "movie night"))
    assert (device(s, "light.ceiling")["state"], device(s, "light.floor")["state"]) == ("on", "on")
    assert said(s) == "Scene on: Movie night."
    asyncio.run(say(s, "undo that"))
    assert device(s, "light.floor")["state"] == "off"
    assert {"id": "light.floor", "do": "off", "value": ""} in world(s)["home_runs"][-2:]


def test_a_lock_asks_every_time_even_in_auto_mode_and_no_leaves_it(tmp_path):
    s = stack(tmp_path, ['[happy] <home device="front door" do="unlock"/>'])
    ask = asyncio.run(answer(s, "unlock the front door", False))
    assert ask.question == "Unlock “Front door”?"
    assert device(s, "lock.front")["state"] == "locked"
    assert said(s).endswith("Okay, I left it.")


def test_a_garage_door_opens_after_a_yes_and_its_undo_asks_again(tmp_path):
    s = stack(tmp_path, ['[happy] <home device="Garage door" do="on"/>'], ["[happy] <undo/>"])
    ask = asyncio.run(answer(s, "open the garage", True))
    assert ask.question == "Open “Garage door”?", "on is open for a garage door"
    assert device(s, "cover.garage")["state"] == "open"
    asyncio.run(answer(s, "undo that", True))
    assert s.sink.of(Confirm)[-1].question == "Close “Garage door”?"
    assert device(s, "cover.garage")["state"] == "closed"


def test_an_unknown_device_says_so(tmp_path):
    s = stack(tmp_path, ['[happy] <home device="sauna" do="on"/>'])
    asyncio.run(say(s, "turn on the sauna"))
    assert said(s) == "That didn't work: I couldn't find “sauna” at home."


def test_no_home_says_how_to_connect_one(tmp_path):
    s = stack(tmp_path, ['[happy] <home device="lights" do="on"/>'], world={"home": []})
    asyncio.run(say(s, "lights on"))
    assert said(s) == "Home Assistant shows me no lights, switches or scenes yet."


def test_the_home_is_in_the_today_block_by_room_without_states(tmp_path):
    s = stack(tmp_path, ["[happy] Sure."])
    asyncio.run(say(s, "hi"))
    block = s.model.turns[0].split("<today>")[1].split("</today>")[0]
    assert "Home (Fake home), the names to use:\n- Kitchen: Kitchen ceiling light, Kitchen counter light\n" \
           "- Wohnzimmer: Stehlampe, Heizung\n- Other: Front door, Garage door\n- Scenes: Movie night" in block
    assert "locked" not in block and "heat" not in block, "no states: they would resend the block"


def test_do_not_disturb_goes_on_without_a_question_and_undo_turns_it_off(tmp_path):
    s = stack(tmp_path, ['[happy] <focus do="on"/>'], ["[happy] <undo/>"])
    asyncio.run(say(s, "turn on do not disturb"))
    assert world(s)["focus"] == {"Do Not Disturb": True}
    assert not s.sink.of(Confirm)
    assert said(s) == "Do Not Disturb is on."
    assert cards(s)[0].kind == "focus"
    asyncio.run(say(s, "undo that"))
    assert world(s)["focus"] == {"Do Not Disturb": False}


def test_a_focus_without_its_shortcut_offers_it_or_says_how_to_make_one(tmp_path):
    s = stack(tmp_path, ['[happy] <focus do="on"/>'], ['[happy] <focus do="on" name="Arbeit"/>'],
              world={"focus_missing": True})
    asyncio.run(say(s, "schalte bitte nicht stören für mich an", "und jetzt bitte den Fokus Arbeit an"))
    assert world(s)["focus_offers"] == 2
    assert said(s).startswith("Für Nicht stören brauche ich zwei kleine Kurzbefehle. Ich habe sie geöffnet")
    assert "Für Arbeit brauche ich Kurzbefehle: leg einen namens „Arbeit an“" in said(s)
    assert cards(s) == []


def test_a_scene_that_unlocks_the_door_asks_like_the_lock_and_so_does_its_undo(tmp_path):
    home = [*HOME, {"id": "scene.welcome", "name": "Welcome home", "kind": "scene",
                    "members": ["lock.front", "light.floor"]}]
    s = stack(tmp_path, ['[happy] <home scene="Welcome home"/>'], ["[happy] <undo/>"], world={"home": home})
    ask = asyncio.run(answer(s, "welcome home scene", True))
    assert ask.question == "Start the scene “Welcome home”?"
    asyncio.run(answer(s, "undo that", False))
    assert s.sink.of(Confirm)[-1].question == "Lock “Front door”?", "putting the lock back asks too"
