"""A scripted brain for --smoke-test and the QML tests: wire events as the real brain sends them, scene by scene.

Each scene is a list of (milliseconds after the last step, event); `ear` steps stand for the hotkeys' instant key
feedback, `connected` for the socket. The scenes end in a state worth a screenshot.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

CONVERSATION = "c-smoke-1"


def _ts(minutes_ago: float = 0) -> str:
    return (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")


def _info(cid: str, title: str, minutes_ago: float, **extra) -> dict:
    return {"id": cid, "kind": "chat", "started": _ts(minutes_ago + 2), "last": _ts(minutes_ago), "title": title,
            "titled_by": "milo", "via": ["voice"], "turns": 1, "preview": "", "tasks": [], **extra}


def welcome() -> list[tuple[int, dict]]:
    """A brain that just connected: settings, keys, the list of conversations and the one going on."""
    first = [
        {"id": "u1", "ts": _ts(6), "kind": "user", "text": "rename the photos from Friday", "via": "voice",
         "conversation": CONVERSATION},
        {"id": "m1", "ts": _ts(6), "kind": "milo", "text": "On it, I'll sort them by date.", "emotion": "happy",
         "done": True, "conversation": CONVERSATION},
        {"id": "t1", "ts": _ts(5.9), "kind": "task", "text": "Rename the photos from Friday by date taken",
         "title": "Rename Friday's photos", "status": "done",
         "result": "I renamed all 40 photos. The list is in Pictures/Friday/renamed.txt.",
         "steps": [{"id": "s1", "kind": "read", "title": "Looking in your Pictures folder", "status": "done"},
                   {"id": "s2", "kind": "edit", "title": "Renaming 40 photos", "status": "done"}],
         "conversation": CONVERSATION},
    ]
    return [
        (0, {"type": "connected"}),
        (0, {"type": "ui_config", "dictate_key": "right_control", "talk_key": "right_option", "hands_free_max_s": 300}),
        (0, {"type": "settings", "settings": [{"section": "ui", "key": "hide_after_s", "value": 0, "options": [],
                                               "labels": [], "live": True}]}),
        (0, {"type": "conversations", "current": CONVERSATION, "more": False, "conversations": [
            _info(CONVERSATION, "Photos from Friday", 1, preview="I renamed all 40 photos.",
                  tasks=[{"id": "t1", "title": "Rename Friday's photos", "status": "done", "at": _ts(5.9)}]),
            _info("c-smoke-2", "Train to Hamburg", 90, via=["message"], preview="The 8:12 is on time."),
            _info("c-smoke-3", "Monday report", 60 * 24 * 3, kind="routine", preview="The report is in Reports."),
            _info("c-smoke-4", "Weekly sync", 60 * 26, kind="meeting", preview="Launch moves to Friday."),
        ]}),
        (0, {"type": "history", "entries": first}),
        (0, {"type": "undo_points", "points": [{"id": "t1", "title": "Rename Friday's photos", "state": "ready",
                                                "said": "I renamed all 40 photos."}]}),
    ]


def turn() -> list[tuple[int, dict]]:
    """Hold the talk key, speak, let go; Milo thinks and answers in a stream of words, then speaks and rests."""
    reply = ["Your ", "standup ", "is ", "at ", "**10:00**", " with Anna and Ben.\n\n",
             "- Bring the launch notes\n", "- Ask about Friday"]
    steps: list[tuple[int, dict]] = [
        (0, {"type": "ear", "kind": "armed", "mode": "talk"}),
        (90, {"type": "ear", "kind": "open", "mode": "talk"}),
        (0, {"type": "state", "state": "listening"}),
    ]
    for level in (0.1, 0.35, 0.5, 0.42, 0.3):
        steps.append((50, {"type": "level", "value": level}))
    steps += [
        (60, {"type": "partial", "text": "what's on my"}),
        (120, {"type": "partial", "text": "what's on my calendar"}),
        (60, {"type": "ear", "kind": "caught", "mode": "talk"}),
        (0, {"type": "state", "state": "transcribing"}),
        (150, {"type": "heard", "text": "what's on my calendar"}),
        (0, {"type": "entry", "entry": {"id": "u2", "ts": _ts(), "kind": "user", "text": "what's on my calendar",
                                         "via": "voice", "conversation": CONVERSATION}}),
        (0, {"type": "state", "state": "thinking"}),
        (200, {"type": "entry", "entry": {"id": "m2", "ts": _ts(), "kind": "milo", "text": "", "emotion": "happy",
                                           "done": False, "conversation": CONVERSATION}}),
    ]
    for piece in reply:
        steps.append((60, {"type": "reply_delta", "id": "m2", "text": piece}))
    steps += [
        (0, {"type": "state", "state": "speaking"}),
        (0, {"type": "emotion", "emotion": "happy"}),
        (0, {"type": "bubble", "text": "Your standup is at 10:00 with Anna and Ben."}),
        (300, {"type": "entry", "entry": {"id": "m2", "ts": _ts(), "kind": "milo", "emotion": "happy", "done": True,
                                           "conversation": CONVERSATION,
                                           "text": "".join(reply)}}),
    ]
    return steps


def at_rest() -> list[tuple[int, dict]]:
    return [(0, {"type": "state", "state": "idle"})]


def dictation() -> list[tuple[int, dict]]:
    """Hold the dictate key, speak, let go: the words go into the focused app, or are kept when they can't."""
    return [
        (0, {"type": "ear", "kind": "armed", "mode": "dictate"}),
        (90, {"type": "ear", "kind": "open", "mode": "dictate"}),
        (0, {"type": "state", "state": "dictating"}),
        (80, {"type": "partial", "text": "Sounds good, ship it."}),
        (60, {"type": "ear", "kind": "caught", "mode": "dictate"}),
        (0, {"type": "state", "state": "transcribing"}),
        (120, {"type": "dictation", "text": "Sounds good, ship it."}),
        (0, {"type": "state", "state": "idle"}),
    ]


