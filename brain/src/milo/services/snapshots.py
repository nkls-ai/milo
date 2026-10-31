"""The AppleScript behind Undo in Excel (ADR 0024): save a copy of a workbook, read its fingerprint, copy it back.

Excel is sandboxed. A script that saves or opens a file outside Excel's own folder makes it show "Grant File Access"
and wait, so every path here must sit in that folder (`folder`), and anything else is refused before a script is
written. Each script turns Excel's alerts off while it works, so a question such as "Save with references to unsaved
documents?" takes its default answer instead of waiting on the screen, and turns them back to what they were.

Measured on this Mac (Excel 16, macOS 26.3) with a scratch workbook: copying a one-sheet workbook into a new
workbook, saving that into Excel's folder and closing it took about 1 s and showed no dialog. Copying a red sheet's
whole range back from the saved copy restored values, formulas, fills, fonts, bold and column widths in under 1 s.
Copying a second sheet that refers to the first turned the reference into a link to the open workbook, and saving
then asked about it; with alerts off that question isn't shown, which is untested.
"""

from __future__ import annotations

import os
import re

from .sheets import literal

EXCEL = "Microsoft Excel"
MARK = "-- milo-undo"
"""Every script Undo writes starts with this line and its kind, so logs and tests can tell them from the worker's."""
WHOLE = 'range "A1:XFD1048576"'
TIMEOUT_S = 120

_WORKBOOK = re.compile(r'\bworkbook\s+"([^"]+)"', re.IGNORECASE)
_TELL = re.compile(r'tell application "([^"]+)"', re.IGNORECASE)


def workbooks_in(script: str) -> list[str]:
    """The workbooks a script names, in order. Empty when it names none (it works on the active one)."""
    return list(dict.fromkeys(_WORKBOOK.findall(script)))


def apps_in(script: str) -> list[str]:
    """The apps a script tells, by name."""
    return list(dict.fromkeys(_TELL.findall(script)))


def inside(path: str, folder: str) -> str:
    """`path` if it is a file right in `folder` (no links, no ..); raises ValueError otherwise. The guard that keeps
    Excel from asking for file access."""
    real, home = os.path.normpath(path), os.path.normpath(folder)
    if os.path.dirname(real) != home or real != path or '"' in path or "\\" in path:
        raise ValueError(f"{path} is outside {folder}")
    return path


def _source(workbook: str) -> str:
    return f"workbook {literal(workbook)}" if workbook else "active workbook"


_QUIET = """\
	set alertsWere to display alerts
	set display alerts to false
	set screen updating to false
"""
_LOUD = """\
		set screen updating to true
		set display alerts to alertsWere
"""
_NEW_BOOK = """\
		set copyBook to missing value
		repeat with i from 1 to count of workbooks
			if namesBefore does not contain (name of workbook i) then set copyBook to workbook i
		end repeat
		if copyBook is missing value then error "Excel made no copy."
"""


def excel_snapshot(workbook: str, path: str, *, folder: str) -> str:
    """Save a copy of `workbook` ("" for the active one) to `path`: its sheets copied one by one into a new workbook,
    which is saved and closed. The user's workbook isn't saved, renamed or changed. Answers `document` and `sheets`."""
    path = inside(path, folder)
    return f"""{MARK} snapshot
with timeout of {TIMEOUT_S} seconds
tell application "{EXCEL}"
	set src to {_source(workbook)}
	set docName to name of src
	set namesBefore to name of every workbook
{_QUIET}	try
		copy worksheet (worksheet 1 of src)
{_NEW_BOOK}		repeat with i from 2 to count of worksheets of src
			copy worksheet (worksheet i of src) after (worksheet (i - 1) of copyBook)
		end repeat
		save workbook as copyBook filename {literal(path)} file format Excel XML file format
		close copyBook saving no
	on error e
		try
			close copyBook saving no
		end try
{_LOUD}		error e
	end try
{_LOUD.replace(chr(9) + chr(9), chr(9))}	set sheetNames to name of every worksheet of src
	set AppleScript's text item delimiters to tab
	set out to "document" & tab & docName & linefeed & "sheets" & tab & (sheetNames as text)
	set AppleScript's text item delimiters to ""
	return out
end tell
end timeout"""


def excel_fingerprint(workbook: str) -> str:
    """What a workbook holds, as text to compare: each sheet's name, used range, formulas, and the fill and font colour
    over the whole sheet. Equal text means nobody changed what Undo would overwrite, as far as this can see."""
    return f"""{MARK} fingerprint
with timeout of 60 seconds
tell application "{EXCEL}"
	set wb to {_source(workbook)}
	set out to {{}}
	repeat with i from 1 to count of worksheets of wb
		set s to worksheet i of wb
		set end of out to name of s
		try
			set u to used range of s
			set end of out to (get address of u)
			set end of out to (formula of u)
		end try
		try
			set end of out to (color of interior object of {WHOLE} of s)
		end try
		try
			set end of out to (color of font object of {WHOLE} of s)
		end try
	end repeat
	set AppleScript's text item delimiters to tab
	set text_ to out as text
	set AppleScript's text item delimiters to ""
	return text_
end tell
end timeout"""


def excel_restore(workbook: str, path: str, *, folder: str) -> str:
    """Copy every sheet of the saved copy at `path` back over the sheet of the same name in `workbook`: values,
    formulas and formats, the whole sheet. The copy opens read-only and closes unsaved. Answers `document`."""
    path = inside(path, folder)
    return f"""{MARK} restore
with timeout of {TIMEOUT_S} seconds
tell application "{EXCEL}"
	set dst to {_source(workbook)}
	set namesBefore to name of every workbook
{_QUIET}	try
		open workbook workbook file name {literal(path)} read only true
{_NEW_BOOK}		repeat with i from 1 to count of worksheets of copyBook
			set sheetName to name of worksheet i of copyBook
			copy range ({WHOLE} of worksheet i of copyBook) destination (range "A1" of worksheet sheetName of dst)
		end repeat
		close copyBook saving no
	on error e
		try
			close copyBook saving no
		end try
{_LOUD}		error e
	end try
{_LOUD.replace(chr(9) + chr(9), chr(9))}	return "document" & tab & (name of dst)
end tell
end timeout"""
