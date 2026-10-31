"""Music by name, the volume and the screen's brightness from the talker (ADR 0036).

The user's story: "play Taylor Swift", "turn it down", "make the screen brighter" are what people say to Siri all
day. Milo could only press play and pause. Now the talker writes one tag, the brain does it at once on the user's
connections (made-up ones here: nothing plays, nothing gets louder), says one short line, shows a card, never asks,
and "undo that" puts it back.
"""

import asyncio
from pathlib import Path

from milo.adapters.connect.fake import World
from milo.core.events import ActionDone, Confirm
from milo.core.access import Access, AccessAnswer
from milo.services.today import Today
from tests.fakes import FakeClock
from tests.services.stack import Stack, settle

LIBRARY = {
    "songs": [{"title": "Shake It Off", "artist": "Taylor Swift", "album": "1989", "genre": "Pop"},
              {"title": "Blank Space", "artist": "Taylor Swift", "album": "1989", "genre": "Pop"},
              {"title": "So What", "artist": "Miles Davis", "album": "Kind of Blue", "genre": "Jazz"}],
    "playlists": {"Running": ["Shake It Off", "So What"]},
    "music_apps": ["Music"],
}


def stack(tmp_path: Path, *turns, world: dict | None = None, **kw) -> Stack:
    from tests.fakes import FakeLiveModel
    World(tmp_path / "world").save({"events": [], "reminders": [], **(world or {})})
    return Stack(model=FakeLiveModel(*turns), world=tmp_path / "world", home=tmp_path / "home", **kw)


def world(s: Stack) -> dict:
    return World(s.world).load()


async def say(s: Stack, *texts: str) -> None:
    for text in texts:
        await s.live_talk.start(text)
        await settle()
        await s.quick.idle()
        await s.undo.idle()
        await settle()


def said(s: Stack) -> str:
    return " ".join(s.voice.spoken)


def cards(s: Stack) -> list[ActionDone]:
    return s.sink.of(ActionDone)


def test_an_artist_plays_by_name_and_undo_pauses_it(tmp_path):
    s = stack(tmp_path, ['[happy] <music do="play" query="Taylor Swift" kind="artist"/>'], ["[happy] <undo/>"],
              world=LIBRARY)
    asyncio.run(say(s, "play Taylor Swift"))
    now = world(s)["now_playing"]
    assert (now["app"], now["artist"], now["state"]) == ("Music", "Taylor Swift", "playing")
    assert said(s) == "Playing Taylor Swift.", "the query, not one song of the artist's"
    [card] = cards(s)
    assert (card.kind, card.title, card.detail, card.app) == ("music", "Taylor Swift", "2 songs", "Music")
    assert card.undo and not s.sink.of(Confirm), "never asks"
    asyncio.run(say(s, "undo that"))
    assert world(s)["now_playing"]["state"] == "paused"


def test_undo_plays_again_what_played_before(tmp_path):
    before = {"app": "Music", "track": "So What", "artist": "Miles Davis", "state": "playing", "id": "So What",
              "position": "61"}
    s = stack(tmp_path, ['[happy] <music do="play" query="Running" kind="playlist"/>'], ["[happy] <undo/>"],
              world={**LIBRARY, "now_playing": before})
    asyncio.run(say(s, "play my running playlist"))
    assert said(s) == "Playing Running." and cards(s)[0].detail == "2 songs"
    asyncio.run(say(s, "undo that"))
    assert world(s)["now_playing"] == before


def test_a_song_plays_by_its_title_in_the_users_language(tmp_path):
    s = stack(tmp_path, ['[happy] <music do="play" query="blank space" kind="song"/>'], world=LIBRARY)
    asyncio.run(say(s, "spiel bitte Blank Space von Taylor Swift"))
    assert world(s)["now_playing"]["track"] == "Blank Space"
    assert said(s) == "Läuft: Blank Space."
    assert cards(s)[0].detail == "", "one song: no count"


def test_what_isnt_in_the_library_opens_the_search_and_says_so(tmp_path):
    s = stack(tmp_path, ['[happy] <music do="play" query="Bad Bunny" kind="artist"/>'], world=LIBRARY)
    asyncio.run(say(s, "play Bad Bunny"))
    assert world(s)["searches"] == [{"app": "Music", "query": "Bad Bunny"}]
    assert said(s) == "“Bad Bunny” isn't in your library, so the search is open in Music."
    [card] = cards(s)
    assert (card.detail, card.undo) == ("Search", ""), "nothing played, nothing to take back"


def test_spotify_can_only_open_a_search_and_milo_says_so_honestly(tmp_path):
    s = stack(tmp_path, ['[happy] <music do="play" query="Taylor Swift" kind="artist" app="Spotify"/>'],
              world=LIBRARY)
    asyncio.run(say(s, "play Taylor Swift on Spotify"))
    assert world(s)["searches"] == [{"app": "Spotify", "query": "Taylor Swift"}]
    assert said(s) == ("The search for “Taylor Swift” is open in Spotify. Pick one there, I can't start a search "
                       "myself.")


def test_the_running_app_or_the_configured_one_plays_when_the_user_names_none(tmp_path):
    s = stack(tmp_path, ['[happy] <music do="play" query="spotify:album:1989" kind="album"/>'],
              world={**LIBRARY, "music_apps": ["Spotify"]})
    asyncio.run(say(s, "play 1989"))
    assert world(s)["now_playing"]["app"] == "Spotify", "only Spotify runs"
    t = stack(tmp_path / "b", ['[happy] <music do="play" query="jazz" kind="genre"/>'],
              world={**LIBRARY, "music_apps": ["Spotify"]})
    t.quick._music_app = "Music"
    asyncio.run(say(t, "play some jazz"))
    assert world(t)["now_playing"]["track"] == "So What", "[connections] music_app wins"


