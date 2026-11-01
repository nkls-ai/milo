from types import SimpleNamespace

import pytest

from milo.desktop.hotkeys import GlobalHotkeys, PushToTalk, combo_name, key_name


def machine():
    events, ears, focus, now = [], [], [], [0.0]
    state = PushToTalk(events.append, lambda: focus.append(True), lambda: now[0],
                       ear=lambda kind, mode: ears.append((kind, mode)))
    return state, events, ears, focus, now


def types(events):
    return [e["type"] for e in events]


def test_hold_records_at_once_shows_after_a_moment_then_stops():
    state, events, ears, focus, now = machine()
    state.press("dictate")
    assert focus == [True] and events == [{"type": "listen_start", "mode": "dictate", "tentative": True}]
    assert ears == [("armed", "dictate")] and state.deadline == pytest.approx(0.08)
    now[0] = 0.08
    state.expire()
    assert types(events)[-1] == "listen_confirm" and ears[-1] == ("open", "dictate")
    now[0] = 0.6
    state.release("dictate")
    assert types(events) == ["listen_start", "listen_confirm", "listen_stop"]
    assert ears == [("armed", "dictate"), ("open", "dictate"), ("caught", "dictate")]
    assert not state.active


def test_a_tap_keeps_recording_for_a_second_tap_then_is_cancelled():
    state, events, ears, _, now = machine()
    state.press("talk")
    now[0] = 0.05
    state.release("talk")
    assert types(events) == ["listen_start"] and state.active == "talk", "a second tap may still come"
    now[0] = 0.35
    state.expire()
    assert types(events) == ["listen_start", "listen_cancel"]
    assert ears == [("armed", "talk"), ("cancelled", "talk")] and not state.active


def test_double_tap_locks_the_first_recording_on_and_another_press_finishes():
    state, events, ears, _, now = machine()
    state.press("talk")
    now[0] = 0.05
    state.release("talk")
    now[0] = 0.2
    state.press("talk")
    now[0] = 0.25
    state.release("talk")
    assert state.locked and state.active == "talk"
    assert types(events) == ["listen_start", "listen_confirm"], "one recording, the first tap's words kept"
    assert ears[-1] == ("open", "talk")
    state.other_key()
    assert state.locked, "typing or Milo's own paste doesn't end a locked recording"
    now[0] = 10.0
    state.press("talk")
    assert types(events)[-1] == "listen_stop" and ears[-1] == ("caught", "talk") and not state.active


def test_a_long_second_press_is_an_ordinary_hold_of_the_same_recording():
    state, events, _, _, now = machine()
    state.press("dictate")
    now[0] = 0.05
    state.release("dictate")
    now[0] = 0.2
    state.press("dictate")
    now[0] = 1.0
    state.release("dictate")
    assert not state.locked and types(events) == ["listen_start", "listen_stop"]


def test_the_lock_is_reported_for_the_hands_free_look():
    locks, now = [], [0.0]
    events = []
    state = PushToTalk(events.append, clock=lambda: now[0], hands_free=locks.append)
    state.press("dictate")
    state.release("dictate")
    now[0] = 0.1
    state.press("dictate")
    state.release("dictate")
    assert locks == ["dictate"]
    now[0] = 3
    state.press("dictate")
    assert locks == ["dictate", ""], "the locked recording ended"
    state.press("talk")
    state.cancel()
    assert locks == ["dictate", ""], "an ordinary hold is never hands-free"


def test_the_mic_opens_before_the_focus_is_read():
    order = []
    state = PushToTalk(lambda e: order.append(e["type"]), lambda: order.append("focus"))
    state.press("talk")
    assert order == ["listen_start", "focus"]


def test_another_key_during_a_hold_is_a_shortcut():
    state, events, ears, _, now = machine()
    state.press("dictate")
    now[0] = 0.1
    state.other_key()
    assert types(events) == ["listen_start", "listen_cancel"] and ears[-1] == ("cancelled", "dictate")


