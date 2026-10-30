"""The worker's tools for Milo's own files (ADR 0020). The worker can't write reminders.md, so it asks the brain
over run/tools.sock, and the brain asks the user before it adds the line."""

from __future__ import annotations

from milo.transport.tool_client import BrainClient

from .tools import WHEN, Tool, _need, _str

INSTRUCTIONS = """
Milo's reminders: milo_remind sets a reminder Milo says out loud at the time. Milo asks the user first. \
Don't edit reminders.md, routines, memory or config.toml yourself; you can't.
"""


class RemoteMilo:
    """The backend of Milo's own tools: asks the brain, which asks the user itself."""

    approves_itself = True

    def __init__(self, brain: BrainClient):
        self._brain = brain

    def remind(self, when: str, text: str) -> dict:
        return self._brain.request({"op": "reminder.add", "when": when, "text": text})


MILO_TOOLS: tuple[Tool, ...] = (
    Tool("milo_remind", "milo", "change",
         "Set one of Milo's own reminders: at that time Milo says it out loud on the Mac (and on the phone if "
         "messages are on). For the Reminders app, use reminders_add. Milo asks the user first.",
         {"when": _str(WHEN), "text": _str("What to remind the user of, one line.")}, ("when", "text"),
         lambda m, a: m.remind(_need(a, "when"), _need(a, "text"))),
)
