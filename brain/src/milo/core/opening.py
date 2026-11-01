"""Opening an app, a web page or a file the moment the user asks: what to open and whether their words named it.

The talker writes `<open app="Google Chrome" url="https://www.youtube.com"/>` (or `<open app="Notes"/>`, or
`<open path="~/Downloads"/>`), and Milo opens it straight away through the app, with no helper. Only web
addresses (http and https) open as URLs: another scheme can run a shortcut, a script or change a setting, so it
is refused here, and the app refuses files that would run code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote_plus, urlsplit

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
_SEARCH_ENGINES = ("google", "duckduckgo", "bing")
_SEARCH_WORDS = frozenset({"search", "google", "find", "look", "such", "suche", "suchen", "googel", "googeln", "finde"})
_STRUCTURE = frozenset({"wiki", "search", "results", "result", "watch", "web", "html", "htm", "php", "index",
                        "query", "search_query", "special", "spezial", "suche", "page", "the", "www"})
"""Words every address of its kind has (`/wiki/`, `/search?q=`), so they needn't come from the user."""
_LANGUAGE_KEYS = ("hl", "gl", "lang", "uselang")  # a page's language: hl=en
_PLAIN_HOST = re.compile(r"[a-z0-9][a-z0-9.-]*", re.IGNORECASE)
"""A host and nothing else: no user, password, port, backslash or other character a browser may read differently."""


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
            return self.path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or self.path
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


def named_by(request: OpenRequest, words: str) -> bool:
    """Whether the user's own words name what is to be opened, so opening it needs no yes even after Milo read
    outside text. An app alone always counts: opening an app changes nothing. A file or folder never does: a name in
    passing can't tell which file outside text put there.

    A page counts when its site is one the user named and every word in its address is theirs. The site: a SITES
    name they said, at its own address or a subdomain of it ("Wikipedia" for de.wikipedia.org), a search engine when
    they asked to search, or the address they said ("open bbc.co.uk"). The words: what the path and query say, but
    for the parts every such address has (`wiki`, `search`, `q`), so "search for Wikipedia" opens
    google.com/search?q=wikipedia. Outside text could have written the rest: youtube.evil under the word "YouTube", a
    word in the query carrying what Milo read out, or an address a browser reads differently from Python (a user
    part, a port, a backslash), so the address part must be a plain host."""
    if request.path:
        return False
    if not request.url:
        return bool(request.app)
    parts = urlsplit(request.url)
    if parts.fragment or not _PLAIN_HOST.fullmatch(parts.netloc):
        return False
    host = parts.netloc.lower().rstrip(".")
    text = (words or "").lower()
    said = set(re.findall(r"[^\W_]+", text))
    if not _site_named(host, text, said):
        return False
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if any(not (key.lower() in _STRUCTURE or re.fullmatch(r"[a-z]{1,2}", key, re.I)) for key, _ in pairs):
        return False
    values = (value for key, value in pairs
              if not (key.lower() in _LANGUAGE_KEYS and re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", value, re.I)))
    rest = " ".join([unquote_plus(parts.path), *values]).lower()
    return all(word in said or word in _STRUCTURE for word in re.findall(r"[^\W_]+", rest))


def _plain_label(label: str, said: set[str]) -> bool:
    """A subdomain part that can't carry what Milo read: www, m(obile), a language edition (de.wikipedia.org), or a
    word the user said."""
    return label in ("www", "m") or re.fullmatch(r"[a-z]{2}", label) is not None or label in said


def _site_named(host: str, text: str, said: set[str]) -> bool:
    for site, address in SITES.items():
        own = (urlsplit(address).hostname or "").removeprefix("www.")
        if all(word in said for word in site.split()) and (host == own or host.endswith(f".{own}")) \
                and all(_plain_label(label, said) for label in host.removesuffix(own).split(".")[:-1]):
            return True
    if said & _SEARCH_WORDS:
        for engine in _SEARCH_ENGINES:
            own = (urlsplit(SITES[engine]).hostname or "").removeprefix("www.")
            if host in (own, f"www.{own}"):
                return True
    bare = host.removeprefix("www.")
    return "." in bare and re.search(rf"(?<![\w.-]){re.escape(bare)}(?![\w-])", text) is not None