def test_another_app_is_a_plain_line(tmp_path):
    s = stack(tmp_path, ['[happy] <music do="play" query="jazz" app="YouTube"/>'], world=LIBRARY)
    asyncio.run(say(s, "play jazz on YouTube"))
    assert said(s) == "That didn't work: I can play by name in Music or Spotify, not in YouTube."


def test_the_volume_goes_to_a_level_and_undo_sets_it_back(tmp_path):
    s = stack(tmp_path, ['[happy] <volume level="40"/>'], ["[happy] <undo/>"],
              world={"volume": {"level": 70, "muted": True}})
    asyncio.run(say(s, "volume to 40"))
    assert world(s)["volume"] == {"level": 40, "muted": False}, "a level the user asks for is heard"
    assert said(s) == "Volume at 40."
    [card] = cards(s)
    assert (card.kind, card.title) == ("sound", "Volume at 40") and not s.sink.of(Confirm)
    asyncio.run(say(s, "undo that"))
    assert world(s)["volume"] == {"level": 70, "muted": True}


def test_louder_quieter_and_mute(tmp_path):
    s = stack(tmp_path, ['[happy] <volume do="up"/>'], ['[happy] <volume do="down"/>'], ['[happy] <volume do="mute"/>'],
              ['[happy] <volume do="unmute"/>'], world={"volume": {"level": 95, "muted": False}})
    asyncio.run(say(s, "louder"))
    assert world(s)["volume"]["level"] == 100, "never past 100"
    asyncio.run(say(s, "quieter"))
    asyncio.run(say(s, "mute"))
    assert world(s)["volume"] == {"level": 90, "muted": True}
    asyncio.run(say(s, "mach bitte den Ton wieder an"))
    assert said(s) == "Volume at 100. Volume at 90. Sound off. Ton an, auf 90."


def test_a_volume_that_isnt_a_number_is_a_plain_line(tmp_path):
    s = stack(tmp_path, ['[happy] <volume level="loud"/>'])
    asyncio.run(say(s, "make it loud"))
    assert said(s) == "That didn't work: the volume must be a number from 0 to 100, not loud."


def test_the_screen_gets_brighter_and_undo_dims_it_again(tmp_path):
    s = stack(tmp_path, ['[happy] <brightness do="up" steps="4"/>'], ["[happy] <undo/>"],
              ['[happy] <brightness do="down"/>'])
    asyncio.run(say(s, "make the screen a lot brighter"))
    assert world(s)["brightness"] == 12
    assert said(s) == "Brighter."
    [card] = cards(s)
    assert (card.kind, card.title) == ("brightness", "Brighter") and card.undo
    asyncio.run(say(s, "undo that"))
    assert world(s)["brightness"] == 8
    asyncio.run(say(s, "dimmer"))
    assert world(s)["brightness"] == 6, "two steps when the model gives none"


def test_switched_off_they_say_so(tmp_path):
    import dataclasses
    s = stack(tmp_path, ['[happy] <volume level="40"/>'])
    s.quick._connections = dataclasses.replace(s.quick._connections, volume=None)
    asyncio.run(say(s, "volume to 40"))
    assert said(s) == "That didn't work: the volume is switched off in Milo's settings."


# ---- what plays, in <today>


class _Access:
    """The system: Music may be scripted, Spotify not yet."""

    def __init__(self, yes=("Music",)):
        self.yes = yes
        self.checked = []

    async def check(self, need, app=None):
        self.checked.append(app.name)
        return AccessAnswer(Access.YES if app.name in self.yes else Access.ASK, app)

    async def request(self, need, app=None):
        raise AssertionError("reading what plays never asks")

    async def places(self, app):
        return None


def test_today_says_what_plays_so_whats_this_song_needs_no_tool(tmp_path):
    playing = {"app": "Music", "track": "Shake It Off", "artist": "Taylor Swift", "state": "playing", "id": "x",
               "position": "3"}
    s = stack(tmp_path, world={**LIBRARY, "now_playing": playing})
    text, outside = asyncio.run(s.quick.today.note())
    assert "Music: playing “Shake It Off” by Taylor Swift in Music." in text and outside is False


def test_today_reads_only_apps_milo_may_script_already(tmp_path):
    from milo.services.access import AccessGate
    from tests.fakes import RecordingSink

    playing = {"app": "Spotify", "track": "Song", "artist": "Band", "state": "playing", "id": "x", "position": "3"}
    s = stack(tmp_path, world={**LIBRARY, "music_apps": ["Spotify"], "now_playing": playing})
    access = _Access()
    s.quick._access = AccessGate(access, RecordingSink(), pause_s=0)
    text, _ = asyncio.run(s.quick.today.note())
    assert "Song" not in text and access.checked == ["Spotify"], "no system question out of nowhere"
    access.yes = ("Spotify",)
    s.quick.today.changed()
    text, _ = asyncio.run(s.quick.today.note())
    assert "Music: playing “Song” by Band in Spotify." in text


def test_today_doesnt_read_what_plays_again_within_seconds(tmp_path):
    reads = []

    class Apps:
        def running(self):
            reads.append(1)
            return []

    from milo.core.ports import Connections
    clock = FakeClock()
    today = Today(Connections(music_apps=Apps()), clock)

    async def run():
        await today.note()
        await today.note()
        clock.advance(seconds=6)
        await today.note()

    asyncio.run(run())
    assert len(reads) == 2
