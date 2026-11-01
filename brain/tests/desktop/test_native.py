"""Native bridge policy is tested without typing into the user's desktop."""
from dataclasses import replace
from pathlib import Path
import os

import pytest

from milo.desktop.native import BorrowRequired, Focus, NativeBridge, NativeError, PynputInput, writable


class Backend:
    def __init__(self):
        self.target = Focus("field-1", 987654, "Editor", "window-1", "Document", "text field", False,
                            True, "before", (20, 30, 200, 100))
        self.values = []
        self.presses = []

    def focus(self):
        return self.target

    def windows(self):
        return [self.target]

    def activate(self, app):
        if app != self.target.app:
            raise NativeError("Not running")
        return self.target

    def elements(self, app=""):
        return [self.target]

    def at_point(self, x, y):
        return self.target

    def press(self, target):
        self.presses.append(target.identity)

    def set_value(self, target, text):
        self.values.append(text)
        self.target = replace(self.target, text=text)

    def selected_text(self, target):
        return "selection"


class Clipboard:
    def __init__(self):
        self.value = "old clipboard"
        self.restores = []

    def text(self):
        return self.value

    def set_text(self, text):
        self.value = text

    def snapshot(self):
        return self.value

    def restore_later(self, snapshot, inserted):
        self.restores.append((snapshot, inserted))


class Input:
    def __init__(self):
        self.shortcuts = []
        self.clicks = []
        self.scrolls = []

    def shortcut(self, combo):
        self.shortcuts.append(combo)

    def click(self, *args):
        self.clicks.append(args)

    def scroll(self, *args):
        self.scrolls.append(args)


class Keys:
    """The OS key platform; its paste lands in the same list as the worker's shortcuts."""

    def __init__(self, input_device):
        self.input = input_device
        self.why_blocked = ""

    def paste_keys(self):
        self.input.shortcuts.append("ctrl+v")

    def blocked(self, pid):
        return self.why_blocked

    def idle_s(self):
        return 0.0


@pytest.fixture
def bridge(tmp_path):
    backend, clipboard, input_device = Backend(), Clipboard(), Input()
    value = NativeBridge(tmp_path, backend=backend, clipboard=clipboard, input_device=input_device,
                         keys=Keys(input_device))
    value.remember_focus()
    return value


def test_dictation_retains_unicode_and_restores_clipboard(bridge):
    result = bridge.paste_dictation(" Grüß dich 🐦\nsecond line")
    assert result["pasted"] and result["app"] == "Editor"
    assert bridge._input.shortcuts == ["ctrl+v"]
    assert bridge.clipboard.restores == [("old clipboard", " Grüß dich 🐦\nsecond line")]
    assert bridge.input_busy


@pytest.mark.parametrize("changes", [{"secure": True}, {"app": "Bitwarden"}])
def test_never_paste_into_password_fields_or_managers(bridge, changes):
    bridge.backend.target = replace(bridge.backend.target, **changes)
    bridge.remember_focus()
    assert bridge.paste_dictation("text") == {"pasted": False, "why": "secure"}
    assert not bridge._input.shortcuts
    assert bridge.clipboard.text() == "old clipboard"


@pytest.mark.parametrize("changes", [{"editable": False}, {"app": "powershell"}, {"app": "WindowsTerminal"},
                                     {"app": "Visual Studio Code"}])
def test_dictation_pastes_where_the_focus_is_even_unverified_as_on_the_mac(bridge, changes):
    """Chrome before its tree wakes, Electron apps, terminals and editors take a paste without a known field."""
    bridge.backend.target = replace(bridge.backend.target, **changes)
    bridge.remember_focus()
    result = bridge.paste_dictation("text")
    assert result["pasted"] and result["field"] == "", "unverified: no undo record"
    assert bridge._input.shortcuts == ["ctrl+v"]
    assert bridge.clipboard.restores == [("old clipboard", "text")]


def test_line_breaks_never_go_into_a_terminal(bridge):
    bridge.backend.target = replace(bridge.backend.target, app="WindowsTerminal")
    assert bridge.paste_dictation("rm -rf build\nnext") == {"pasted": False, "why": "terminal", "copied": True}
    assert not bridge._input.shortcuts


