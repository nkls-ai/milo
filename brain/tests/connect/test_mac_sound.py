"""Music, Spotify and the volume on the Mac (ADR 0036), with a fake script runner: nothing plays, nothing gets louder.

Spotify isn't installed where these were written, and Music shouldn't start playing during a test run, so these
check what the adapter asks the scripts for and how it reads their answers. The scripts themselves ran by hand only.
"""

import pytest

from milo.adapters.connect import mac_sound
from milo.adapters.connect.mac_sound import MacMusicApps, MacVolume
from milo.core.types import ToolError

US = "\x1f"


class Scripts:
    """Answers each script with the next of `answers`, and keeps what it was asked."""

    def __init__(self, *answers: str):
        self.answers = list(answers)
        self.calls: list[tuple[str, tuple, str]] = []

    def __call__(self, script, *args, app, timeout_s=None):
        self.calls.append((script, args, app))
        return self.answers.pop(0) if self.answers else ""


def apps(scripts: Scripts, running=("Music",)) -> tuple[MacMusicApps, list[str]]:
    opened: list[str] = []
    return MacMusicApps(run=scripts, running=lambda app: app in running, open=opened.append), opened


def test_music_plays_from_the_library_and_says_what_played_before():
    scripts = Scripts(f"Taylor Swift{US}24\nSo What{US}Miles Davis{US}playing{US}ABC123{US}61")
    music, opened = apps(scripts)
    played = music.play("Taylor Swift", "artist")
    script, args, app = scripts.calls[0]
    assert (args, app) == (("Taylor Swift", "artist", str(mac_sound.MAX_TRACKS)), "Music")
    assert "Taylor Swift" not in script, "the query is an argument, never in the script's source"
    assert played == {"app": "Music", "title": "Taylor Swift", "count": 24,
                      "was": {"app": "Music", "track": "So What", "artist": "Miles Davis", "state": "playing",
                              "id": "ABC123", "position": "61"}}
    assert opened == []


def test_nothing_in_the_library_opens_musics_search():
    music, opened = apps(Scripts(""))
    assert music.play("Bad Bunny & Friends") == {"app": "Music", "title": "Bad Bunny & Friends", "searched": True,
                                                 "missing": True}
    assert opened == ["music://music.apple.com/search?term=Bad%20Bunny%20%26%20Friends"]


def test_spotify_plays_an_address_and_only_searches_anything_else():
    scripts = Scripts(f"Shake It Off{US}1\n")
    spotify, opened = apps(scripts, running=("Spotify",))
    assert spotify.which() == "Spotify", "the one running"
    assert spotify.scripts("Spotify", "Taylor Swift") is False
    assert spotify.play("Taylor Swift", "artist") == {"app": "Spotify", "title": "Taylor Swift", "searched": True,
                                                       "missing": False}
    assert opened == ["spotify:search:Taylor%20Swift"] and scripts.calls == [], "no script for a search"
    played = spotify.play("https://open.spotify.com/album/1989xyz?si=abc", "album", "spotify")
    assert scripts.calls[0][1:] == (("spotify:album:1989xyz",), "Spotify")
    assert played["title"] == "Shake It Off" and played["was"] == {}


def test_the_default_app_and_names():
    music, _ = apps(Scripts(), running=())
    assert music.which() == "Music", "nothing runs: Music"
    assert apps(Scripts(), running=("Music", "Spotify"))[0].which() == "Music"
    assert music.which("Apple Music") == "Music" and music.which("SPOTIFY") == "Spotify"
    assert music.which("YouTube") == ""
    with pytest.raises(ToolError, match="Music or Spotify"):
        music.play("jazz", app="YouTube")


def test_what_plays_prefers_a_playing_app_and_starts_none():
    scripts = Scripts(f"Song A{US}Band{US}paused{US}id1{US}5", f"Song B{US}Other{US}playing{US}spotify:track:2{US}9")
    music, _ = apps(scripts, running=("Music", "Spotify"))
    assert music.running() == ["Music", "Spotify"]
    now = music.playing(["Music", "Spotify"])
    assert (now["app"], now["track"], now["state"]) == ("Spotify", "Song B", "playing")
    assert music.playing([]) == {} and len(scripts.calls) == 2


def test_resume_and_pause():
    scripts = Scripts()
    music, _ = apps(scripts, running=("Music",))
    music.resume({"app": "Music", "id": "ABC123", "position": "61"})
    assert scripts.calls[-1][1:] == (("ABC123", "61"), "Music")
    music.pause("Spotify")
    assert len(scripts.calls) == 1, "Spotify doesn't run: nothing to pause, and no script starts it"
    music.pause("Music")
    assert scripts.calls[-1][2] == "Music"
    with pytest.raises(ToolError):
        music.resume({"app": "Music"})


def test_the_volume_reads_and_sets_as_arguments():
    scripts = Scripts(f"44{US}false", f"40{US}false", f"40{US}true")
    volume = MacVolume(run=scripts)
    assert volume.get() == {"level": 44, "muted": False}
    assert volume.set(140, False) == {"level": 40, "muted": False}
    assert scripts.calls[1][1] == ("100", "false"), "never past 100"
    assert volume.set(None, True) == {"level": 40, "muted": True}
    assert scripts.calls[2][1] == ("", "true")


def test_an_output_without_a_volume_is_plain_words():
    with pytest.raises(ToolError, match="no volume"):
        MacVolume(run=Scripts(f"missing value{US}false")).get()
