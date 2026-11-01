"""The home adapters (ADR 0037): Home Assistant over a stub instead of HTTP, Apple Home and the Focus over a fake
`shortcuts` command. Nothing here reaches a real home, runs a shortcut or opens a file."""

import json
import plistlib
from pathlib import Path

import pytest

from milo.adapters.home.apple_home import AppleHome
from milo.adapters.home.focus import OWN, ShortcutsFocus, workflow
from milo.adapters.home.home_assistant import HomeAssistant
from milo.core.home import NotSetUp
from milo.core.registry import HOMES, AdapterContext
from milo.core.types import ToolError
from tests.fakes import FakeClock

STATES = [
    {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen light", "brightness": 128}},
    {"entity_id": "cover.garage", "state": "closed", "attributes": {"friendly_name": "Garage", "device_class": "garage"}},
    {"entity_id": "cover.blinds", "state": "open", "attributes": {"friendly_name": "Blinds", "current_position": 70}},
    {"entity_id": "lock.front", "state": "locked", "attributes": {"friendly_name": "Front door"}},
    {"entity_id": "alarm_control_panel.home", "state": "disarmed", "attributes": {"friendly_name": "Alarm"}},
    {"entity_id": "climate.living", "state": "heat", "attributes": {"friendly_name": "Heating", "temperature": 20}},
    {"entity_id": "scene.movie", "state": "scening", "attributes": {"friendly_name": "Movie night",
                                                                    "entity_id": ["light.kitchen"]}},
    {"entity_id": "sensor.temp", "state": "21", "attributes": {"friendly_name": "Temperature"}},
]


class StubHA:
    """What Home Assistant answers, and every request Milo made."""

    def __init__(self, status: int = 200):
        self.status = status
        self.requests: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, bytes]:
        assert headers["Authorization"] == "Bearer secret-token"
        path = url.removeprefix("http://ha.local:8123")
        self.requests.append((method, path, json.loads(body) if body else None))
        if self.status != 200:
            return self.status, b"nope"
        if path == "/api/states":
            return 200, json.dumps(STATES).encode()
        if path == "/api/template":
            return 200, json.dumps([["light.kitchen", "Kitchen"]]).encode()
        if path.startswith("/api/states/"):
            return 200, json.dumps({**STATES[0], "state": "off"}).encode()
        return 200, b"[]"


def ha(tmp_path: Path, send: StubHA) -> HomeAssistant:
    secrets = tmp_path / "secrets"
    secrets.mkdir(mode=0o700)
    (secrets / "ha.token").write_text("secret-token\n", encoding="utf-8")
    (secrets / "ha.token").chmod(0o600)
    return HomeAssistant("http://ha.local:8123/", secrets / "ha.token", send=send)


def test_home_assistant_devices_get_kinds_rooms_levels_and_scene_members(tmp_path):
    devices = {d.id: d for d in ha(tmp_path, StubHA()).devices()}
    assert "sensor.temp" not in devices, "only what Milo can switch"
    assert (devices["light.kitchen"].kind, devices["light.kitchen"].room, devices["light.kitchen"].level) == \
        ("light", "Kitchen", 50)
    assert devices["cover.garage"].kind == "garage" and devices["cover.blinds"].kind == "cover"
    assert devices["lock.front"].kind == "lock" and devices["alarm_control_panel.home"].kind == "alarm"
    assert devices["climate.living"].level == 20 and devices["scene.movie"].members == ("light.kitchen",)
    assert devices["scene.movie"].known and devices["light.kitchen"].known


def test_home_assistant_acts_through_its_services(tmp_path):
    stub = StubHA()
    home = ha(tmp_path, stub)
    after = home.act("light.kitchen", "set", "40")
    home.act("cover.garage", "open")
    home.act("climate.living", "set", "21.5")
    home.act("alarm_control_panel.home", "arm", "night")
    home.act("scene.movie", "run")
    posts = [(path, body) for method, path, body in stub.requests if method == "POST"]
    assert posts == [
        ("/api/services/light/turn_on", {"entity_id": "light.kitchen", "brightness_pct": 40}),
        ("/api/services/cover/open_cover", {"entity_id": "cover.garage"}),
        ("/api/services/climate/set_temperature", {"entity_id": "climate.living", "temperature": 21.5}),
        ("/api/services/alarm_control_panel/alarm_arm_night", {"entity_id": "alarm_control_panel.home"}),
        ("/api/services/scene/turn_on", {"entity_id": "scene.movie"})]
    assert after.state == "off", "the state after it, read back"


def test_home_assistant_says_what_is_wrong_in_plain_words(tmp_path):
    with pytest.raises(ToolError, match="didn't take Milo's token"):
        ha(tmp_path, StubHA(401)).devices()
    missing = HomeAssistant("http://ha.local:8123", tmp_path / "none.token", send=StubHA())
    with pytest.raises(ToolError, match="long-lived token"):
        missing.devices()
    with pytest.raises(ToolError, match="no address"):
        HomeAssistant("", tmp_path / "none.token", send=StubHA()).devices()


