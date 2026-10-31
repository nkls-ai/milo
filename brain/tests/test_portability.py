"""The platform boundary (ADR 0027): the brain's core stays free of macOS, so a Windows or Linux app can drive it.

Platform specifics belong in `milo/adapters/` (picked by name in config.toml) and in the native app. This test
reads every core module and fails when one imports or names something only macOS has: AppleScript, bundle ids,
macOS paths and commands, the ⌘ key vocabulary, System Settings, Apple-only frameworks and apps, "Mac" in words
the user or the model reads, POSIX-only calls, `%-d`-style strftime flags (Windows raises on them; use
`milo.core.words.dates`), and branches on `sys.platform`.

It reads code, not comments: imports, attribute uses and string values. Docstrings and other bare strings are
left alone, so a comment may still say how macOS behaves.

`ALLOWED` is today's state, one (file, rule) pair per line with why it is there. It is the to-do list for a port:
moving a coupling out deletes its line, and a line that matches nothing any more fails too. `CEILING` holds the
count and only goes down, so the list only shrinks: a new coupling in core needs a new line here and a `GROWN`
entry with a reason a reviewer will accept. Usually the answer is an adapter, a port or `milo.system` instead.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

SRC = Path(__file__).parents[1] / "src" / "milo"

CORE = ("core", "services", "memory", "proactive", "connect", "transport")
"""Packages that must work on any platform. Not here: `adapters/` (that is where platforms live), `system/` (the
OS primitives, one module per OS family; tests/test_system.py keeps them in step), `eval/`
(developer tools that drive the real Mac app) and `workspace_template/` (no Python)."""
TOP_LEVEL = ("brain.py", "compose.py", "config.py", "config_file.py", "mcp_server.py", "server.py", "settings.py")

TEXT_RULES: dict[str, re.Pattern[str]] = {
    "applescript": re.compile(r"osascript|applescript|\btell application\b|JavaScript for Automation|\bJXA\b",
                              re.IGNORECASE),
    "bundle-id": re.compile(r"\b(?:com|org|net|us|co|io|company)\.[a-z0-9-]+\.[a-z0-9.-]+", re.IGNORECASE),
    "mac-path": re.compile(r"~/Library|\bLibrary/|/Applications\b|/System/|/usr/bin/|\.app\b"),
    "mac-keys": re.compile(r"\bcmd\b|\bcommand\+|\+command\b|\boption\+|\+option\b|[⌘⌥⌃]|right_(?:option|command|control)"
                           r"|\bfn\b", re.IGNORECASE),
    "mac-settings": re.compile(r"System Settings|System Preferences|Systemeinstellungen|Privacy & Security"
                               r"|Full Disk Access|systempreferences", re.IGNORECASE),
    "mac-framework": re.compile(r"\bmlx\w*|\bmps\b|PyObjC|\bAppKit\b|\bQuartz\b|EventKit|PDFKit|Spotlight"
                                r"|\bTCC\b|\bAX[A-Z]\w+|Apple Silicon|LOCAL_PEERCRED|AppleLocale"),
    "mac-app": re.compile(r"\b(?:Finder|Safari|TextEdit|Numbers|Pages|Keynote|Script Editor|Automator|iMessage)\b"),
    "mac-word": re.compile(r"\bmacOS\b|\bMacs?\b|\bMac's\b"),
    "posix-strftime": re.compile(r"%[-#][aAbBdeHIjmMpSyYUwWxXcZ]"),
}
"""Matched against string values in code, case as written unless the rule says otherwise."""

MAC_COMMANDS = frozenset({
    "osascript", "defaults", "pmset", "mdfind", "mdls", "textutil", "shortcuts", "say", "launchctl", "open",
    "pbcopy", "pbpaste", "sw_vers", "plutil", "screencapture", "afplay", "sips", "security", "codesign",
})
"""Programs only macOS ships, as the first word of an argv list or tuple: rule "mac-command"."""

MAC_MODULES = frozenset({
    "objc", "AppKit", "Foundation", "Quartz", "ApplicationServices", "CoreFoundation", "ScriptingBridge",
    "EventKit", "mlx", "mlx_whisper", "mlx_lm", "applescript", "osascript", "Cocoa", "PyObjCTools",
})
"""Imports of these: rule "mac-import"."""

POSIX_MODULES = frozenset({"fcntl", "termios", "pwd", "grp", "resource", "pty", "tty", "posix"})
POSIX_ATTRS = frozenset({
    "os.getuid", "os.geteuid", "os.killpg", "os.getpgid", "os.setsid", "os.fchown", "os.chown",
    "socket.AF_UNIX", "signal.SIGKILL", "signal.SIGHUP", "signal.SIGUSR1", "signal.SIGUSR2",
})
"""Imports and uses that Windows lacks: rule "posix"."""

PLATFORM_ATTRS = frozenset({"sys.platform", "platform.system", "platform.mac_ver", "platform.machine", "os.uname"})
"""Branching on the platform belongs in adapters or compose's choice of them: rule "platform-branch"."""


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    line: int
    text: str


