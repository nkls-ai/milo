"""The worker's tools for Milo's own files (ADR 0020). The worker can't write reminders.md, so it asks the brain
over run/tools.sock, and the brain asks the user before it adds the line."""

from __future__ import annotations

from milo.transport.tool_client import BrainClient

from .tools import WHEN, Tool, _need, _str, _text

TASK = "The task id from your instructions (\"Task id for undo_point and undo_note\")."

INSTRUCTIONS = """
Milo's reminders: milo_remind sets a reminder Milo says out loud at the time. Milo asks the user first. \
Don't edit reminders.md, routines, memory or config.toml yourself; you can't.
Undo: undo_point keeps a copy of a file before you change it, undo_note writes down how something was before \
you change it where no copy can be kept. Pass the task id from your instructions as `task`.
"""


class RemoteMilo:
    """The backend of Milo's own tools: asks the brain, which asks the user itself."""

    approves_itself = True

    def __init__(self, brain: BrainClient):
        self._brain = brain

    def remind(self, when: str, text: str) -> dict:
        return self._brain.request({"op": "reminder.add", "when": when, "text": text})

    def undo_point(self, path: str, task: str) -> dict:
        return self._brain.request({"op": "undo.point", "path": path, "task": task})

    def undo_note(self, text: str, task: str) -> dict:
        return self._brain.request({"op": "undo.note", "text": text, "task": task})


MILO_TOOLS: tuple[Tool, ...] = (
    Tool("milo_remind", "milo", "change",
         "Set one of Milo's own reminders: at that time Milo says it out loud on the Mac (and on the phone if "
         "messages are on). For the Reminders app, use reminders_add. Milo asks the user first.",
         {"when": _str(WHEN), "text": _str("What to remind the user of, one line.")}, ("when", "text"),
         lambda m, a: m.remind(_need(a, "when"), _need(a, "text"))),
    Tool("undo_point", "milo", "read",
         "Before you change, move or overwrite a file, keep a copy so the user can undo your task. For a file you are "
         "about to make, it notes that it is new. Excel workbooks Milo copies himself.",
         {"path": _str("The file's full path."), "task": _str(TASK)}, ("path",),
         lambda m, a: m.undo_point(_need(a, "path"), _text(a, "task"))),
    Tool("undo_note", "milo", "read",
         "Before a change Milo can't keep a copy for (text in a window, a note, an event, cells in Numbers), write "
         "down exactly what you change and how it was, so the user can undo your task.",
         {"text": _str("What you change and its old value, e.g. 'Note “Shopping” said: milk, eggs'."),
          "task": _str(TASK)}, ("text",),
         lambda m, a: m.undo_note(_need(a, "text"), _text(a, "task"))),
)
