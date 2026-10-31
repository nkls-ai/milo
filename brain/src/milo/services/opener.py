"""Opening what the user asked for at once: an app, a web page (in the browser they named) or a file or folder.

The talker's `<open>` tag lands here while its reply still streams, and the app opens it and brings it to the
front (ADR 0028). No helper, no harness turn and no question: opening changes nothing, and LiveTalk only lets an
address or a file through without a yes when the user's own words named it or the conversation read no outside
text.
"""

from __future__ import annotations

import logging

from milo.core import words
from milo.core.events import ActionDone, Status
from milo.core.logtext import private
from milo.core.opening import OpenRequest
from milo.core.ports import AppHands, Clock, EventSink
from milo.core.types import HandsError
from milo.core.words import say

log = logging.getLogger("milo.open")


def action(request: OpenRequest) -> tuple[str, dict]:
    """The app action that opens `request`: open_url (a page, in `app` if named; the app checks it opens web
    pages), open_file (a file or folder, always in its own app: a named one could be a terminal, which runs what it
    opens) or open_app."""
    if request.url:
        return "open_url", {"url": request.url, **({"app": request.app} if request.app else {})}
    if request.path:
        return "open_file", {"path": request.path}
    return "open_app", {"name": request.app}


class Opener:
    """Opens through the app (the AppHands port), outside any helper's task, and logs how long it took."""

    def __init__(self, hands: AppHands, sink: EventSink, clock: Clock):
        self._hands = hands
        self._sink = sink
        self._clock = clock

    async def open(self, request: OpenRequest, *, since: float | None = None, language: str = "") -> bool:
        """Open it and bring it to the front. `since` is when the user's words arrived (the clock's monotonic
        time), for the log. False if the app couldn't; the user then sees why in the bubble."""
        tool, args = action(request)
        started = self._clock.monotonic()
        try:
            result = await self._hands.act(tool, args)
        except HandsError as e:
            log.warning("could not open %s: %s", private(request.what), e)
            self._sink.emit(Status(say("opener.couldnt", language, what=request.what)))
            return False
        done = self._clock.monotonic()
        after = f", {done - since:.2f}s after the user's words" if since is not None else ""
        front = "" if result.get("front", True) else ", not in front"
        log.info("opened %s%s in %.2fs%s%s", private(request.what),
                 f" in {request.app}" if request.app and (request.url or request.path) else "", done - started,
                 after, front)
        # A card for it (ADR 0030): a click on it opens the page again, or the app it opened in.
        self._sink.emit(ActionDone("opened", request.what, request.url, app=str(result.get("app") or request.app),
                                   lang=words.language(language)))
        return True