def _strings(tree: ast.AST) -> list[tuple[int, str]]:
    """String values in code, without docstrings and other bare string statements."""
    bare = {id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in bare]


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        inner = _dotted(node.value)
        return f"{inner}.{node.attr}" if inner else ""
    return node.id if isinstance(node, ast.Name) else ""


def scan(source: str, path: str) -> list[Finding]:
    """Every coupling to macOS (and to POSIX) in one module's code."""
    tree = ast.parse(source)
    found: list[Finding] = []
    for line, value in _strings(tree):
        for rule, pattern in TEXT_RULES.items():
            match = pattern.search(value)
            if match:
                found.append(Finding(path, rule, line, match.group(0)))
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts and isinstance(node.elts[0], ast.Constant) \
                and isinstance(node.elts[0].value, str) and node.elts[0].value.rsplit("/", 1)[-1] in MAC_COMMANDS:
            found.append(Finding(path, "mac-command", node.lineno, node.elts[0].value))
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules = [node.module]
        for module in modules:
            top = module.split(".")[0]
            if top in MAC_MODULES:
                found.append(Finding(path, "mac-import", node.lineno, module))
            if top in POSIX_MODULES:
                found.append(Finding(path, "posix", node.lineno, module))
        if isinstance(node, ast.Attribute):
            name = _dotted(node)
            if name in POSIX_ATTRS:
                found.append(Finding(path, "posix", node.lineno, name))
            if name in PLATFORM_ATTRS:
                found.append(Finding(path, "platform-branch", node.lineno, name))
    return found


def core_files() -> list[Path]:
    files = [SRC / name for name in TOP_LEVEL]
    for package in CORE:
        files += sorted((SRC / package).rglob("*.py"))
    return files


def findings() -> list[Finding]:
    out: list[Finding] = []
    for file in core_files():
        out += scan(file.read_text(encoding="utf-8"), file.relative_to(SRC).as_posix())
    return out


