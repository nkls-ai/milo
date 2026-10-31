"""Music by name, what plays, and the sound output on this Mac (ADR 0036).

Music and Spotify through their AppleScript dictionaries, the output volume through Standard Additions (`set volume`,
which needs no Automation permission). Inputs go to the scripts as arguments, never into their source.

Music plays from the library: a playlist by its name, or the matching tracks through a playlist called "Milo" that
Milo fills again each time, shuffled for an artist, a genre or a search. What isn't in the library can't be played by
a script, so its search opens in Music instead. Spotify plays a Spotify address (spotify:… or open.spotify.com/…);
anything else opens its search, since a search can only be played through Spotify's web API.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from urllib.parse import quote

from milo.core.types import ToolError

from . import _osascript

APPS = {"music": "Music", "apple music": "Music", "itunes": "Music", "spotify": "Spotify"}
"""What the user or the model may call an app, and the app's name."""
KINDS = ("artist", "song", "album", "playlist", "genre", "any")
MAX_TRACKS = 200
"""How many tracks a search puts in the "Milo" playlist, one by one."""
OPEN_TIMEOUT_S = 10

Run = Callable[..., str]
"""`_osascript.run`: (script, *args, app=...) -> stdout."""

# The track that played before, so Undo can play it again: name, artist, state, id, position in whole seconds.
_MUSIC_NOW = """
on now()
	set US to character id 31
	tell application "Music"
		if player state is stopped then return ""
		try
			set t to current track
			return (name of t) & US & (artist of t) & US & (player state as text) & US & (persistent ID of t) & ¬
				US & ((round (player position) rounding down) as text)
		end try
	end tell
	return ""
end now
"""

_MUSIC_NOW_RUN = _MUSIC_NOW + """
on run argv
	return now()
end run
"""

# Returns what plays (title, number of tracks) and, after a line break, what played before. Nothing found: "".
_MUSIC_PLAY = _MUSIC_NOW + """
on run argv
	set q to item 1 of argv
	set kind to item 2 of argv
	set lim to (item 3 of argv) as integer
	set US to character id 31
	set was to now()
	tell application "Music"
		if kind is "playlist" or kind is "any" then
			set lists to (every user playlist whose name is q)
			if lists is {} then set lists to (every user playlist whose name contains q)
			repeat with p in lists
				if (name of p) is not "Milo" and (count of tracks of p) > 0 then
					play p
					return (name of p) & US & ((count of tracks of p) as text) & linefeed & was
				end if
			end repeat
			if kind is "playlist" then return ""
		end if
		if kind is "song" then
			set found to (every track of library playlist 1 whose name is q)
			if found is {} then set found to (every track of library playlist 1 whose name contains q)
			if found is {} then return ""
			play item 1 of found
			return (name of item 1 of found) & US & "1" & linefeed & was
		end if
		if kind is "artist" then
			set found to (every track of library playlist 1 whose artist contains q)
		else if kind is "album" then
			set found to (every track of library playlist 1 whose album contains q)
		else if kind is "genre" then
			set found to (every track of library playlist 1 whose genre contains q)
		else
			set found to (search library playlist 1 for q)
		end if
		if found is missing value or found is {} then return ""
		if not (exists user playlist "Milo") then make new user playlist with properties {name:"Milo"}
		set mine to user playlist "Milo"
		delete every track of mine
		set n to 0
		repeat with t in found
			if n ≥ lim then exit repeat
			duplicate t to mine
			set n to n + 1
		end repeat
		set shuffle enabled to (kind is not "album")
		play mine
		return q & US & (n as text) & linefeed & was
	end tell
end run
"""

_MUSIC_RESUME = """
on run argv
	tell application "Music"
		play (first track of library playlist 1 whose persistent ID is (item 1 of argv))
		set player position to ((item 2 of argv) as integer)
	end tell
end run
"""

_MUSIC_PAUSE = """
on run argv
	tell application "Music" to pause
end run
"""

_SPOTIFY_NOW = """
on now()
	set US to character id 31
	tell application "Spotify"
		if player state is stopped then return ""
		try
			set t to current track
			return (name of t) & US & (artist of t) & US & (player state as text) & US & (spotify url of t) & ¬
				US & ((round (player position) rounding down) as text)
		end try
	end tell
	return ""
end now
"""

_SPOTIFY_NOW_RUN = _SPOTIFY_NOW + """
on run argv
	return now()
end run
"""

_SPOTIFY_PLAY = _SPOTIFY_NOW + """
on run argv
	set was to now()
	tell application "Spotify"
		play track (item 1 of argv)
		delay 0.3
		set US to character id 31
		set t to ""
		try
			set t to name of current track
		end try
		return t & US & "1" & linefeed & was
	end tell
end run
"""

_SPOTIFY_RESUME = """
on run argv
	tell application "Spotify"
		play track (item 1 of argv)
		set player position to ((item 2 of argv) as integer)
	end tell
end run
"""

_SPOTIFY_PAUSE = """
on run argv
	tell application "Spotify" to pause
end run
"""

_NOW = {"Music": _MUSIC_NOW_RUN, "Spotify": _SPOTIFY_NOW_RUN}
_RESUME = {"Music": _MUSIC_RESUME, "Spotify": _SPOTIFY_RESUME}
_PAUSE = {"Music": _MUSIC_PAUSE, "Spotify": _SPOTIFY_PAUSE}
_SEARCH = {"Music": "music://music.apple.com/search?term={q}", "Spotify": "spotify:search:{q}"}