class FakeShortcuts:
    """The `shortcuts` command over a list of names, with or without a "Milo Home" folder."""

    def __init__(self, names: list[str], *, folder: list[str] | None = None):
        self.names, self.folder = names, folder
        self.ran: list[list[str]] = []

    def __call__(self, cmd: list[str], timeout_s: float) -> str:
        assert cmd[0] == "shortcuts"
        if cmd[1:] == ["list", "--folders"]:
            return "Milo Home\n" if self.folder is not None else ""
        if cmd[1:3] == ["list", "--folder-name"]:
            return "\n".join(self.folder or [])
        if cmd[1:] == ["list"]:
            return "\n".join(self.names + (self.folder or []))
        if cmd[1] == "run":
            self.ran.append(cmd[2:])
            if cmd[2] not in self.names + (self.folder or []):
                raise ToolError("no such shortcut")
            return ""
        if cmd[1] == "sign":
            Path(cmd[cmd.index("--output") + 1]).write_bytes(b"AEA1signed")
            return ""
        raise AssertionError(cmd)


def test_apple_home_reads_devices_and_scenes_from_the_folders_shortcut_names():
    runner = FakeShortcuts([], folder=["Living room lights on", "Living room lights off", "Movie night",
                                       "Haustür abschließen", "Haustür aufschließen", "Garage open", "Heizung set"])
    home = AppleHome(run=runner)
    devices = {d.name: d for d in home.devices()}
    assert (devices["Living room lights"].kind, set(devices["Living room lights"].does)) == ("light", {"on", "off"})
    assert devices["Movie night"].kind == "scene" and devices["Movie night"].does == ("run",)
    assert devices["Haustür"].kind == "lock" and devices["Garage"].kind == "garage"
    home.act(devices["Living room lights"].id, "off")
    home.act(devices["Movie night"].id, "run")
    home.act(devices["Heizung"].id, "set", "21")
    assert [r[0] for r in runner.ran] == ["Living room lights off", "Movie night", "Heizung set"]
    assert runner.ran[2][1] == "--input-path", "the level goes in as the shortcut's input"
    with pytest.raises(ToolError):
        home.act(devices["Movie night"].id, "off")


def test_without_the_folder_only_shortcuts_about_the_home_count():
    home = AppleHome(run=FakeShortcuts(["Kitchen light on", "Kitchen light off", "Send invoice", "Make GIF",
                                        "Good night scene"]))
    assert sorted(d.name for d in home.devices()) == ["Good night scene", "Kitchen light"]
    assert not any(d.known for d in home.devices()), "outside the folder they only sound like home ones: they ask"


def test_focus_runs_milos_own_shortcut_or_the_users_for_another_focus():
    runner = FakeShortcuts([OWN[True], OWN[False], "Work Focus on", "Fokus Arbeit aus", "Sleep on"])
    focus = ShortcutsFocus(Path("/nonexistent"), run=runner)
    focus.set(True)
    focus.set(False, "Do Not Disturb")
    focus.set(True, "Work")
    focus.set(False, "Arbeit")
    assert [r[0] for r in runner.ran] == [OWN[True], OWN[False], "Work Focus on", "Fokus Arbeit aus"]
    with pytest.raises(NotSetUp):
        focus.set(True, "Sleep")  # "Sleep on" doesn't say Focus: it could do anything


def test_focus_makes_signs_and_opens_its_two_shortcuts_once(tmp_path):
    runner, opened = FakeShortcuts([]), []
    focus = ShortcutsFocus(tmp_path / "shortcuts", run=runner, opener=lambda cmd, t: opened.append(cmd) or "")
    with pytest.raises(NotSetUp):
        focus.set(True)
    assert focus.offer() is True
    assert sorted(Path(cmd[1]).name for cmd in opened) == sorted(f"{n}.shortcut" for n in OWN.values())
    assert sorted(p.name for p in (tmp_path / "shortcuts").iterdir()) == sorted(f"{n}.shortcut" for n in OWN.values())
    assert focus.offer() and sum(1 for c in runner.ran) == 0, "signed once, kept"
    assert focus.offer("Work") is False, "another Focus's id isn't Milo's to know"


def test_the_focus_shortcut_is_one_set_focus_action():
    on, off = workflow(True), workflow(False)
    assert plistlib.loads(plistlib.dumps(on))["WFWorkflowActions"][0]["WFWorkflowActionIdentifier"] == \
        "is.workflow.actions.dnd.set"
    assert on["WFWorkflowActions"][0]["WFWorkflowActionParameters"]["Enabled"] == 1
    assert off["WFWorkflowActions"][0]["WFWorkflowActionParameters"]["Enabled"] == 0


def test_auto_picks_home_assistant_when_it_has_a_url_else_apple_home_where_shortcuts_exist(tmp_path, monkeypatch):
    import milo.adapters as adapters
    adapters.load_builtin()
    ctx = AdapterContext(tmp_path, tmp_path / "state", FakeClock())
    picked = HOMES.create("auto", {"home_assistant": {"url": "http://ha.local:8123"}}, ctx)
    assert isinstance(picked, HomeAssistant) and picked._key_file == tmp_path / "secrets" / "home_assistant.token"
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/shortcuts" if name == "shortcuts" else None)
    assert isinstance(HOMES.create("auto", {"apple_home": {"folder": "Zuhause"}}, ctx), AppleHome)
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert HOMES.create("auto", {}, ctx) is None
    assert HOMES.create("none", {}, ctx) is None


def test_a_door_or_gate_cover_is_a_garage_and_asks_first():
    """Security review, 2026-11-01: a cover with device_class door opened like a blind, without a question."""
    from milo.adapters.home.home_assistant import _device
    for cls in ("door", "gate", "garage"):
        d = _device({"entity_id": "cover.x", "state": "closed", "attributes": {"device_class": cls}}, {})
        assert d is not None and d.kind == "garage", cls
    blinds = _device({"entity_id": "cover.y", "state": "open", "attributes": {"device_class": "blind"}}, {})
    assert blinds is not None and blinds.kind == "cover"
