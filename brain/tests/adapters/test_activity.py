"""Activity rows from the worker CLIs' streamed events, in plain words."""

import asyncio
import json
from pathlib import Path

import pytest

from milo.adapters.harness._activity import ClaudeActivity, CodexActivity, describe_command
from milo.adapters.harness.claude import result_line
from milo.core.registry import HARNESSES
from milo.core.types import Step, StepStatus
from tests.adapters.test_harness import CLAUDE_RESULT, fake_cli

WORKDIR = Path("/Users/you/Milo")

# Recorded from `codex exec --json` (codex-cli 0.164) asked to run `ls` and edit a.txt; output trimmed.
CODEX_RUN = """\
{"type":"thread.started","thread_id":"01a18a2c-2aca-7740-80e7-9e836af102e8"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"I’ll list the directory and update a.txt.\\n"}}
{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"/bin/zsh -lc ls","aggregated_output":"","exit_code":null,"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"/bin/zsh -lc ls","aggregated_output":"a.txt\\n","exit_code":0,"status":"completed"}}
{"type":"item.started","item":{"id":"item_2","type":"command_execution","command":"/bin/zsh -lc \\"printf 'hi' > a.txt\\"","aggregated_output":"","exit_code":null,"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_2","type":"command_execution","command":"/bin/zsh -lc \\"printf 'hi' > a.txt\\"","aggregated_output":"","exit_code":0,"status":"completed"}}
{"type":"item.completed","item":{"id":"item_3","type":"agent_message","text":"{\\"emotion\\":\\"happy\\",\\"say\\":\\"Done\\"}"}}
{"type":"turn.completed","usage":{"input_tokens":38071,"cached_input_tokens":32128,"output_tokens":72}}
"""

# Item shapes codex documents for exec --json that the recording above didn't hit.
CODEX_OTHER_ITEMS = """\
{"type":"item.started","item":{"id":"item_4","type":"command_execution","command":"/bin/zsh -lc 'cat missing.txt'","aggregated_output":"","exit_code":null,"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_4","type":"command_execution","command":"/bin/zsh -lc 'cat missing.txt'","aggregated_output":"cat: missing.txt: No such file or directory\\n","exit_code":1,"status":"failed"}}
{"type":"item.completed","item":{"id":"item_5","type":"file_change","changes":[{"path":"/Users/you/Milo/memory/notes.md","kind":"update"}],"status":"completed"}}
{"type":"item.completed","item":{"id":"item_6","type":"file_change","changes":[{"path":"a.md","kind":"add"},{"path":"b.md","kind":"delete"}],"status":"failed"}}
{"type":"item.started","item":{"id":"item_7","type":"mcp_tool_call","server":"mac-helper","tool":"run_applescript","arguments":{"script":"tell application \\"Numbers\\" to activate"},"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_7","type":"mcp_tool_call","server":"mac-helper","tool":"run_applescript","arguments":{"script":"tell application \\"Numbers\\" to activate"},"result":{"content":[]},"error":null,"status":"completed"}}
{"type":"item.started","item":{"id":"item_8","type":"web_search","query":"hetzner invoice pdf"}}
{"type":"item.completed","item":{"id":"item_8","type":"web_search","query":"hetzner invoice pdf"}}
{"type":"item.completed","item":{"id":"item_9","type":"reasoning","text":"**Looking for the file**"}}
{"type":"item.started","item":{"id":"item_10","type":"todo_list","items":[{"text":"find it","completed":false}]}}
"""

# Recorded from `claude -p --output-format stream-json --verbose` (Claude Code 2.1) running ls, a failing
# cat and a Read; tool output trimmed, system and rate-limit lines dropped.
CLAUDE_RUN = """\
{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_01J2fEiGUwuiesaPkPKXFecA", "name": "Bash", "input": {"command": "ls", "description": "List files in current directory"}}]}, "session_id": "s1"}
{"type": "user", "message": {"role": "user", "content": [{"tool_use_id": "toolu_01J2fEiGUwuiesaPkPKXFecA", "type": "tool_result", "content": "a.txt\\nclaude.err", "is_error": false}]}, "session_id": "s1"}
{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_01JkFKdt6NKmx149GS1o3YDq", "name": "Bash", "input": {"command": "cat nonexistent.txt", "description": "Attempt to print nonexistent file"}}]}, "session_id": "s1"}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "Exit code 1\\ncat: nonexistent.txt: No such file or directory", "is_error": true, "tool_use_id": "toolu_01JkFKdt6NKmx149GS1o3YDq"}]}, "session_id": "s1"}
{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_01BoB5pLnKJRz46Jj7E7vdQJ", "name": "Read", "input": {"file_path": "/private/tmp/milo-probe/a.txt"}}]}, "session_id": "s1"}
{"type": "user", "message": {"role": "user", "content": [{"tool_use_id": "toolu_01BoB5pLnKJRz46Jj7E7vdQJ", "type": "tool_result", "content": "1\\thi"}]}, "session_id": "s1"}
{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}, "session_id": "s1"}
"""