def test_an_elevated_window_keeps_the_words_to_copy(bridge):
    bridge.keys.why_blocked = "That window runs as administrator."
    result = bridge.paste_dictation("text")
    assert result["why"] == "elevated" and not bridge._input.shortcuts
    assert result["copied"] and bridge.clipboard.text() == "text"


class TypingKeys(Keys):
    """A platform that types Unicode keys (Windows), unless a modifier is held."""

    def __init__(self, input_device, held=False):
        super().__init__(input_device)
        self.typed, self.held = [], held

    def type_text(self, text):
        if self.held:
            return False
        self.typed.append(text)
        return True


@pytest.mark.parametrize("app", ["WindowsTerminal", "powershell"])
def test_a_terminal_gets_the_words_typed_not_pasted(bridge, app):
    """Claude Code in Windows Terminal drops a synthetic Ctrl+V; typed keys arrive, and the clipboard stays."""
    bridge.keys = TypingKeys(bridge._input)
    bridge.backend.target = replace(bridge.backend.target, app=app)
    bridge.remember_focus()
    result = bridge.paste_dictation("fix the tests")
    assert result["pasted"] and result["typed"]
    assert bridge.keys.typed == ["fix the tests"] and not bridge._input.shortcuts
    assert bridge.clipboard.text() == "old clipboard"


def test_a_terminal_pastes_when_typing_is_refused(bridge):
    bridge.keys = TypingKeys(bridge._input, held=True)
    bridge.backend.target = replace(bridge.backend.target, app="WindowsTerminal")
    bridge.remember_focus()
    assert bridge.paste_dictation("text")["pasted"]
    assert bridge._input.shortcuts == ["ctrl+v"]


def test_other_apps_still_paste_with_a_typing_platform(bridge):
    bridge.keys = TypingKeys(bridge._input)
    bridge.paste_dictation("text")
    assert not bridge.keys.typed and bridge._input.shortcuts == ["ctrl+v"]


def test_words_that_could_not_be_pasted_wait_on_the_clipboard(bridge):
    bridge.backend.target = replace(bridge.backend.target, app="WindowsTerminal")
    assert bridge.paste_dictation("one\ntwo") == {"pasted": False, "why": "terminal", "copied": True}
    assert bridge.clipboard.text() == "one\ntwo"


def test_after_focus_moves_the_words_go_where_it_is_now(bridge):
    bridge.backend.target = replace(bridge.backend.target, identity="other-field")
    result = bridge.paste_dictation("text")
    assert result["pasted"] and result["field"] == ""
    assert bridge._input.shortcuts == ["ctrl+v"]


def test_a_verified_field_gets_a_space_after_a_word(bridge):
    bridge.backend.target = replace(bridge.backend.target, text="Hello")
    bridge.backend.selection_span = lambda _: (5, 5)
    bridge.remember_focus()
    bridge.paste_dictation("world")
    assert bridge.clipboard.restores == [("old clipboard", " world")]
    bridge.backend.target = replace(bridge.backend.target, text="Hello (")
    bridge.backend.selection_span = lambda _: (7, 7)
    bridge.paste_dictation("world")
    assert bridge.clipboard.restores[-1][1] == "world"


def onscreen_finish(bridge):
    captured = bridge.backend.target
    bridge.backend.target = replace(captured, identity="milo-finish", pid=os.getpid(), app="Milo")
    restored = []
    bridge.backend.refresh = lambda _: captured

    def focus_field(target):
        restored.append(target)
        bridge.backend.target = target
        return target

    bridge.backend.focus_field = focus_field
    bridge.arm_return_to_dictation_target()
    return captured, restored


def test_explicit_onscreen_finish_returns_only_to_exact_captured_field(bridge):
    captured, restored = onscreen_finish(bridge)
    assert bridge.paste_dictation("hello")["pasted"]
    assert restored == [captured] and bridge._input.shortcuts == ["ctrl+v"]
    assert bridge._dictation_return is None


def test_milo_focus_without_explicit_finish_never_activates_external_app(bridge):
    _, restored = onscreen_finish(bridge)
    bridge._dictation_return = None
    assert bridge.paste_dictation("hello")["why"] == "here"
    assert restored == [] and not bridge._input.shortcuts


