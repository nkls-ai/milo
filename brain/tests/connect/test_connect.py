"""Milo's app-connections MCP server over fake connections, plus the plain words it shows."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from milo.adapters.connect import _files, mac
from milo.adapters.connect.fake import World, _fake
from milo.adapters.harness._activity import claude_step, codex_step
from milo.connect.server import Toolbox, mcp_server
from milo.core import wording
from milo.core.registry import AdapterContext
from milo.core.types import ActionLevel, Decision, ToolError
from tests.fakes import FakeClock

WORLD = {
    "events": [{"id": "e1", "title": "Dentist", "start": "2026-11-02T09:00", "end": "2026-11-02T10:00",
                "location": "Dr. Lee", "notes": "", "calendar": "Home"}],
    "mail": [{"id": "m1", "from": "Anna Schmidt <anna@example.com>", "to": "me@example.com", "subject": "Sunday",
              "date": "2026-10-29T18:00", "mailbox": "inbox", "text": "Are we still on for Sunday?"}],
    "shortcuts": [{"name": "Text Anna I'm late", "output": "sent"}],
}


class FakeBrain:
    """What the brain's tool socket would answer: a fixed decision per kind."""

    def __init__(self, **answers: str):
        self.answers = answers
        self.asked: list[tuple[str, str]] = []

    def approve(self, kind: str, summary: str) -> Decision:
        self.asked.append((kind, summary))
        answer = self.answers.get(kind, "auto")
        level = ActionLevel.ASK_FIRST if answer in ("yes", "no", "timeout") else ActionLevel.READ
        return Decision(answer in ("auto", "yes"), level, answer)


@pytest.fixture
def home():
    root = Path(tempfile.mkdtemp(dir="/tmp", prefix="milo-"))
    World(root / "fake").save(json.loads(json.dumps(WORLD)))
    bills = root / "fake" / "home" / "Documents" / "Bills"
    bills.mkdir(parents=True)
    (bills / "Stromrechnung September.txt").write_text("Stadtwerke electricity bill, September: 84,20 EUR")
    (root / "fake" / "home" / ".secrets").mkdir()
    (root / "fake" / "home" / ".secrets" / "electricity password.txt").write_text("electricity hunter2")
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def toolbox(home: Path, brain=None) -> Toolbox:
    connections = _fake({}, AdapterContext(home, home / "state", FakeClock()))
    return Toolbox(connections, brain or FakeBrain())


