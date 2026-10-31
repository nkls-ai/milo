"""Reading the text of common file types with what macOS ships, and keeping paths inside the allowed folder."""

from __future__ import annotations

import email
import email.policy
import os
import re
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from milo.core.control import Protected
from milo.core.types import ToolError

PLAIN = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log", ".xml", ".yaml", ".yml", ".ini", ".ics",
         ".vcf", ".text"}
TEXTUTIL = {".doc", ".docx", ".rtf", ".rtfd", ".odt", ".html", ".htm", ".webarchive", ".wordml"}
READABLE = PLAIN | TEXTUTIL | {".pdf", ".xlsx", ".eml"}
TIMEOUT_S = 30

OUTSIDE = "That file is outside the folders Milo may look in."
MILOS = "That is one of Milo's own files. Only the user changes those, in Milo's settings."
SHARED = "That folder is shared or synced to the internet, so I don't move files into it. The user can do that."
# Top-level folders of the home that other people or the internet can see. ~/Library (iCloud Drive and the
# cloud storage apps) is out of reach anyway.
_SHARED = ("public", "sites", "dropbox", "google drive", "my drive", "onedrive", "box", "box sync", "icloud drive",
           "nextcloud", "owncloud", "pcloud drive", "mega", "sync")

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


def allowed(path: Path, scope: Path, home: Path | None = None, protected: Protected | None = None) -> bool:
    """Inside `scope`, not in ~/Library or any hidden folder, and not one of Milo's control files (`protected`,
    ADR 0020). Names compare without case, like APFS does."""
    if protected is not None and protected.covers(path):
        return False
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


def checked(path: str, scope: Path, protected: Protected | None = None) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = scope / p
    if protected is not None and protected.covers(p):
        raise ToolError(MILOS)
    if not allowed(p, scope):
        raise ToolError(OUTSIDE)
    if not p.is_file():
        raise ToolError("I couldn't find that file.")
    return p.resolve()


def folder(path: str, scope: Path, *, must_exist: bool = True, protected: Protected | None = None) -> Path:
    """A folder inside `scope`, like "~/Downloads" or "Invoices" (inside the scope)."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = scope / p
    if protected is not None and protected.covers(p):
        raise ToolError(MILOS)
    if not allowed(p, scope):
        raise ToolError(OUTSIDE)
    if must_exist and not p.is_dir():
        raise ToolError("I couldn't find that folder.")
    if p.exists() and not p.is_dir():
        raise ToolError("That is a file, not a folder.")
    return p.resolve()


def listing(path: str, scope: Path, name: str = "", limit: int = 20, protected: Protected | None = None) -> list[dict]:
    """The files right inside one folder whose name contains `name`, newest first. No Spotlight needed."""
    where = folder(path, scope, protected=protected)
    return newest([p for p in where.iterdir() if name.lower() in p.name.lower()], scope, limit, protected)


def move(paths: list[str], into: str, scope: Path, protected: Protected | None = None) -> dict:
    """Move files into a folder inside `scope`, making the folder if needed. Nothing is ever replaced: if a
    file of the same name is there, nothing moves."""
    if not paths:
        raise ToolError("Say which files to move.")
    files = [checked(p, scope, protected) for p in paths]
    dest = folder(into, scope, must_exist=False, protected=protected)
    if shared(dest):
        raise ToolError(SHARED)
    clashes = [f.name for f in files if (dest / f.name).exists() and (dest / f.name).resolve() != f]
    if clashes:
        raise ToolError(f"There is already a file called {clashes[0]} in that folder, so I moved nothing.")
    if len({f.name for f in files}) < len(files):
        raise ToolError("Two of those files have the same name, so I moved nothing.")
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    into_fd = _pinned(dest, scope, protected, into=True)
    try:
        for f in files:
            target = dest / f.name
            if target.resolve() != f:
                from_fd = _pinned(f.parent, scope, protected)
                try:
                    try:
                        os.stat(f.name, dir_fd=into_fd, follow_symlinks=False)
                        raise ToolError(f"There is already a file called {f.name} in that folder.")
                    except FileNotFoundError:
                        pass
                    os.rename(f.name, f.name, src_dir_fd=from_fd, dst_dir_fd=into_fd)
                finally:
                    os.close(from_fd)
            moved.append(describe(target, scope))
    finally:
        os.close(into_fd)
    return {"moved": moved, "folder": describe_folder(dest)}


def _pinned(folder: Path, scope: Path, protected: Protected | None, *, into: bool = False) -> int:
    """A handle on `folder` (resolved when it was checked), checked again through the handle itself. The
    folders were checked by path, and a helper can make links in its own folder: one swapped in since then
    can't redirect the move now. `into`: the destination, which mustn't be shared either."""
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        real = Path(_path_of(fd))
        if protected is not None and protected.covers(real):
            raise ToolError(MILOS)
        if str(real).casefold() != str(folder).casefold() or not allowed(real, scope, protected=protected):
            raise ToolError(OUTSIDE)
        if into and shared(real):
            raise ToolError(SHARED)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _path_of(fd: int) -> str:
    """The real path of an open folder."""
    import fcntl  # here, not at the top: Windows has no fcntl, and loading this adapter must not fail there

    if hasattr(fcntl, "F_GETPATH"):  # macOS
        return os.fsdecode(fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0])
    return os.readlink(f"/proc/self/fd/{fd}")


def shared(path: Path, home: Path | None = None) -> bool:
    """`path` is in a folder of the home that is shared or synced: ~/Public, ~/Dropbox, ~/OneDrive - Work, ..."""
    try:
        top = path.resolve().relative_to((home or Path.home()).resolve()).parts[:1]
    except ValueError:
        return False
    name = top[0].casefold() if top else ""
    return any(name == s or name.startswith(s + " ") or name.startswith(s + "-") for s in _SHARED)


def describe_folder(path: Path) -> str:
    home = Path.home()
    return f"~/{path.relative_to(home)}" if path.is_relative_to(home) else str(path)


def describe(path: Path, scope: Path) -> dict:
    st = path.stat()
    home = Path.home()
    shown = f"~/{path.relative_to(home)}" if path.is_relative_to(home) else str(path)
    return {"path": str(path), "name": path.name, "where": shown,
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"), "size": st.st_size}


def newest(paths: list[Path], scope: Path, limit: int, protected: Protected | None = None) -> list[dict]:
    files = [p for p in paths if p.is_file() and allowed(p, scope, protected=protected)]
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