def test_explicit_finish_never_takes_focus_from_another_external_app(bridge):
    captured, restored = onscreen_finish(bridge)
    bridge.backend.target = replace(captured, identity="other-app", pid=1234567)
    result = bridge.paste_dictation("hello")
    assert result["pasted"] and result["field"] == "", "the words go where the user went, like any dictation"
    assert restored == [], "Milo never pulls the focus back from an app the user chose"
    assert bridge._dictation_return is None


@pytest.mark.parametrize("changes", [{"identity": "replaced-field"}, {"pid": 11111},
    {"window": "another-window"}, {"secure": True}, {"editable": False}, {"app": "PowerShell"}])
def test_return_revalidates_captured_field_before_activating(bridge, changes):
    captured, restored = onscreen_finish(bridge)
    bridge.backend.refresh = lambda _: replace(captured, **changes)
    assert not bridge.paste_dictation("hello")["pasted"]
    assert restored == [] and not bridge._input.shortcuts


def test_return_revalidates_focus_after_backend_activation(bridge):
    captured, restored = onscreen_finish(bridge)

    def unexpected_focus(target):
        restored.append(target)
        bridge.backend.target = replace(captured, identity="other-field")

    bridge.backend.focus_field = unexpected_focus
    assert not bridge.paste_dictation("hello")["pasted"]
    assert restored == [captured] and not bridge._input.shortcuts


def test_expired_or_changed_recording_cannot_return_focus(bridge):
    captured, restored = onscreen_finish(bridge)
    bridge._dictation_return = (captured.identity, captured.pid, -1)
    assert not bridge.paste_dictation("hello")["pasted"]
    bridge.arm_return_to_dictation_target()
    bridge._remembered = replace(captured, identity="new-recording")
    assert not bridge.paste_dictation("hello")["pasted"]
    assert restored == [] and not bridge._input.shortcuts


def test_helper_text_write_cannot_use_explicit_dictation_return(bridge):
    _, restored = onscreen_finish(bridge)
    assert not bridge.app_request("text.write", {"text": "helper"})["pasted"]
    assert restored == [] and not bridge._input.shortcuts


def test_explicit_finish_uses_os_pid_without_querying_own_qt_accessibility(bridge):
    captured, restored = onscreen_finish(bridge)
    bridge.backend.foreground_pid = lambda: bridge.backend.target.pid
    reader = bridge.backend.focus

    def only_query_external_provider():
        assert bridge.backend.target.pid != os.getpid(), "own Qt provider would block the GUI thread"
        return reader()

    bridge.backend.focus = only_query_external_provider
    bridge.arm_return_to_dictation_target()
    assert bridge.paste_dictation("hello")["pasted"]
    assert restored == [captured]


def test_stale_accessibility_focus_never_counts_as_a_verified_field(bridge):
    bridge.backend.keyboard_focus_matches = lambda _: False
    result = bridge.paste_dictation("text")
    assert result["pasted"] and result["field"] == "", "no undo for a field the keyboard isn't in"
    assert not bridge._writes


def test_focus_race_after_clipboard_change_falls_back_to_the_new_focus(bridge):
    def set_text(text):
        bridge.clipboard.value = text
        bridge.backend.target = replace(bridge.backend.target, identity="moved")
    bridge.clipboard.set_text = set_text
    result = bridge.paste_dictation("text")
    assert result["pasted"] and result["field"] == "" and not bridge._writes
    assert bridge._input.shortcuts == ["ctrl+v"]


def test_helper_writes_stay_strict(bridge):
    bridge.backend.target = replace(bridge.backend.target, identity="other-field")
    assert bridge.app_request("text.write", {"text": "draft"}) == {"pasted": False, "why": "moved"}
    bridge.backend.target = replace(bridge.backend.target, identity="field-1", app="WindowsTerminal")
    bridge.remember_focus()
    assert not bridge.app_request("text.write", {"text": "draft"})["pasted"]
    assert not bridge._input.shortcuts


def test_explicit_copy_works_without_a_focused_field(bridge):
    bridge.backend.target = None
    assert bridge.app_request("text.copy", {"text": "value"}) == {"copied": True}
    assert bridge.clipboard.text() == "value"