def test_escape_cancels_even_a_locked_recording():
    state, events, ears, _, now = machine()
    state.press("talk")
    state.release("talk")
    now[0] = 0.1
    state.press("talk")
    state.release("talk")
    assert state.locked
    state.cancel()
    assert types(events)[-1] == "listen_cancel" and not state.active and ears[-1] == ("cancelled", "talk")


def test_hands_free_limit_stops_instead_of_discarding():
    state, events, ears, _, now = machine()
    state.max_locked = 5
    state.press("talk")
    state.release("talk")
    now[0] = 0.1
    state.press("talk")
    state.release("talk")
    now[0] = 5.2
    state.expire()
    assert types(events)[-1] == "listen_stop" and ears[-1] == ("caught", "talk") and not state.active


def test_repeated_press_does_not_restart_recording():
    state, events, _, _, _ = machine()
    state.press("talk")
    state.press("talk")
    state.press("dictate")
    assert len(events) == 1


def test_every_armed_ends_in_caught_or_cancelled():
    state, events, ears, _, now = machine()
    for hold in (0.01, 0.1, 0.3, 1.0):
        start = now[0] = now[0] + 5
        state.press("dictate")
        now[0] = start + hold
        state.expire()
        state.release("dictate")
        now[0] = start + 5
        state.expire()
    kinds = [kind for kind, _ in ears]
    assert kinds.count("armed") == 4 and kinds.count("caught") + kinds.count("cancelled") == 4


def test_shortcut_aliases_use_same_modifiers():
    assert combo_name("Control+Option+M") == (frozenset({"ctrl", "alt"}), "m")


@pytest.mark.parametrize("vk", [0xFE03, 0xFF7E, 0xFFEA])
def test_x11_layout_altgr_keycodes_map_to_talk(monkeypatch, vk):
    monkeypatch.setattr("milo.desktop.hotkeys.sys.platform", "linux")
    assert key_name(SimpleNamespace(vk=vk, char=None)) == "right_option"


def test_windows_control_character_press_and_plain_release_have_same_identity(monkeypatch):
    monkeypatch.setattr("milo.desktop.hotkeys.sys.platform", "win32")
    assert key_name(SimpleNamespace(vk=0x43, char="\x03")) == "c"
    assert key_name(SimpleNamespace(vk=0x43, char="c")) == "c"
    assert key_name(SimpleNamespace(vk=0x31, char="!")) == "1"
    assert key_name(SimpleNamespace(vk=0x31, char="1")) == "1"


class Keys:
    """A KeyPlatform whose physical state the test sets."""
    polls = True

    def __init__(self):
        self.held: set[str] = set()
        self.others = False
        self.masked: list[str] = []

    def is_down(self, name):
        return name in self.held

    def other_down(self, name):
        return self.others or bool(self.held - {name})

    def listener_options(self):
        return {}

    def mask_menu(self, name):
        self.masked.append(name)


def hotkeys(keys=None):
    events, ears = [], []
    source = GlobalHotkeys(on_command=events.append, keys=keys or Keys())
    source.ear.connect(lambda kind, mode: ears.append((kind, mode)))
    return source, events, ears


def test_hotkey_source_emits_ear_and_masks_a_lone_alt():
    keys = Keys()
    source, events, ears = hotkeys(keys)
    source._on_key("right_option", True)
    assert ears == [("armed", "talk")] and keys.masked == ["right_option"]
    source._ptt.since -= 1  # held a second
    source._on_key("right_option", False)
    assert ears[-1] == ("caught", "talk") and types(events)[-1] == "listen_stop"
    source.stop()


def test_escape_cancels_a_recording_but_never_stops_everything():
    source, events, ears = hotkeys()
    source._on_key("escape", True)
    assert events == [], "Esc in another app must not stop Milo's helpers"
    source._on_key("right_control", True)
    source._on_key("escape", True)
    assert types(events) == ["listen_start", "listen_cancel"] and ears[-1] == ("cancelled", "dictate")
    source.stop()