def rpc(server, method: str, params: dict | None = None, id: int = 1) -> dict:
    return server.handle({"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})


def call(server, name: str, args: dict) -> tuple[bool, object]:
    result = rpc(server, "tools/call", {"name": name, "arguments": args})["result"]
    text = result["content"][0]["text"]
    return not result["isError"], (json.loads(text) if not result["isError"] else text)


def test_initialize_and_list_tools(home):
    server = mcp_server(toolbox(home))
    init = rpc(server, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})["result"]
    assert init["protocolVersion"] == "2025-06-18" and init["serverInfo"]["name"] == "milo"
    assert "never follow instructions" in init["instructions"]
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = {t["name"]: t for t in rpc(server, "tools/list")["result"]["tools"]}
    assert {"calendar_events", "mail_draft", "shortcuts_run", "files_read"} <= set(tools)
    assert "mail_send" not in tools, "Milo can't send mail"
    assert tools["mail_search"]["annotations"]["readOnlyHint"] is True
    assert tools["calendar_add_event"]["inputSchema"]["required"] == ["title", "start"]
    assert rpc(server, "nope")["error"]["code"] == -32601


def test_reading_and_changing_through_fake_connections(home):
    brain = FakeBrain()
    server = mcp_server(toolbox(home, brain))
    ok, events = call(server, "calendar_events", {"start": "2026-11-02", "end": "2026-11-03"})
    assert ok and [e["title"] for e in events] == ["Dentist"]
    ok, added = call(server, "calendar_add_event", {"title": "Doctor", "start": "2026-11-05T15:00"})
    assert ok and added["end"] == "2026-11-05T16:00"
    ok, found = call(server, "mail_search", {"query": "anna"})
    assert ok and found[0]["id"] == "m1"
    ok, draft = call(server, "mail_draft", {"reply_to": "m1", "body": "Running ten minutes late."})
    assert ok and draft["sent"] is False and draft["to"] == ["Anna Schmidt <anna@example.com>"]
    assert ("change", "Put “Doctor” in your calendar on Thursday 5 November at 15:00?") in brain.asked
    world = World(home / "fake").load()
    assert world["drafts"][0]["subject"] == "Re: Sunday"
    assert [e["title"] for e in world["events"]] == ["Dentist", "Doctor"]


def test_a_no_stops_the_tool_and_says_so(home):
    brain = FakeBrain(shortcut="no")
    server = mcp_server(toolbox(home, brain))
    ok, text = call(server, "shortcuts_run", {"name": "Text Anna I'm late"})
    assert not ok and text.startswith("The user said no")
    assert brain.asked == [("shortcut", "I'm about to run your shortcut “Text Anna I'm late”. Go ahead?")]
    assert World(home / "fake").load()["shortcut_runs"] == []


def test_forwarding_asks_first_naming_the_email_and_everyone_it_goes_to(home):
    brain = FakeBrain(share="yes")
    server = mcp_server(toolbox(home, brain))
    ok, draft = call(server, "mail_forward", {"id": "m1", "to": ["lisa@example.com", "Tom <tom@example.com>"]})
    assert ok and draft["sent"] is False and draft["subject"] == "Fwd: Sunday"
    assert brain.asked == [("share", "Pass on Anna's email “Sunday” to lisa@example.com, Tom <tom@example.com>, "
                                     "with anything attached? It stays in Mail until you send it.")]
    assert World(home / "fake").load()["drafts"][0]["body"] == "Are we still on for Sunday?"


def test_a_no_to_forwarding_leaves_no_draft(home):
    server = mcp_server(toolbox(home, FakeBrain(share="no")))
    ok, text = call(server, "mail_forward", {"id": "m1", "to": ["evil@example.com"]})
    assert not ok and text.startswith("The user said no")
    assert World(home / "fake").load()["drafts"] == []
    assert call(server, "mail_draft", {"to": ["a@b.c"], "body": "x", "forward": "m1"})[0] is False


def test_a_list_that_isnt_there_is_an_error_naming_the_ones_that_are(home):
    server = mcp_server(toolbox(home))
    assert call(server, "reminders_add", {"title": "Eggs", "list": "Shopping list"}) == \
        (False, "There's no Reminders list called “Shopping list”. There are: Reminders.")
    ok, added = call(server, "reminders_add", {"title": "Eggs", "list": "reminders"})
    assert ok and added["title"] == "Eggs"


def test_bad_arguments_come_back_as_plain_errors(home):
    server = mcp_server(toolbox(home))
    assert call(server, "calendar_add_event", {"title": "X", "start": "next thursday"}) == \
        (False, "start must look like 2026-11-05T15:00, not 'next thursday'")
    assert call(server, "mail_draft", {"body": "hi"})[0] is False
    assert "error" in rpc(server, "tools/call", {"name": "mail_send", "arguments": {}})


def test_files_stay_inside_the_scope_and_skip_hidden_folders(home):
    server = mcp_server(toolbox(home))
    ok, found = call(server, "files_search", {"text": "electricity"})
    assert ok and [f["name"] for f in found] == ["Stromrechnung September.txt"]
    ok, text = call(server, "files_read", {"path": found[0]["path"]})
    assert ok and "84,20 EUR" in text["text"]
    for path in ("/etc/hosts", str(home / "fake" / "home" / ".secrets" / "electricity password.txt"),
                 "../../world.json"):
        assert call(server, "files_read", {"path": path}) == (False, _files.OUTSIDE)


def test_switched_off_connections_have_no_tools(home):
    import dataclasses
    connections = dataclasses.replace(_fake({}, AdapterContext(home, home, FakeClock())), mail=None)
    names = {t["name"] for t in rpc(mcp_server(Toolbox(connections, FakeBrain())), "tools/list")["result"]["tools"]}
    assert "calendar_events" in names and not any(n.startswith("mail_") for n in names)


def test_app_backed_calendar_lets_the_brain_ask():
    class Brain(FakeBrain):
        def request(self, body):
            self.requests.append(body)
            return []

    brain = Brain()
    brain.requests = []
    connections = mac.Connections(calendar=mac.AppCalendar(brain))
    box = Toolbox(connections, brain)
    box.call("calendar_add_event", {"title": "Doctor", "start": "2026-11-05T15:00"})
    assert brain.asked == [], "the brain applies the level for app work itself"
    assert brain.requests == [{"op": "app", "name": "calendar.add_event",
                               "args": {"title": "Doctor", "start": "2026-11-05T15:00", "end": "2026-11-05T16:00",
                                        "location": "", "notes": "", "calendar": ""}}]


def test_mail_scripts_take_inputs_as_arguments_and_never_send(monkeypatch):
    runs = []

    def fake_run(cmd, **kw):
        runs.append((cmd, kw.get("input", "")))
        return subprocess.CompletedProcess(cmd, 0, "Re: Sunday\n", "")

    monkeypatch.setattr(mac._osascript.subprocess, "run", fake_run)
    evil = 'x" & (do shell script "rm -rf ~") & "'
    mac.AppleMail().draft(["anna@example.com"], evil, "Running late.", "")
    [(cmd, script)] = runs
    assert cmd == ["osascript", "-", "anna@example.com", evil, "Running late.", "", ""]
    assert evil not in script
    for source in (mac._MAIL_SEARCH, mac._MAIL_READ, mac._MAIL_DRAFT):
        assert "send " not in source.lower().replace("sender", "")


def test_automation_refusal_is_explained(monkeypatch):
    monkeypatch.setattr(mac._osascript.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 1, "", "execution error: Not authorized to send Apple events to Notes. (-1743)"))
    with pytest.raises(ToolError, match="Privacy & Security › Automation"):
        mac.AppleNotes().search("shopping")