R, D, F = StepStatus.RUNNING, StepStatus.DONE, StepStatus.FAILED


def feed(parser_cls, text: str) -> list[Step]:
    steps: list[Step] = []
    parser = parser_cls(steps.append, WORKDIR)
    for line in text.splitlines():
        parser.line(line + "\n")
    return steps


def rows(steps: list[Step]) -> list[tuple]:
    return [(s.id, s.kind, s.title, s.status) for s in steps]


def test_codex_recorded_run():
    steps = feed(CodexActivity, CODEX_RUN)
    assert rows(steps) == [
        ("item_1", "read", "Looking in Milo's folder", R),
        ("item_1", "read", "Looking in Milo's folder", D),
        ("item_2", "edit", "Writing a.txt", R),
        ("item_2", "edit", "Writing a.txt", D),
    ]
    assert steps[0].detail == "ls"
    assert steps[2].detail == "printf 'hi' > a.txt"


def test_codex_failures_file_changes_tools_and_searches():
    steps = feed(CodexActivity, CODEX_OTHER_ITEMS)
    assert rows(steps) == [
        ("item_4", "read", "Reading missing.txt", R),
        ("item_4", "read", "Reading missing.txt", F),
        ("item_5", "edit", "Editing notes.md", D),
        ("item_6", "edit", "Changing 2 files", F),
        ("item_7", "tool", "Controlling an app", R),
        ("item_7", "tool", "Controlling an app", D),
        ("item_8", "web", "Searching the web for “hetzner invoice pdf”", R),
        ("item_8", "web", "Searching the web for “hetzner invoice pdf”", D),
    ]
    assert steps[1].detail.endswith("No such file or directory")
    assert steps[3].detail == "add a.md\ndelete b.md"
    assert steps[4].detail.startswith('mac-helper.run_applescript {"script"')


def test_claude_recorded_run():
    steps = feed(ClaudeActivity, CLAUDE_RUN)
    assert rows(steps) == [
        ("toolu_01J2fEiGUwuiesaPkPKXFecA", "read", "Looking in Milo's folder", R),
        ("toolu_01J2fEiGUwuiesaPkPKXFecA", "read", "Looking in Milo's folder", D),
        ("toolu_01JkFKdt6NKmx149GS1o3YDq", "read", "Reading nonexistent.txt", R),
        ("toolu_01JkFKdt6NKmx149GS1o3YDq", "read", "Reading nonexistent.txt", F),
        ("toolu_01BoB5pLnKJRz46Jj7E7vdQJ", "read", "Reading a.txt", R),
        ("toolu_01BoB5pLnKJRz46Jj7E7vdQJ", "read", "Reading a.txt", D),
    ]
    assert steps[3].detail.startswith("cat nonexistent.txt\n\n") and "No such file" in steps[3].detail


def claude_line(name: str, args: dict) -> str:
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": name, "input": args}]}})


@pytest.mark.parametrize("name, args, kind, title", [
    ("Edit", {"file_path": "/x/notes.md"}, "edit", "Editing notes.md"),
    ("Write", {"file_path": "/x/plan.md"}, "edit", "Writing plan.md"),
    ("Grep", {"pattern": "invoice"}, "search", "Searching your files for “invoice”"),
    ("Glob", {"pattern": "*.pdf", "path": str(Path.home() / "Downloads")}, "search",
     "Looking for files in your Downloads folder"),
    ("WebSearch", {"query": "weather berlin"}, "web", "Searching the web for “weather berlin”"),
    ("WebFetch", {"url": "https://www.example.com/a"}, "web", "Reading example.com"),
    ("mcp__computer__screenshot", {}, "tool", "Looking at the screen"),
    ("mcp__notes__create_note", {"title": "x"}, "tool", "Create note"),
    ("Bash", {"command": "make -j8", "description": "Build the thing"}, "command", "Build the thing"),
])
def test_claude_tools_get_plain_titles(name, args, kind, title):
    (step,) = feed(ClaudeActivity, claude_line(name, args))
    assert (step.kind, step.title, step.status) == (kind, title, R)


