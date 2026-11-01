"""`window`: the Milo window's own state around the pages: the connection, notices, the composer, kept dictation,
the key names, and the buttons in its frame. Wire commands go out through `sender`, which says whether they left."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from ..hotkeys import physical_key
from ..presentation.keys import key_label
from ..presentation import thread
from ._qt import field

DEFAULT_KEYS = {"talk_key": "right_option", "dictate_key": "right_control"}
KEPT_REASONS = {"moved": "The focused field changed while you were speaking.",
                "secure": "Milo does not paste into protected fields.",
                "no_field": "No editable field was focused.",
                "keys_held": "Keys were still held down, so Milo didn't paste.",
                "here": "Milo's own window had the focus.",
                "terminal": "Milo doesn't paste line breaks into a terminal, where they would run a command."}
COPIED_NOTE = " Your words are on the clipboard: press Ctrl+V."
RECONNECTING = "Milo is reconnecting. Please try again when he is connected."


class WindowViewModel(QObject):
    connectedChanged = Signal()
    noticeChanged = Signal()
    keptChanged = Signal()
    talkKeyChanged = Signal()
    dictateKeyChanged = Signal()
    speakRepliesChanged = Signal()
    prefillChanged = Signal()
    focusTickChanged = Signal()
    stateChanged = Signal()
    pendingChanged = Signal()
    waitingChanged = Signal()
    recordingChanged = Signal()
    canRestartChanged = Signal()

    setupRequested = Signal()
    restartRequested = Signal()
    quitRequested = Signal()
    copyRequested = Signal(str)
    # A file or folder to show; a relative path is in the Milo workspace ("memory/dictionary.md").
    revealRequested = Signal(str)
    listenRequested = Signal(str)
    listenStopRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sender: Callable[[dict], bool] = lambda command: False
        self._last_entry: Callable[[], dict | None] = lambda: None
        self._values = {"connected": False, "notice": "", "kept": {}, "talkKey": key_label("right_option"),
                        "dictateKey": key_label(physical_key("right_control")), "speakReplies": False, "prefill": "",
                        "focusTick": 0, "state": "idle", "pending": "", "waiting": 0, "recording": "",
                        "canRestart": False}

    connected = field(bool, "connected", connectedChanged)
    notice = field(str, "notice", noticeChanged)
    # {text, reason}: dictation that couldn't be pasted, kept here to copy.
    kept = field("QVariantMap", "kept", keptChanged)
    talkKey = field(str, "talkKey", talkKeyChanged)
    dictateKey = field(str, "dictateKey", dictateKeyChanged)
    speakReplies = field(bool, "speakReplies", speakRepliesChanged)
    # Text to put in the composer, ready to finish and send ("Change it" on a recipe draft).
    prefill = field(str, "prefill", prefillChanged)
    # Bumped to put the cursor in the composer (Ctrl+L).
    focusTick = field(int, "focusTick", focusTickChanged)
    state = field(str, "state", stateChanged)
    # "Listening…" or "Thinking…" at the end of the thread while nothing has arrived yet.
    pending = field(str, "pending", pendingChanged)
    waiting = field(int, "waiting", waitingChanged)
    # The mode the composer's hold-to-talk button records in; "" when it isn't.
    recording = field(str, "recording", recordingChanged)
    canRestart = field(bool, "canRestart", canRestartChanged)

    def set(self, **values) -> None:
        for key, value in values.items():
            if self._values[key] != value:
                self._values[key] = value
                getattr(self, key + "Changed").emit()

    # ---- fed by the controller

    def follow(self, last_entry: Callable[[], dict | None]) -> None:
        """Where to look for the thread's last line, for the pending row."""
        self._last_entry = last_entry

    def apply(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "state":
            state = str(event.get("state", "idle"))
            self.set(state=state)
            if state not in ("listening", "dictating"):
                self.set(recording="")
        elif kind == "ui_config":
            self.configure_keys(event)
        elif kind in ("status",) and event.get("text"):
            self.set(notice=str(event["text"]))
        if kind in ("state", "entry", "reply_delta", "history", "conversation", "conversations"):
            self.set(pending=thread.pending(self._values["state"], self._last_entry()))

    def configure_keys(self, event: dict) -> None:
        names = {field: key_label(physical_key(str(event.get(field) or default)))
                 for field, default in DEFAULT_KEYS.items()}
        self.set(talkKey=names["talk_key"], dictateKey=names["dictate_key"])

    def set_connected(self, up: bool) -> None:
        self.set(connected=up, notice="" if up else "Connecting to Milo's brain…")
        if not up:
            self.set(state="idle", recording="", pending="")

    def keep_dictation(self, text: str, reason: str = "", copied: bool = False) -> None:
        why = (KEPT_REASONS.get(reason, reason) or "Your text couldn't be pasted.") + (COPIED_NOTE if copied else "")
        self.set(kept={"text": text, "reason": why}, notice=why)

    def set_waiting(self, questions: int, drafts: int) -> None:
        self.set(waiting=questions + drafts)

    # ---- what the window calls

    @Slot("QVariantMap", result=bool)
    def send(self, command: dict) -> bool:
        return self.sender(dict(command))

    @Slot(str, str, result=bool)
    def sendText(self, text: str, conversation: str) -> bool:
        """A turn typed in the window. True: it left, clear the field. False: keep the draft."""
        text = text.strip()
        if not text:
            return False
        if not self._values["connected"]:
            self.set(notice=RECONNECTING)
            return False
        command = {"type": "text", "text": text, "speak": self._values["speakReplies"]}
        if conversation:
            command["conversation"] = conversation
        return self.sender(command)

    @Slot(bool)
    def setSpeakReplies(self, on: bool) -> None:
        self.set(speakReplies=on)

    @Slot(str)
    def changeDraft(self, name: str) -> None:
        self.set(prefill="")
        self.set(prefill=f"Change {name}: ")

    @Slot()
    def takePrefill(self) -> None:
        self.set(prefill="")

    @Slot()
    def focusComposer(self) -> None:
        self.set(focusTick=self._values["focusTick"] + 1)

    @Slot(str)
    def listen(self, mode: str) -> None:
        """The composer's hold-to-talk button went down."""
        if self._values["recording"] or not self._values["connected"]:
            return
        self.set(recording=mode)
        self.listenRequested.emit(mode)

    @Slot()
    def stopListening(self) -> None:
        if not self._values["recording"]:
            return
        self.set(recording="")
        self.listenStopRequested.emit()

    @Slot()
    def dismissNotice(self) -> None:
        self.set(notice="")

    @Slot()
    def dismissKept(self) -> None:
        self.set(kept={})

    @Slot(str)
    def copy(self, text: str) -> None:
        self.copyRequested.emit(text)

    @Slot(str)
    def reveal(self, path: str) -> None:
        self.revealRequested.emit(path)

    @Slot()
    def stopAll(self) -> None:
        self.sender({"type": "stop_all"})

    @Slot()
    def openSetup(self) -> None:
        self.setupRequested.emit()

    @Slot()
    def restartBrain(self) -> None:
        self.restartRequested.emit()

    @Slot()
    def quit(self) -> None:
        self.quitRequested.emit()