ALLOWED: dict[tuple[str, str], str] = {
    # Config: key names chosen for a Mac.
    ("config.py", "mac-keys"): "push-to-talk key names (fn, right_option) and the cmd/option combo grammar",
    ("settings.py", "mac-keys"): "Settings labels for the Mac's push-to-talk keys (Right Option, fn)",
    # The worker's tools: names, descriptions and the protocol to the app.
    ("core/hands.py", "applescript"): "the run_applescript tool; becomes run_script with a language (ADR 0027)",
    ("core/hands.py", "mac-app"): "sheet_write/write_document enums and examples name Numbers, TextEdit, Pages, Keynote",
    ("core/hands.py", "mac-keys"): "the key tool's vocabulary is cmd/option; becomes mod/alt (ADR 0027)",
    ("core/hands.py", "mac-word"): "INSTRUCTIONS say the tools act on the user's Mac",
    ("mcp_server.py", "mac-word"): "NO_BRAIN says \"the Mac tools are off\"",
    ("services/hands.py", "applescript"): "gating, logging and app detection of run_applescript scripts",
    ("services/hands.py", "mac-keys"): "_pretty_combo shows combos with the Mac's ⌘⌥⌃ glyphs",
    ("services/hands.py", "mac-settings"): "NOT_ALLOWED points to System Settings › Privacy & Security › Automation",
    ("services/hands.py", "mac-word"): "messages to the worker name the Mac and macOS",
    ("services/snapshots.py", "applescript"): "Undo's Excel copy, fingerprint and restore (ADR 26); moves behind the "
                                              "per-platform script builder with sheets.py",
    ("services/undo.py", "applescript"): "Undo runs those scripts with run_applescript; becomes run_script (ADR 27)",
    ("memory/undo_shelf.py", "bundle-id"): "APP_FOLDERS names Excel's sandbox container; should come from "
                                           "AccessGate.places (ADR 25) instead",
    ("memory/undo_shelf.py", "mac-path"): "the same container path, under ~/Library",
    ("connect/milo_tools.py", "mac-app"): "undo_point's description names Numbers as an app without a copy",
    ("connect/tools.py", "mac-keys"): "the worker's undo instructions say Excel's ⌘Z can't undo a script",
    ("services/sheets.py", "applescript"): "sheet_write/sheet_read compose AppleScript; moves behind a per-platform script builder",
    ("services/sheets.py", "mac-app"): "Excel and Numbers by their Mac names",
    ("services/sheets.py", "mac-path"): "app_name strips \".app\" from a path",
    ("services/documents.py", "applescript"): "write_document composes AppleScript for TextEdit and Pages",
    ("services/documents.py", "mac-app"): "TextEdit and Pages are the document apps",
    # Risk: the word lists know Mac apps, bundle ids and shortcuts.
    ("services/risk.py", "applescript"): "the run_applescript rule and the do shell script / osascript words",
    ("services/risk.py", "bundle-id"): "app lists (trash, documents, browsers, secrets, code) include bundle ids",
    ("services/risk.py", "mac-keys"): "_RISKY_COMBOS and the modifier aliases are the Mac's (cmd+delete, ⌘)",
    ("services/risk.py", "mac-path"): "app_names strips \".app\" from a path",
    ("services/risk.py", "mac-settings"): "System Settings is the settings app the never-rules guard",
    # App identity: bundle ids stand for apps.
    ("core/types.py", "bundle-id"): "_BUNDLES maps app names to Mac bundle ids for AppRef",
    ("core/types.py", "mac-path"): "_name strips \".app\" from a path",
    ("services/tool_requests.py", "bundle-id"): "AppRefs for Calendar, Reminders, Notes and Finder by bundle id",
    ("services/tool_requests.py", "mac-app"): "Finder is the app the files tools change things in",
    ("connect/server.py", "mac-app"): "Finder is the app the files tools change things in",
    ("services/helpers.py", "mac-path"): "is_installed_app looks for Name.app in /Applications",
    ("proactive/engine.py", "mac-app"): "quiet_apps default names Keynote (and zoom.us, a Mac process name)",
    # Words the user or the model reads.
    ("connect/milo_tools.py", "mac-word"): "a reminder is said out loud \"on the Mac\"",
    ("connect/tools.py", "mac-app"): "send_to_phone names iMessage as a channel",
    ("connect/tools.py", "mac-framework"): "files_search says Spotlight",
    ("connect/tools.py", "mac-path"): "files_find says it skips ~/Library",
    ("connect/tools.py", "mac-word"): "INSTRUCTIONS say the apps are on this Mac",
    ("services/approvals.py", "mac-word"): "a log line about an answer at the Mac",
    ("services/brief.py", "mac-word"): "\"is Milo running on the Mac?\"",
    ("services/cloud_hearing.py", "mac-word"): "NOTICE says it transcribes on this Mac",
    ("services/talk_prompt.py", "mac-app"): "the talker's prompt names Numbers among the apps",
    ("services/messages.py", "mac-word"): "phone replies say \"at your Mac\"",
    ("services/routines.py", "mac-app"): "the recipe example uses apps: [Numbers]",
    ("services/routines.py", "mac-word"): "the recipe prompt asks for \"the Mac apps\" the work used",
    ("services/settings_guard.py", "mac-word"): "PUT_BACK says \"change them at the Mac\"",
    ("services/orchestrator.py", "mac-settings"): "_SCREEN_WORDS counts \"system settings\" as screen work",
    # Private folders are where macOS keeps them.
    ("services/sharing.py", "bundle-id"): "PRIVATE lists Library/Application Support/com.apple.TCC",
    ("services/sharing.py", "mac-framework"): "PRIVATE lists the TCC database folder",
    ("services/sharing.py", "mac-path"): "PRIVATE lists ~/Library folders (Keychains, Cookies, Messages, Mail)",
    # Recall eval data: made-up memories that mention apps.
    ("memory/index.py", "mac-app"): "an ANCHORS sentence (the yardstick for background scores) mentions Safari",
    ("memory/recall_eval.py", "mac-app"): "eval memories mention Safari and Finder",
    ("memory/recall_eval.py", "mac-framework"): "the eval runs with the mlx_e5 embedder",
    ("memory/recall_eval.py", "mac-settings"): "eval memories mention System Settings",
}