def _app_name(app: str) -> str:
    return APPS.get(" ".join(app.lower().split()), "")


def _spotify_address(query: str) -> str:
    """A Spotify address the app can play: spotify:track:…, or one from open.spotify.com/album/…; else ""."""
    query = query.strip()
    if query.startswith("spotify:") and not query.startswith("spotify:search:"):
        return query
    if "open.spotify.com/" in query:
        path = query.split("open.spotify.com/", 1)[1].split("?", 1)[0].strip("/").split("/")
        if len(path) >= 2 and path[-2] in ("track", "album", "playlist", "artist", "episode", "show"):
            return f"spotify:{path[-2]}:{path[-1]}"
    return ""


def _song(app: str, out: str) -> dict:
    r = out.split(_osascript.US)
    if len(r) < 5 or not r[0]:
        return {}
    return {"app": app, "track": r[0], "artist": r[1], "state": r[2], "id": r[3], "position": r[4]}


class MacMusicApps:
    """Music and Spotify. `run` runs a script (`_osascript.run`); `running` says whether an app runs (pgrep), `open`
    opens an address: a test passes its own, so nothing plays."""

    def __init__(self, *, run: Run = _osascript.run, running: Callable[[str], bool] | None = None,
                 open: Callable[[str], None] | None = None):
        self._run = run
        self._is_running = running or _is_running
        self._open = open or _open

    def which(self, app: str = "") -> str:
        if app.strip():
            return _app_name(app)
        running = self.running()
        return "Spotify" if running == ["Spotify"] else "Music"

    def scripts(self, app: str, query: str) -> bool:
        return app == "Music" or bool(_spotify_address(query))

    def play(self, query: str, kind: str = "any", app: str = "") -> dict:
        app = self.which(app)
        if not app:
            raise ToolError("I can play by name in Music or Spotify.")
        kind = kind if kind in KINDS else "any"
        if app == "Spotify":
            address = _spotify_address(query)
            if not address:
                return self._search(app, query, missing=False)
            out = self._run(_SPOTIFY_PLAY, address, app=app)
        else:
            out = self._run(_MUSIC_PLAY, query, kind, str(MAX_TRACKS), app=app)
        played, _, was = out.partition("\n")
        title, _, count = played.partition(_osascript.US)
        if not played:
            return self._search(app, query, missing=True)
        return {"app": app, "title": title or query, "count": int(count) if count.isdigit() else 1,
                "was": _song(app, was)}

    def running(self) -> list[str]:
        return [app for app in ("Music", "Spotify") if self._is_running(app)]

    def playing(self, apps: list[str]) -> dict:
        found: dict = {}
        for app in apps:
            if app not in _NOW:
                continue
            song = _song(app, self._run(_NOW[app], app=app, timeout_s=5))
            if song.get("state") == "playing":
                return song
            found = found or song
        return found

    def resume(self, was: dict) -> None:
        app = str(was.get("app") or "")
        if app not in _RESUME or not was.get("id"):
            raise ToolError("I don't know what played before.")
        self._run(_RESUME[app], str(was["id"]), str(was.get("position") or 0), app=app)

    def pause(self, app: str) -> None:
        app = _app_name(app)
        if app and self._is_running(app):
            self._run(_PAUSE[app], app=app)

    def _search(self, app: str, query: str, *, missing: bool) -> dict:
        self._open(_SEARCH[app].format(q=quote(query)))
        return {"app": app, "title": query, "searched": True, "missing": missing}


def _is_running(app: str) -> bool:
    try:
        return subprocess.run(["pgrep", "-xq", app], timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _open(address: str) -> None:
    try:
        done = subprocess.run(["open", address], capture_output=True, timeout=OPEN_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        raise ToolError("I couldn't open the search.") from None
    if done.returncode != 0:
        raise ToolError("I couldn't open the search: is the app installed?")


_VOLUME_GET = """
on run argv
	set s to get volume settings
	return ((output volume of s) as text) & (character id 31) & ((output muted of s) as text)
end run
"""

_VOLUME_SET = """
on run argv
	if item 1 of argv is not "" then set volume output volume ((item 1 of argv) as integer)
	if item 2 of argv is "true" then set volume output muted true
	if item 2 of argv is "false" then set volume output muted false
	set s to get volume settings
	return ((output volume of s) as text) & (character id 31) & ((output muted of s) as text)
end run
"""


class MacVolume:
    """The output volume, 0 to 100, and whether it is muted."""

    def __init__(self, *, run: Run = _osascript.run):
        self._run = run

    def get(self) -> dict:
        return self._settings(self._run(_VOLUME_GET, app="the sound settings", timeout_s=10))

    def set(self, level: int | None = None, muted: bool | None = None) -> dict:
        given = "" if level is None else str(max(0, min(100, int(level))))
        mute = "" if muted is None else ("true" if muted else "false")
        return self._settings(self._run(_VOLUME_SET, given, mute, app="the sound settings", timeout_s=10))

    @staticmethod
    def _settings(out: str) -> dict:
        level, _, muted = out.partition(_osascript.US)
        if not level.strip().isdigit():
            raise ToolError("This sound output has no volume I can set.")
        return {"level": int(level), "muted": muted.strip() == "true"}
