"""Opening an app, a web page or a file the moment the user asks: what to open and whether their words named it.

The talker writes `<open app="Google Chrome" url="https://www.youtube.com"/>` (or `<open app="Notes"/>`, or
`<open path="~/Downloads"/>`), and Milo opens it straight away through the app, with no helper. Only web
addresses (http and https) open as URLs: another scheme can run a shortcut, a script or change a setting, so it
is refused here, and the app refuses files that would run code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com",
    "google maps": "https://maps.google.com", "maps": "https://maps.google.com",
    "google drive": "https://drive.google.com", "google docs": "https://docs.google.com",
    "wikipedia": "https://www.wikipedia.org", "github": "https://github.com", "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com", "reddit": "https://www.reddit.com", "twitter": "https://x.com",
    "x": "https://x.com", "facebook": "https://www.facebook.com", "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com", "spotify": "https://open.spotify.com", "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai", "whatsapp": "https://web.whatsapp.com", "outlook": "https://outlook.live.com",
    "twitch": "https://www.twitch.tv", "duckduckgo": "https://duckduckgo.com", "bing": "https://www.bing.com",
}
"""Sites people name without an address ("go on YouTube"), to their https address."""

_BARE = re.compile(r"^[a-z0-9][a-z0-9 -]{0,40}$", re.IGNORECASE)
_HOST = re.compile(r"^[a-z0-9.-]+(?::\d+)?$", re.IGNORECASE)
_SECOND_LEVEL = frozenset({"co", "com", "org", "net", "ac", "gov", "edu", "ne", "or"})
"""Second-level labels under a country code (co.uk, com.au): the name a person uses sits one label further left."""


@dataclass(frozen=True)
class OpenRequest:
    """An <open> tag: the app to open (or to open the page or file in), the page, the file or folder."""

    app: str = ""
    url: str = ""
    path: str = ""

    @property
    def what(self) -> str:
        """The thing opened, for a log line or a question: the page's host, the file's name, or the app."""
        if self.url:
            return urlsplit(self.url).hostname or self.url
        if self.path:
            return self.path.rstrip("/").rsplit("/", 1)[-1] or self.path
        return self.app


def resolve_url(text: str) -> str | None:
    """A web address to open: "https://www.youtube.com/..." as it is, "youtube.com" with https in front, a bare
    site name ("YouTube") from SITES or as www.<name>.com. None for anything that isn't a web page (another scheme,
    spaces in a host, nothing at all)."""
    text = " ".join((text or "").split()).strip().strip("“”\"'<>")
    if not text:
        return None
    lowered = text.lower()
    if lowered in SITES:
        return SITES[lowered]
    if "://" in text:
        parts = urlsplit(text)
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            return None
        return text
    if ":" in text.split("/", 1)[0] and not _HOST.match(text.split("/", 1)[0]):
        return None  # mailto:, javascript:, a custom scheme
    host = text.split("/", 1)[0]
    if "." in host and _HOST.match(host):
        return "https://" + text
    if _BARE.match(text) and " " not in text:
        return f"https://www.{lowered}.com"
    return None


def site_names(url: str) -> list[str]:
    """The words a person would use for a site: the name of the domain it belongs to ("youtube" for
    www.youtube.com, "bbc" for www.bbc.co.uk), and the SITES name of that address ("maps" for maps.google.com).
    Never another label of the host, so youtube.com.evil.example is "evil", not "youtube"."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    labels = [part for part in host.split(".") if part]
    names = []
    if len(labels) >= 2 and not labels[-1].isdigit():
        cut = 3 if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL else 2
        names.append(labels[-cut])
    origin = f"{urlsplit(url).scheme}://{host}"
    names += [site for site, address in SITES.items() if address == origin]
    return list(dict.fromkeys(names))


def named_by(request: OpenRequest, words: str) -> bool:
    """Whether the user's own words name what is to be opened, so opening it needs no yes even after Milo read
    outside text: the site's own name ("go on YouTube" for www.youtube.com). An app alone always counts: opening an
    app changes nothing. A file or folder never does: a name in passing can't tell which file outside text put
    there, so after outside text a path always asks."""
    if request.path:
        return False
    if request.url:
        said = set(re.findall(r"[\w-]+", (words or "").lower()))
        return any(name in said for name in site_names(request.url))
    return bool(request.app)