def test_hold_timer_confirms_through_qt(desktop_application):
    import time
    source, events, ears = hotkeys()
    source._on_key("right_control", True)
    end = time.monotonic() + 1
    while "listen_confirm" not in types(events) and time.monotonic() < end:
        desktop_application.processEvents()
        time.sleep(0.005)
    assert ears[:2] == [("armed", "dictate"), ("open", "dictate")]
    source.stop()


def test_poll_recovers_voice_key_when_hook_silently_stops_and_cleans_stale_keys():
    keys = Keys()
    source, events, _ = hotkeys(keys)
    keys.held = {"right_control"}
    source._pressed = {"c"}  # a release the old hook never delivered
    source._poll_keys()
    assert events == [{"type": "listen_start", "mode": "dictate", "tentative": True}]
    assert source._pressed == {"right_control"}
    source._poll_keys()
    assert len(events) == 1, "hook and polling cannot duplicate a press"
    source._ptt.since -= 1
    keys.held.clear()
    source._poll_keys()
    assert types(events) == ["listen_start", "listen_stop"]
    source.stop()


def test_poll_refuses_a_voice_modifier_in_a_real_shortcut():
    keys = Keys()
    keys.held, keys.others = {"right_control"}, True
    source, events, _ = hotkeys(keys)
    source._poll_keys()
    assert events == []
    source.stop()


def test_listener_failure_cancels_recording_and_reports_fallback():
    source, events, _ = hotkeys()
    statuses = []
    source.status.connect(statuses.append)

    class DeadListener:
        stopped = False

        def is_alive(self):
            return False

        def join(self, timeout):
            raise RuntimeError("test hook failure")

        def stop(self):
            self.stopped = True

    listener = DeadListener()
    source._keyboard = listener
    source._on_key("right_control", True)
    source._check_listeners()
    assert listener.stopped and source._keyboard is None
    assert types(events) == ["listen_start", "listen_cancel"]
    assert len(statuses) == 1 and "test hook failure" in statuses[0]
    assert "Talk and Dictate buttons" in statuses[0]
    assert not source._health_timer.isActive()


def test_windows_filter_drops_milos_own_keys_and_altgr_phantom_control():
    from milo.desktop.platform.windows import MARKER, WindowsKeys
    keep = WindowsKeys.event_filter
    assert not keep(0x100, SimpleNamespace(vkCode=0xA2, scanCode=0x21D, dwExtraInfo=0))
    assert not keep(0x101, SimpleNamespace(vkCode=0xA2, scanCode=0x21D, dwExtraInfo=0))
    assert keep(0x100, SimpleNamespace(vkCode=0xA2, scanCode=0x1D, dwExtraInfo=0))
    assert keep(0x100, SimpleNamespace(vkCode=0xA5, scanCode=0x38, dwExtraInfo=None))
    assert not keep(0x100, SimpleNamespace(vkCode=0x56, scanCode=0x2F, dwExtraInfo=MARKER))


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows key injection")
def test_windows_paste_keys_never_leave_a_modifier_the_user_does_not_hold(monkeypatch):
    from milo.desktop.platform import windows
    sent = []
    keys = windows.WindowsKeys()
    held = set()
    monkeypatch.setattr(keys, "_down", lambda vk: vk in held)
    monkeypatch.setattr(keys, "_send", lambda sequence: sent.append(sequence))
    keys.paste_keys()
    assert sent[-1] == [(0xA2, True), (0x56, True), (0x56, False), (0xA2, False)]
    held = {0xA3}  # the user still holds Right Control (stream = "type")
    keys.paste_keys()
    assert sent[-1] == [(0x56, True), (0x56, False)], "their Control is used, never released under them"
    held = {0xA5, 0xA2}  # AltGr: Right Alt plus its phantom left Control
    keys.paste_keys()
    assert sent[-1] == [(0xE8, True), (0xE8, False), (0xA5, False), (0x56, True), (0x56, False)]
