"""X11 discovery works without EWMH, as on WSLg and a bare X server."""
import sys
from types import SimpleNamespace

from milo.desktop._native_linux import LinuxAccessibility
from milo.desktop._native_types import Focus


class Window:
    def __init__(self, identifier, *, title="", pid=None, parent=None, children=()):
        self.id, self.title, self.pid, self.parent, self.children = identifier, title, pid, parent, children
        self.actions = []

    def get_full_property(self, atom, kind):
        if atom == "_NET_WM_NAME" and self.title:
            return SimpleNamespace(value=self.title.encode())
        if atom == "_NET_WM_PID" and self.pid:
            return SimpleNamespace(value=[self.pid])
        return None

    def get_wm_name(self):
        return self.title

    def get_wm_class(self):
        return ("fixture", "Fixture")

    def query_tree(self):
        return SimpleNamespace(parent=self.parent, children=self.children)

    def map(self):
        self.actions.append("map")

    def configure(self, **values):
        self.actions.append(("configure", values))

    def set_input_focus(self, *values):
        self.actions.append(("focus", values))

    def send_event(self, event, **values):
        self.actions.append(("event", event))


def backend():
    value = LinuxAccessibility.__new__(LinuxAccessibility)
    root = Window(1)
    window = Window(2, title="Milo disposable native integration test", pid=42, parent=root)
    field = Window(3, parent=window)
    root.children = [window]
    value.display = SimpleNamespace(screen=lambda: SimpleNamespace(root=root),
                                    intern_atom=lambda atom: atom,
                                    get_input_focus=lambda: SimpleNamespace(focus=field),
                                    sync=lambda: None)
    value.windows = lambda: [Focus("owned", 42, "Fixture", title=window.title)]
    return value, window


def test_foreground_pid_walks_input_focus_ancestors_without_active_window_property():
    value, _ = backend()
    assert value._front_pid() == 42


def test_stale_atspi_focus_does_not_count_when_x11_has_no_keyboard_target():
    value, _ = backend()
    target = Focus("owned", 42, "Fixture", editable=True)
    assert value.keyboard_focus_matches(target)
    value.display.get_input_focus = lambda: SimpleNamespace(focus=value.display.screen().root)
    assert not value.keyboard_focus_matches(target)


def test_activation_discovers_and_focuses_a_window_without_an_ewmh_window_manager(monkeypatch):
    value, window = backend()
    fake_xlib = SimpleNamespace(X=SimpleNamespace(Above=0, RevertToParent=2, CurrentTime=0,
                                                  SubstructureRedirectMask=1, SubstructureNotifyMask=2),
                                protocol=SimpleNamespace(event=SimpleNamespace(ClientMessage=lambda **values: values)))
    monkeypatch.setitem(sys.modules, "Xlib", fake_xlib)
    result = value.activate("Milo disposable native integration test")
    assert result.pid == 42
    assert window.actions == ["map", ("configure", {"stack_mode": 0}), ("focus", (2, 0))]


def test_x11_window_discovery_supports_utf8_titles(monkeypatch):
    value, window = backend()
    window.title = "Milo — Grüß dich 🐦"
    fake_xlib = SimpleNamespace(X=SimpleNamespace(Above=0, RevertToParent=2, CurrentTime=0,
                                                  SubstructureRedirectMask=1, SubstructureNotifyMask=2),
                                protocol=SimpleNamespace(event=SimpleNamespace(ClientMessage=lambda **values: values)))
    monkeypatch.setitem(sys.modules, "Xlib", fake_xlib)
    assert value.activate("Grüß dich").pid == 42