def helpers() -> list[tuple[int, dict]]:
    return [
        (0, {"type": "entry", "entry": {"id": "t3", "ts": _ts(), "kind": "task", "text": "Budget table in Excel",
                                         "title": "Budget table in Excel", "status": "running",
                                         "steps": [{"id": "hands_1", "title": "Typing “Monday” in Excel",
                                                    "status": "running"}], "conversation": CONVERSATION}}),
        (0, {"type": "helpers", "helpers": [
            {"id": "t3", "title": "Budget table in Excel", "status": "working", "step": "Typing “Monday” in Excel",
             "progress": 0.4, "screen": True},
            {"id": "h2", "title": "Flights to Lisbon", "status": "queued", "step": "Waiting for a free helper"}]}),
        (0, {"type": "hands_session", "on": True}),
        (0, {"type": "activity", "task_id": "t3", "step": {"id": "hands_1", "title": "Typing “Monday” in Excel",
                                                          "status": "running"}}),
        (0, {"type": "fly_to", "point": {"x": 640.0, "y": 360.0}}),
    ]


def confirm() -> list[tuple[int, dict]]:
    return [
        (0, {"type": "confirm", "id": "q-smoke", "question": "Replace 8 filled cells in “Budget”?", "always": True,
             "money": False}),
        (0, {"type": "bubble", "text": "Replace 8 filled cells in “Budget”?"}),
    ]


SCENES = {"welcome": welcome, "turn": turn, "rest": at_rest, "dictation": dictation, "helpers": helpers,
          "confirm": confirm}


class Recorder(QObject):
    """A brain connection that keeps what the app sends and always takes it, for scripted runs."""
    event = Signal(dict)
    connection_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.commands: list[dict] = []

    def send(self, command: dict) -> bool:
        self.commands.append(command)
        return True

    def close(self) -> None:
        pass


def play(controller, steps: list[tuple[int, dict]], done=lambda: None) -> None:
    """Feeds `steps` to the controller on the Qt event loop, at their pace."""
    queue = list(steps)

    def step():
        while queue:
            delay, event = queue[0]
            if delay and not getattr(step, "waited", False):
                step.waited = True
                QTimer.singleShot(delay, step)
                return
            step.waited = False
            queue.pop(0)
            kind = event.get("type")
            if kind == "connected":
                controller.on_connection(True)
            elif kind == "ear":
                controller.views.presence.ear(event["kind"], event["mode"])
            else:
                controller.on_event(event)
        done()
    step.waited = False
    step()


def play_now(controller, steps: list[tuple[int, dict]]) -> None:
    """The same steps without waiting, for tests that step the clock themselves."""
    play(controller, [(0, event) for _, event in steps])