def test_undo_only_reverses_exact_paste_in_same_field(bridge):
    result = bridge.paste_dictation(" inserted")
    bridge.backend.target = replace(bridge.backend.target, text="before inserted")
    assert bridge.app_request("text.unwrite", {"field": result["field"], "text": " inserted"})["removed"]
    assert bridge.backend.values == ["before"]


def test_undo_refuses_when_user_has_edited(bridge):
    result = bridge.paste_dictation(" inserted")
    bridge.backend.target = replace(bridge.backend.target, text="before inserted user's edits")
    assert not bridge.app_request("text.unwrite", {"field": result["field"], "text": " inserted"})["removed"]
    assert not bridge.backend.values


def test_keyboard_input_waits_for_borrow_approval(bridge):
    bridge.hands_request("describe", {"tool": "key"})
    with pytest.raises(BorrowRequired) as caught:
        bridge.hands_request("key", {"combo": "ctrl+s"})
    assert caught.value.borrow == "keyboard" and not bridge._input.shortcuts
    bridge.session_event({"type": "hands_borrow", "on": True, "what": "keyboard"})
    bridge.hands_request("key", {"combo": "ctrl+s"})
    assert bridge._input.shortcuts == ["ctrl+s"]
    bridge.session_event({"type": "hands_session", "on": False})
    bridge.hands_request("describe", {"tool": "key"})
    with pytest.raises(BorrowRequired):
        bridge.hands_request("key", {"combo": "ctrl+s"})


def test_keyboard_input_refuses_changed_checked_target(bridge):
    bridge.hands_request("describe", {"tool": "key"})
    bridge.backend.target = replace(bridge.backend.target, identity="moved")
    bridge.session_event({"type": "hands_borrow", "on": True, "what": "keyboard"})
    with pytest.raises(NativeError, match="changed"):
        bridge.hands_request("key", {"combo": "ctrl+s"})
    assert not bridge._input.shortcuts


def test_element_tree_has_scoped_ids_and_passwords_are_excluded(bridge):
    assert "e0 text field" in bridge.hands_request("ax_tree", {})["text"]
    bridge.hands_request("ax_set_value", {"element": "e0", "text": "replacement"})
    assert bridge.backend.values == ["replacement"]
    bridge.backend.target = replace(bridge.backend.target, secure=True)
    assert bridge.hands_request("ax_tree", {})["text"] == ""
    with pytest.raises(NativeError, match="expired"):
        bridge.hands_request("ax_press", {"element": "e0"})


def test_coordinates_map_pixels_to_global_points_for_scaled_secondary_monitor(bridge):
    bridge._shot = (-1920, 0, 3840, 2160, 2.0)
    assert bridge._point({"x": 200, "y": 100}) == (-1820, 50)
    with pytest.raises(NativeError, match="outside"):
        bridge._point({"x": 3840, "y": 0})


def test_click_uses_screen_mapping_and_waits_for_mouse_borrow(bridge):
    bridge._shot = (-1920, 0, 3840, 2160, 2.0)
    with pytest.raises(BorrowRequired):
        bridge.hands_request("click", {"x": 200, "y": 100})
    bridge.session_event({"type": "hands_borrow", "on": True, "what": "mouse"})
    bridge.hands_request("click", {"x": 200, "y": 100, "double": True})
    assert bridge._input.clicks == [(-1820, 50, "left", True)]


@pytest.mark.parametrize("url", ["file:///tmp/run.exe", "javascript:alert(1)", "https://", "https://x\ncommand"])
def test_open_url_rejects_non_web_targets(bridge, url):
    with pytest.raises(NativeError):
        bridge.hands_request("open_url", {"url": url})


def test_unavailable_integration_is_an_error(bridge):
    with pytest.raises(NativeError, match="not available"):
        bridge.app_request("calendar.create", {})
    with pytest.raises(NativeError, match="platform adapter"):
        bridge.hands_request("run_applescript", {"script": "anything"})


def test_wayland_does_not_claim_global_capture_or_input(monkeypatch, bridge):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert not bridge.capabilities()["global_input"]
    assert not bridge.capabilities()["screen_capture"]
    with pytest.raises(NativeError, match="Wayland"):
        bridge._screenshot()


