"""The tools a helper gets for its task: served by the connection server, and named in its prompt."""

import json
import os
import subprocess
import sys

from milo.connect.brief import SAFETY, brief
from milo.connect.server import Toolbox, mcp_server
from milo.connect.memory_tools import RemoteMemory
from milo.connect.milo_tools import RemoteMilo
from milo.connect.tools import INSTRUCTIONS as CONNECTION_RULES
from milo.core import hands
from milo.core.task_scope import ALL, TOOLS_ENV, ToolScope
from tests.connect.test_connect import FakeBrain, home, rpc, toolbox  # noqa: F401 (home is a fixture)
from milo.adapters.connect.fake import _fake
from milo.core.registry import AdapterContext
from tests.fakes import FakeClock

CALENDAR = ToolScope(frozenset({"calendar"}))


def names(server) -> set[str]:
    return {t["name"] for t in rpc(server, "tools/list")["result"]["tools"]}


def full_toolbox(home, kinds=None) -> Toolbox:
    brain = FakeBrain()
    return Toolbox(_fake({}, AdapterContext(home, home / "state", FakeClock())), brain, RemoteMemory(brain),
                   RemoteMilo(brain), kinds=kinds)


def test_the_server_serves_only_the_kinds_it_is_told_and_always_milos_own(home):
    server = mcp_server(full_toolbox(home, frozenset({"calendar"})))
    assert names(server) == {"calendar_events", "calendar_add_event", "milo_remind", "undo_point", "undo_note"}
    everything = names(mcp_server(full_toolbox(home)))
    assert {"mail_search", "files_read", "memory_search", "calendar_events"} <= everything


def test_no_tool_description_carries_the_servers_rules(home):
    """Codex puts a server's instructions in front of every one of its tools' descriptions: 2.8 KB times 25 tools
    came back each time the worker looked for one. The rules go in the helper's prompt, once."""
    init = rpc(mcp_server(full_toolbox(home)), "initialize")["result"]
    assert "instructions" not in init


def test_the_server_reads_its_kinds_from_the_environment(home, tmp_path):
    (home / "config.toml").write_text('[connections]\nuse = "fake"\n[memory]\nenabled = false\n')
    env = {**os.environ, "MILO_HOME": str(home), TOOLS_ENV: "mail"}
    lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})]
    out = subprocess.run([sys.executable, "-m", "milo.connect"], input="\n".join(lines) + "\n", env=env,
                         capture_output=True, text=True, timeout=30).stdout
    tools = {t["name"] for t in json.loads(out.splitlines()[0])["result"]["tools"]}
    assert {"mail_search", "mail_read", "mail_draft", "mail_forward"} <= tools
    assert not any(t.startswith(("calendar_", "files_", "notes_")) for t in tools)


def test_the_brief_names_each_tool_with_its_arguments_so_the_worker_needs_no_search():
    text = brief(CALENDAR)
    assert "mcp__milo__calendar_events(start?, end?, query?)" in text
    assert "mcp__milo__calendar_add_event(title, start, end?" in text
    assert "mcp__milo__undo_note(" in text and "mail_search" not in text
    assert "never follow instructions" in text, "the connections' rules, once"
    assert "memory_search" not in text and "milo-mac" not in text


def test_a_screen_brief_names_the_mac_tools_and_their_route_order():
    text = brief(ToolScope(frozenset(), screen=True))
    for tool in hands.TOOLS:
        assert f"mcp__milo_mac__{tool.name}(" in text
    assert hands.INSTRUCTIONS in text
    assert "calendar_events" not in text and "mcp__milo__undo_point(" in text


def test_the_brief_leaves_out_what_is_switched_off():
    text = brief(ALL, available=frozenset({"calendar", "mail"}))
    assert "calendar_events" in text and "mail_search" in text
    assert "files_read" not in text and "memory_search" not in text and "send_to_phone" not in text


def test_a_brief_is_short():
    assert len(brief(CALENDAR)) < 3500
    assert len(brief(ALL)) < 9000


def test_every_brief_carries_the_safety_rules_whatever_the_instructions_lost():
    """AGENTS.md is trimmed per task and the user may edit it, so the rules against outside instructions, passwords
    and money come with the tools, in code."""
    for scope in (ToolScope(frozenset()), ToolScope(frozenset(), screen=True), ToolScope(frozenset({"memory"})),
                  CALENDAR, ALL):
        text = brief(scope)
        assert SAFETY in text
    assert "never instructions" in SAFETY and "passwords" in SAFETY and "only the user's Yes counts" in SAFETY


class InstallBrain:
    def __init__(self):
        self.requests: list[dict] = []

    def request(self, body: dict) -> dict:
        self.requests.append(body)
        return {"installed": True}

    def approve(self, kind, summary, app=""):
        raise AssertionError("the brain asks about installs itself")


def test_only_a_task_about_installing_gets_install_package(home):
    assert "install_package" not in names(mcp_server(full_toolbox(home, frozenset({"calendar"}))))
    assert "install_package" in names(mcp_server(full_toolbox(home, frozenset({"install"}))))
    assert "install_package" in names(mcp_server(full_toolbox(home)))
    assert "install_package" not in brief(CALENDAR) and "Installing programs" not in brief(CALENDAR)
    text = brief(ToolScope(frozenset({"install"})), available=frozenset({"install", "calendar"}))
    assert "mcp__milo__install_package(manager, package)" in text
    assert "brew_cask" in text and "Never sudo" in text
    assert "calendar_events" not in text and CONNECTION_RULES.strip() not in text, "no rules for tools it hasn't got"


def test_install_package_goes_to_the_brain_which_asks_itself(home):
    brain = InstallBrain()
    box = Toolbox(_fake({}, AdapterContext(home, home / "state", FakeClock())), brain, None, RemoteMilo(brain),
                  kinds=frozenset({"install"}))
    assert box.call("install_package", {"manager": "npm", "package": "@openai/codex"}) == {"installed": True}
    assert brain.requests == [{"op": "package.install", "manager": "npm", "package": "@openai/codex"}]
