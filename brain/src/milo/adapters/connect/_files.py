"""Reading the text of common file types with what macOS ships, and keeping paths inside the allowed folder."""

from __future__ import annotations

import email
import email.policy
import re
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from milo.core.types import ToolError

PLAIN = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log", ".xml", ".yaml", ".yml", ".ini", ".ics",
         ".vcf", ".text"}
TEXTUTIL = {".doc", ".docx", ".rtf", ".rtfd", ".odt", ".html", ".htm", ".webarchive", ".wordml"}
READABLE = PLAIN | TEXTUTIL | {".pdf", ".xlsx", ".eml"}
TIMEOUT_S = 30

OUTSIDE = "That file is outside the folders Milo may look in."

# PDFKit through JavaScript for Automation: no permission prompt, no extra package.
_PDF_JXA = """
ObjC.import('PDFKit');
function run(argv) {
  const doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  if (doc.isNil()) { return ''; }
  const text = doc.string;
  return text.isNil() ? '' : ObjC.unwrap(text);
}
"""
_SHEET_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
# Python 3.12's expat resolves no external entities and caps entity expansion; this caps the rest.
MAX_XML_BYTES = 30 * 1024 * 1024


def allowed(path: Path, scope: Path, home: Path | None = None) -> bool:
    """Inside `scope`, not in ~/Library or any hidden folder. Names compare without case, like APFS does."""
    try:
        real = path.resolve()
        rel = real.relative_to(scope.resolve())
    except (ValueError, OSError):
        return False
    if any(part.startswith(".") for part in rel.parts):
        return False
    for root in (scope.resolve(), (home or Path.home()).resolve()):
        try:
            under = real.relative_to(root).parts
        except ValueError:
            continue
        if under[:1] and under[0].casefold() == "library":
            return False
    return True


def checked(path: str, scope: Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = scope / p
    if not allowed(p, scope):
        raise ToolError(OUTSIDE)
    if not p.is_file():
        raise ToolError("I couldn't find that file.")
    return p.resolve()


def describe(path: Path, scope: Path) -> dict:
    st = path.stat()
    home = Path.home()
    shown = f"~/{path.relative_to(home)}" if path.is_relative_to(home) else str(path)
    return {"path": str(path), "name": path.name, "where": shown,
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"), "size": st.st_size}


def newest(paths: list[Path], scope: Path, limit: int) -> list[dict]:
    files = [p for p in paths if p.is_file() and allowed(p, scope)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [describe(p, scope) for p in files[:limit]]


def read(path: Path, max_chars: int) -> dict:
    text = text_of(path)
    return {"path": str(path), "name": path.name, "text": text[:max_chars], "truncated": len(text) > max_chars}


def text_of(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in PLAIN:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        text = _run(["osascript", "-l", "JavaScript", "-e", _PDF_JXA, str(path)])
        if not text.strip():
            raise ToolError("That PDF has no text I can read. It may be a scan.")
        return text
    if suffix in TEXTUTIL:
        return _run(["textutil", "-convert", "txt", "-stdout", str(path)])
    if suffix == ".xlsx":
        return xlsx_text(path)
    if suffix == ".eml":
        message = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
        body = message.get_body(preferencelist=("plain", "html"))
        head = "\n".join(f"{k}: {message[k]}" for k in ("From", "To", "Date", "Subject") if message[k])
        return head + "\n\n" + (body.get_content() if body is not None else "")
    raise ToolError(f"I can't read {suffix or 'that kind of'} files yet.")


def xlsx_text(path: Path) -> str:
    """Every sheet as tab-separated rows. Values only: formulas show their last computed result."""
    try:
        with zipfile.ZipFile(path) as z:
            if any(i.file_size > MAX_XML_BYTES for i in z.infolist()):
                raise ToolError("That spreadsheet is too big for me to read.")
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
                shared = ["".join(t.text or "" for t in si.iter(f"{{{_SHEET_NS['s']}}}t"))
                          for si in root.findall("s:si", _SHEET_NS)]
            sheets = sorted((n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                            key=lambda n: int(re.findall(r"\d+", n)[-1]))
            out = []
            for name in sheets:
                out.append(f"# {Path(name).stem}")
                root = ElementTree.fromstring(z.read(name))
                for row in root.iter(f"{{{_SHEET_NS['s']}}}row"):
                    cells = []
                    for c in row.findall("s:c", _SHEET_NS):
                        v = c.find("s:v", _SHEET_NS)
                        inline = c.find("s:is", _SHEET_NS)
                        if c.get("t") == "s" and v is not None:
                            cells.append(shared[int(v.text)] if int(v.text) < len(shared) else "")
                        elif inline is not None:
                            cells.append("".join(t.text or "" for t in inline.iter(f"{{{_SHEET_NS['s']}}}t")))
                        else:
                            cells.append(v.text if v is not None and v.text else "")
                    out.append("\t".join(cells))
            return "\n".join(out)
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, ValueError):
        raise ToolError("That spreadsheet looks damaged.") from None


def _run(cmd: list[str]) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        raise ToolError("Reading that file took too long.") from None
    if done.returncode != 0:
        raise ToolError("I couldn't read that file.")
    return done.stdout