def test_pc_injected_shortcut_and_risk_classifier_use_identical_key_aliases():
    from types import SimpleNamespace
    from milo.adapters.risk_policy import WINDOWS
    from milo.services.risk import Risk, classify, normalize_combo
    events = []
    injection = PynputInput.__new__(PynputInput)
    injection.policy = WINDOWS
    injection.keyboard = SimpleNamespace(Key=SimpleNamespace(ctrl="CONTROL", shift="SHIFT", delete="DELETE",
                                                              backspace="BACKSPACE"))
    injection.keys = SimpleNamespace(press=lambda key: events.append(("down", key)),
                                    release=lambda key: events.append(("up", key)))
    injection.shortcut("Command+Shift+Delete")
    assert events[:3] == [("down", "CONTROL"), ("down", "SHIFT"), ("down", "DELETE")]
    assert normalize_combo("Command+Shift+Delete", WINDOWS) == "ctrl+shift+forwarddelete"
    assert classify("key", {"combo": "Command+Shift+Delete"}, {}, WINDOWS).risk is Risk.ASK
    events.clear()
    injection.shortcut("Command+Backspace")
    assert events[:2] == [("down", "CONTROL"), ("down", "BACKSPACE")]


def test_idle_focus_poll_does_not_read_field_values_when_not_watching_corrections(bridge):
    from dataclasses import replace
    reads = []
    original = bridge.backend.focus
    bridge.backend.focus = lambda: (reads.append("value"), original())[1]
    bridge.backend.focus_metadata = lambda: (reads.append("metadata"), replace(original(), text=""))[1]
    bridge.poll_focus()
    assert reads == ["metadata"]
    assert bridge._external.text == ""
    bridge.set_learning(False)
    bridge.poll_focus()
    assert reads == ["metadata", "metadata"]


def test_undo_bookkeeping_does_not_retain_the_fields_value(bridge):
    result = bridge.paste_dictation(" inserted")
    record = bridge._writes[result["field"]]
    assert record.target.text == "" and isinstance(record.before_hash, bytes) and len(record.before_hash) == 32


def test_middle_of_field_paste_is_undone_at_its_verified_offset(bridge):
    bridge.backend.target = replace(bridge.backend.target, text="left right")
    bridge.backend.selection_span = lambda _: (5, 5)
    bridge.remember_focus()
    result = bridge.paste_dictation("middle ")
    bridge.backend.target = replace(bridge.backend.target, text="left middle right")
    assert bridge.app_request("text.unwrite", {"field": result["field"], "text": "middle "})["removed"]
    assert bridge.backend.target.text == "left right"


def test_paste_over_selected_text_restores_only_the_replaced_selection(bridge):
    bridge.backend.target = replace(bridge.backend.target, text="left old right")
    bridge.backend.selection_span = lambda _: (5, 8)
    bridge.remember_focus()
    result = bridge.paste_dictation("new")
    record = bridge._writes[result["field"]]
    assert record.replaced == "old" and record.target.text == ""
    bridge.backend.target = replace(bridge.backend.target, text="left new right")
    assert bridge.app_request("text.unwrite", {"field": result["field"], "text": "new"})["removed"]
    assert bridge.backend.target.text == "left old right"


def test_middle_field_undo_refuses_even_when_a_different_part_of_the_field_changed(bridge):
    bridge.backend.target = replace(bridge.backend.target, text="left right")
    bridge.backend.selection_span = lambda _: (5, 5)
    bridge.remember_focus()
    result = bridge.paste_dictation("middle ")
    bridge.backend.target = replace(bridge.backend.target, text="edited left middle right")
    assert not bridge.app_request("text.unwrite", {"field": result["field"], "text": "middle "})["removed"]
    assert not bridge.backend.values


def test_without_any_focus_information_nothing_is_pasted(bridge):
    bridge.backend.target = None
    assert bridge.paste_dictation("text") == {"pasted": False, "why": "no_field", "copied": True}
    bridge.backend.foreground_pid = lambda: 4242  # the OS still names the app in front
    assert bridge.paste_dictation("text")["pasted"]