def test_claude_bookkeeping_tools_are_not_shown():
    assert feed(ClaudeActivity, claude_line("TodoWrite", {"todos": []})) == []
    assert feed(ClaudeActivity, claude_line("StructuredOutput", {"emotion": "happy", "say": "Done."})) == []


def test_milo_mac_calls_are_left_to_the_brain():
    """HandsService logs them with what they touched ("Clicking Save in Excel"), so the CLI's copy is skipped."""
    assert feed(ClaudeActivity, claude_line("mcp__milo-mac__click", {"x": 1, "y": 2})) == []
    codex = json.dumps({"type": "item.started", "item": {"id": "i1", "type": "mcp_tool_call", "server": "milo-mac",
                                                          "tool": "click", "arguments": {}, "status": "in_progress"}})
    assert feed(CodexActivity, codex) == []


@pytest.mark.parametrize("command, kind, title", [
    ("open -a 'Microsoft Excel'", "app", "Opening Microsoft Excel"),
    ("osascript -e 'tell application \"Numbers\" to activate'", "app", "Working in Numbers"),
    ("ls -la ~/Downloads", "read", "Looking in your Downloads folder"),
    ("cd ~/Documents && ls", "read", "Looking in your Documents folder"),
    ("sed -n '1,40p' report.txt", "read", "Reading report.txt"),
    ("rg -n 'Hetzner' ~/Documents", "search", "Searching your files for “Hetzner”"),
    ("mv a.jpg 2026-10-24.jpg", "edit", "Moving a.jpg"),
    ("echo hi > /dev/null", "command", "Running a command"),
    ("curl -sL https://www.hetzner.com/x", "web", "Downloading from hetzner.com"),
    ("python3 -c 'print(1)'", "command", "Running a small program"),
    ("/bin/zsh -lc 'mkdir -p ~/Pictures/Friday'", "edit", "Making the Friday folder"),
    ("frobnicate --all", "command", "Running a command"),
])
def test_shell_commands_in_plain_words(command, kind, title):
    assert describe_command(command, WORKDIR) == (kind, title)


def test_titles_stay_short():
    (step,) = feed(ClaudeActivity, claude_line("WebSearch", {"query": "x " * 200}))
    assert len(step.title) <= 64


def test_claude_result_line_picks_the_result_out_of_the_stream():
    out = CLAUDE_RUN + CLAUDE_RESULT + "\n"
    assert json.loads(result_line(out))["structured_output"]["say"] == "On it!"
    assert result_line("not json") == "not json"


def test_codex_harness_reports_steps_while_it_runs(tmp_path, ctx):
    events = tmp_path / "events.jsonl"
    events.write_text(CODEX_RUN)
    binary = fake_cli(tmp_path, f'cat "{events}"\n')
    steps: list[Step] = []
    reply = asyncio.run(HARNESSES.create("codex", {"binary": binary}, ctx).reply("hi", None, on_step=steps.append))
    assert reply.say == "Done"
    assert [s.status for s in steps] == [R, D, R, D]


def test_claude_harness_reports_steps_and_reads_the_result_line(tmp_path, ctx):
    events = tmp_path / "events.jsonl"
    events.write_text(CLAUDE_RUN + CLAUDE_RESULT + "\n")
    binary = fake_cli(tmp_path, f'cat "{events}"\n')
    ctx.home.mkdir(parents=True)
    steps: list[Step] = []
    h = HARNESSES.create("claude", {"binary": binary}, ctx)
    reply = asyncio.run(h.reply("hi", None, on_step=steps.append))
    assert (reply.say, reply.session_id) == ("On it!", "s1")
    assert len(steps) == 6
    assert asyncio.run(h.reply("hi", None)).say == "On it!", "without a callback it still answers"
