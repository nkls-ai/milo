"""The Usage page: tokens and dictations per day, and the accounts Milo uses. No model call.

`get_usage` must not hold up the next command (a key press), so the files are read and the accounts checked on
worker threads in a task of their own. The page gets the numbers at once, with the accounts from the last check;
when that check is older than ACCOUNTS_TTL_S it runs again and the page gets a second report with the new rows.
"""

from __future__ import annotations

import asyncio
import logging

from milo.core.events import UsageReport
from milo.core.ports import AccountProbe, Clock, EventSink, UsageHistory
from milo.core.usage import Account, Summary, start_of, summarize

log = logging.getLogger("milo.usage")

ACCOUNTS_TTL_S = 600.0
"""How long one check of the accounts is shown. Its key is nothing (one user, one Mac); it ends with time, and with
a restart, which a change of service in config.toml needs anyway."""


class UsageService:
    def __init__(self, history: UsageHistory, accounts: AccountProbe | None, sink: EventSink, clock: Clock, *,
                 ttl_s: float = ACCOUNTS_TTL_S):
        self._history = history
        self._probe = accounts
        self._sink = sink
        self._clock = clock
        self._ttl_s = ttl_s
        self._accounts: list[Account] = []
        self._checked: float | None = None
        self._tasks: set[asyncio.Task] = set()
        self._checking: asyncio.Task | None = None

    def request(self, span: int) -> None:
        """Answer `get_usage` in the background."""
        task = asyncio.create_task(self.send(span))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def idle(self) -> None:
        """Wait for the reports asked for so far. For tests and shutdown."""
        while pending := [t for t in self._tasks if not t.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    async def send(self, span: int) -> None:
        try:
            summary = await asyncio.to_thread(self.summary, span)
        except OSError as e:
            log.warning("couldn't read usage: %s", e)
            return
        self._sink.emit(self.report(summary))
        if self._probe is None or not self._stale():
            return
        if self._checking is None:
            self._checking = asyncio.create_task(asyncio.to_thread(self._probe.accounts))
        checking = self._checking
        try:
            self._accounts = await checking
            self._checked = self._clock.monotonic()
        except Exception:  # noqa: BLE001 - a probe bug must not take the page down
            log.exception("account check failed")
            return
        finally:
            if self._checking is checking:
                self._checking = None
        self._sink.emit(self.report(summary))

    def summary(self, span: int) -> Summary:
        today = self._clock.now().date()
        since = start_of(today, span)
        return summarize(self._history.calls(since), self._history.dictations(since), today, span,
                         self._history.first_day())

    def report(self, s: Summary) -> UsageReport:
        return UsageReport(s.span, s.today.isoformat(), s.since.isoformat() if s.since else "", s.daily, s.sources,
                           s.apps, [a.wire() for a in self._accounts])

    def _stale(self) -> bool:
        return self._checked is None or self._clock.monotonic() - self._checked >= self._ttl_s