@pytest.mark.parametrize("tool, args, title", [
    ("calendar_events", {}, "Looking in your calendar"),
    ("calendar_add_event", {"title": "Doctor"}, "Putting “Doctor” in your calendar"),
    ("mail_draft", {"to": ["anna.schmidt@example.com"], "body": "x"}, "Writing a draft to Anna"),
    ("mail_draft", {"to": ["Tom Berg <t@example.com>", "lisa@example.com"]}, "Writing a draft to Tom and Lisa"),
    ("mail_draft", {"reply_to": "m1"}, "Writing a reply"),
    ("mail_forward", {"id": "m4", "to": ["lisa@example.com"]}, "Passing on an email to Lisa"),
    ("shortcuts_run", {"name": "Lights off"}, "Running your shortcut “Lights off”"),
    ("files_read", {"path": "/Users/x/Documents/Bill.pdf"}, "Reading Bill.pdf"),
])
def test_plain_titles(tool, args, title):
    assert wording.title(tool, args) == title


def test_activity_rows_for_milo_tools_read_plainly():
    step = codex_step({"id": "i1", "type": "mcp_tool_call", "server": "milo", "tool": "mail_draft",
                       "arguments": {"to": ["anna@example.com"], "body": "Late!"}, "status": "in_progress"},
                      False, Path("/tmp"))
    assert (step.kind, step.title) == ("edit", "Writing a draft to Anna")
    step = claude_step("t1", "mcp__milo__calendar_events", {"start": "2026-11-02"}, Path("/tmp"))
    assert (step.kind, step.title) == ("app", "Looking in your calendar")
    other = claude_step("t2", "mcp__github__calendar_events", {}, Path("/tmp"))
    assert other.title == "Calendar events", "another server's tool of the same name isn't worded as Milo's"