CEILING = 55
"""How many ALLOWED lines there were at the last count (2026-10-31: 57, less the one in GROWN). It only goes down:
when a coupling moves out and its line goes, lower it too. It never goes up."""

GROWN: dict[tuple[str, str], str] = {}
"""ALLOWED lines added past CEILING, each with why the coupling can't be an adapter or a port yet. A reviewer reads
this dict; growing ALLOWED without a line here fails test_allowlist_only_grows_with_a_reason."""


def test_allowlist_only_grows_with_a_reason():
    unexplained = len(ALLOWED) - CEILING - len(GROWN)
    assert unexplained <= 0, (f"ALLOWED grew by {unexplained} line(s) with no GROWN entry. Move the coupling into an "
                              "adapter or milo.system, or add its (file, rule) to GROWN with why it can't move yet.")
    assert unexplained == 0, f"ALLOWED shrank: lower CEILING to {len(ALLOWED) - len(GROWN)}, so it stays down."
    assert set(GROWN) <= set(ALLOWED), "a GROWN line whose coupling is gone: delete it from both"
    assert all(len(reason.split()) >= 8 for reason in GROWN.values()), "say why it can't move, in a sentence"


def test_the_docs_state_todays_count():
    files = len({path for path, _ in ALLOWED})
    text = (SRC.parents[2] / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert f"today's {len(ALLOWED)} exceptions in {files} files" in text, \
        f"docs/ARCHITECTURE.md (Portability) should say \"today's {len(ALLOWED)} exceptions in {files} files\""


def test_core_names_no_new_macos_couplings():
    new: dict[tuple[str, str], list[Finding]] = {}
    for f in findings():
        if (f.path, f.rule) not in ALLOWED:
            new.setdefault((f.path, f.rule), []).append(f)
    lines = [f"  {path} [{rule}]: " + ", ".join(f"line {f.line} {f.text!r}" for f in hits[:4])
             for (path, rule), hits in sorted(new.items())]
    assert not new, ("macOS-only code in the brain's core (ADR 0027). Put it in an adapter behind a port, or, "
                     "if it truly can't move yet, add a line to ALLOWED with the reason:\n" + "\n".join(lines))


def test_allowlist_has_no_stale_lines():
    seen = {(f.path, f.rule) for f in findings()}
    stale = sorted(set(ALLOWED) - seen)
    assert not stale, "These couplings are gone, so delete their lines from ALLOWED: " + ", ".join(
        f"{path} [{rule}]" for path, rule in stale)


def test_allowlist_lines_say_why():
    assert all(len(reason.split()) >= 3 for reason in ALLOWED.values()), "each line says why, in a few words"
    assert all(rule in TEXT_RULES or rule in ("mac-command", "mac-import", "posix", "platform-branch")
               for _, rule in ALLOWED)


@pytest.mark.parametrize("code, rule", [
    ('run(["osascript", "-e", s])', "mac-command"),
    ('run(("/usr/bin/pmset", "-g"))', "mac-command"),
    ('APP = "com.apple.finder"', "bundle-id"),
    ('HINT = "press cmd+s"', "mac-keys"),
    ('ERR = "Turn it on in System Settings"', "mac-settings"),
    ('SAY = "on your Mac"', "mac-word"),
    ('SCRIPT = \'tell application "Numbers"\'', "applescript"),
    ("import mlx.core as mx", "mac-import"),
    ("import fcntl", "posix"),
    ("x = os.getuid()", "posix"),
    ("if sys.platform == 'darwin': pass", "platform-branch"),
    ('P = "~/Library/Mail"', "mac-path"),
    ('s = f"{day:%A %-d %B}"', "posix-strftime"),
    ('s = day.strftime("%#d")', "posix-strftime"),
])
def test_scan_catches(code, rule):
    assert rule in {f.rule for f in scan(code, "x.py")}


@pytest.mark.parametrize("code", [
    '"""Runs on macOS through osascript, see cmd+s in System Settings."""',
    "def f():\n    \"\"\"The Mac's Finder.\"\"\"\n    return 1",
    "# osascript on the Mac\nx = 1",
    'KEY = "say"',
    'COMBO = "mod+s"',
    's = f"{day:%d %H:%M} 50%-ish"',
])
def test_scan_leaves_comments_docstrings_and_plain_words(code):
    assert scan(code, "x.py") == []