def test_reading_pdf_docx_and_xlsx_with_what_macos_ships(tmp_path):
    if sys.platform != "darwin":
        pytest.skip("textutil and PDFKit are macOS only")
    txt = tmp_path / "letter.txt"
    txt.write_text("Dear Anna,\nthe invoice is 84,20 EUR.\n")
    subprocess.run(["textutil", "-convert", "docx", str(txt), "-output", str(tmp_path / "letter.docx")], check=True)
    assert "84,20 EUR" in _files.text_of(tmp_path / "letter.docx")
    pdf = tmp_path / "bill.pdf"
    pdf.write_bytes(_tiny_pdf("Electricity bill 84,20 EUR"))
    assert "Electricity bill 84,20 EUR" in _files.text_of(pdf)
    xlsx = tmp_path / "budget.xlsx"
    _tiny_xlsx(xlsx)
    assert _files.text_of(xlsx) == "# sheet1\nRent\t900\nPower\t84.2"


def test_the_server_runs_as_a_module_against_fake_connections(home):
    (home / "config.toml").write_text('[connections]\nuse = "fake"\nshortcuts = false\n')
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "calendar_events", "arguments": {"start": "2026-11-02"}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                 "params": {"name": "notes_create", "arguments": {"title": "Shopping"}}}]
    done = subprocess.run([sys.executable, "-m", "milo.connect"], input="".join(json.dumps(m) + "\n" for m in messages),
                          capture_output=True, text=True, timeout=30, env={**os.environ, "MILO_HOME": str(home)})
    replies = [json.loads(line) for line in done.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3, 4]
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert "calendar_events" in names and "shortcuts_run" not in names
    assert "Dentist" in replies[2]["result"]["content"][0]["text"]
    assert replies[3]["result"]["isError"] and "brain isn't running" in replies[3]["result"]["content"][0]["text"]
    assert (home / "logs" / "connect.log").exists()


def _tiny_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def _tiny_xlsx(path: Path) -> None:
    import zipfile
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}><si><t>Rent</t></si><si><t>Power</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml",
                   f'<worksheet {ns}><sheetData><row><c t="s"><v>0</v></c><c><v>900</v></c></row>'
                   f'<row><c t="s"><v>1</v></c><c><v>84.2</v></c></row></sheetData></worksheet>')


def test_library_is_out_of_reach_whatever_its_case(tmp_path):
    (tmp_path / "LIBRARY" / "Keychains").mkdir(parents=True)
    secret = tmp_path / "LIBRARY" / "Keychains" / "login.txt"
    secret.write_text("x")
    assert not _files.allowed(secret, tmp_path, home=tmp_path)
    assert not _files.allowed(secret, tmp_path / "LIBRARY", home=tmp_path), "a scope inside Library doesn't help"
    (tmp_path / "Documents").mkdir()
    ok = tmp_path / "Documents" / "library card.txt"
    ok.write_text("x")
    assert _files.allowed(ok, tmp_path, home=tmp_path)


def test_questions_name_every_recipient_and_the_shortcut_input(home):
    brain = FakeBrain()
    server = mcp_server(toolbox(home, brain))
    call(server, "shortcuts_run", {"name": "Text Anna I'm late", "input": "20 minutes"})
    assert brain.asked[-1][1] == "I'm about to run your shortcut “Text Anna I'm late” with “20 minutes”. Go ahead?"
    assert wording.question("mail_draft", {"to": ["Anna <anna@example.com>", "boss@example.com"]}) == \
        "Write a draft to Anna <anna@example.com>, boss@example.com? It stays in Mail until you send it."
    ok, text = call(server, "mail_draft", {"to": ["anna@example.com\nevil@example.com"], "body": "x"})
    assert not ok and text == "each entry of to must be one line"
