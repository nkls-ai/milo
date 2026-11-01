"""Data-only Office operations, separate from clipboard and accessibility.

Windows edits the active Excel workbook through COM and creates Word documents.
When a live Office application is unavailable, new documents can be generated
as interoperable files. Existing documents are never silently replaced by files.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable
from copy import copy
from pathlib import Path
from typing import Protocol

from milo.core.types import HandsError
from milo.services import documents, sheets

from ._native_types import NativeError

_DANGEROUS_FORMULA = re.compile(r"\b(?:WEBSERVICE|HYPERLINK|RTD|CALL|EXEC|REGISTER|RUN|SQL\.REQUEST|DDE)\s*\(", re.I)
_FORMULA_FUNCTIONS = frozenset((
    "SUM AVERAGE MIN MAX COUNT COUNTA COUNTBLANK COUNTIF COUNTIFS SUMIF SUMIFS AVERAGEIF AVERAGEIFS "
    "IF IFS IFERROR IFNA AND OR NOT TRUE FALSE ABS ROUND ROUNDUP ROUNDDOWN INT MOD CEILING FLOOR "
    "VLOOKUP HLOOKUP XLOOKUP LOOKUP INDEX MATCH XMATCH CHOOSE CHOOSECOLS CHOOSEROWS "
    "CONCAT CONCATENATE TEXT TEXTJOIN LEFT RIGHT MID LEN TRIM UPPER LOWER PROPER SUBSTITUTE REPLACE "
    "VALUE NUMBERVALUE ISNUMBER ISTEXT ISBLANK ISERROR ISNA DATE DATEVALUE TIME TIMEVALUE TODAY NOW "
    "YEAR MONTH DAY HOUR MINUTE SECOND WEEKDAY WEEKNUM DAYS DATEDIF EDATE EOMONTH NETWORKDAYS WORKDAY "
    "SUBTOTAL AGGREGATE SUMPRODUCT PRODUCT POWER SQRT EXP LN LOG LOG10 SIGN RAND RANDBETWEEN "
    "SORT SORTBY FILTER UNIQUE SEQUENCE TRANSPOSE ROW ROWS COLUMN COLUMNS SMALL LARGE RANK RANK.EQ "
    "PERCENTILE.INC PERCENTILE.EXC MEDIAN STDEV STDEV.S STDEV.P VAR VAR.S VAR.P"
).split())
_TOOLS = ("sheet_write", "sheet_read", "write_document")


class OfficeUnavailable(NativeError):
    pass


class OfficeBackend(Protocol):
    def describe(self, tool: str, args: dict) -> dict: ...

    def run(self, tool: str, args: dict) -> dict: ...


def _range(reference: str) -> str:
    reference = sheets.check_range(reference)
    ends = reference.split(":")
    left, top = sheets.cell(ends[0])
    right, bottom = sheets.cell(ends[-1])
    if right < left or bottom < top or right > 16384 or bottom > 1048576:
        raise NativeError("That range is outside a spreadsheet or has its corners reversed.")
    if (right - left + 1) * (bottom - top + 1) > sheets.MAX_CELLS:
        raise NativeError(f"Use at most {sheets.MAX_CELLS} cells in one operation.")
    return reference


def _validate(args: dict, *, writing: bool = True) -> sheets.Block | None:
    rows = args.get("rows") or []
    block = sheets.block(rows, args.get("start", "A1")) if rows else None
    if block:
        _range(block.range)
        for row in rows:
            for value in row:
                if isinstance(value, float) and not math.isfinite(value):
                    raise NativeError("A cell cannot contain NaN or infinity.")
                if isinstance(value, str) and value.startswith("="):
                    if "|" in value or "[" in value or _DANGEROUS_FORMULA.search(value):
                        raise NativeError("External data, links, DDE and executable spreadsheet formulas are unavailable.")
                    expression = re.sub(r'"(?:[^\"]|\"\")*"', '""', value)
                    functions = re.findall(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(", expression)
                    if any(name.upper() not in _FORMULA_FUNCTIONS for name in functions):
                        raise NativeError("That formula uses a function outside Milo's supported calculation functions.")
    for key in ("bold", "money", "decimals"):
        for reference in sheets.ranges(args.get(key, "")):
            _range(reference)
    for key in ("fill", "font_color"):
        for reference, _ in sheets.colours(args.get(key, "")):
            if reference not in sheets.WHOLE:
                _range(reference)
    if writing and not block and not any(args.get(k) for k in ("bold", "money", "decimals", "fill", "font_color")):
        raise NativeError("Provide rows or formatting for the spreadsheet.")
    if args.get("new_document") and not block:
        raise NativeError("A new spreadsheet needs rows.")
    return block


def _grid(value) -> list[list]:
    if isinstance(value, (tuple, list)):
        return [list(row) if isinstance(row, (tuple, list)) else [row] for row in value]
    return [[value]]


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8")).hexdigest()


def new_document_path(home: Path, suffix: str) -> Path:
    """Unique managed output name shared by portable and native document adapters."""
    if suffix not in (".xlsx", ".docx", ".ods", ".odt"):
        raise NativeError("Unsupported document file type.")
    work = home / "work"
    folder = work / "created"
    if work.is_symlink() or work.is_junction() or folder.is_symlink() or folder.is_junction():
        raise NativeError("The document output folder must be a real folder, not a link.")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / ("Milo-" + uuid.uuid4().hex + suffix)


class COMGateway:
    def __call__(self, program: str, create: bool, operation: Callable):
        try:
            import pythoncom
            import pywintypes
            import win32com.client
        except ImportError:
            raise OfficeUnavailable("Live Office editing needs Windows and Microsoft Office.") from None
        pythoncom.CoInitialize()
        app = None
        try:
            try:
                app = win32com.client.Dispatch(program) if create else win32com.client.GetActiveObject(program)
            except pywintypes.com_error:
                raise OfficeUnavailable("Open Microsoft Office with the document you want to use first.") from None
            try:
                return operation(app)
            except pywintypes.com_error:
                raise NativeError("Office couldn't complete this operation. Check that the document is editable "
                                  "and that no Office dialog is waiting.") from None
        finally:
            app = None
            pythoncom.CoUninitialize()


class WindowsOffice:
    def __init__(self, call: Callable | None = None):
        self._call = call or COMGateway()
        self._expected: dict | None = None

    @staticmethod
    def _active(app):
        book, sheet = app.ActiveWorkbook, app.ActiveSheet
        if book is None or sheet is None:
            raise NativeError("Excel has no workbook and worksheet open.")
        return book, sheet

    @staticmethod
    def _target(book, sheet, args):
        block = _validate(args)
        selected = sheet.Range(block.range) if block else sheet.UsedRange
        if int(selected.Rows.Count) * int(selected.Columns.Count) > sheets.MAX_CELLS:
            raise NativeError("That sheet is too large for one operation; name smaller ranges.")
        values, formulas = selected.Value2, selected.Formula
        return {"app": "Microsoft Excel", "document": str(book.Name), "sheet": str(sheet.Name),
                "document_id": str(book.FullName), "range": block.range if block else str(selected.Address),
                # Formula may display an empty string while still containing work.
                "filled": sum(value not in (None, "") for row in _grid(formulas) for value in row) if block else 0,
                "fingerprint": _fingerprint([values, formulas])}

    def describe(self, tool: str, args: dict) -> dict:
        if tool == "write_document" or args.get("new_document"):
            if tool == "sheet_write":
                _validate(args)
            return {"app": args["app"], "new": True}
        if args.get("app") != "Microsoft Excel":
            raise OfficeUnavailable("Live spreadsheet editing on Windows supports Microsoft Excel.")

        def describe(app):
            book, sheet = self._active(app)
            target = self._target(book, sheet, args)
            self._expected = target
            return target
        return self._call("Excel.Application", False, describe)

    @staticmethod
    def _format(sheet, args, block):
        for reference in sheets.ranges(args.get("bold", "")):
            sheet.Range(reference).Font.Bold = True
        if args.get("header") and block:
            last_col, first_row = sheets.cell(block.last)[0], sheets.cell(block.first)[1]
            sheet.Range(f"{block.first}:{sheets.column_letters(last_col)}{first_row}").Font.Bold = True
        for reference in sheets.ranges(args.get("money", "")):
            sheet.Range(reference).NumberFormat = sheets.excel_money(args.get("locale", ""))
        for reference in sheets.ranges(args.get("decimals", "")):
            sheet.Range(reference).NumberFormat = "0.00"
        for key, part in (("fill", "Interior"), ("font_color", "Font")):
            for reference, (red, green, blue) in sheets.colours(args.get(key, "")):
                selected = sheet.UsedRange if reference == "sheet" else (
                    sheet.UsedRange.Rows(1) if reference == "header" else sheet.Range(reference))
                getattr(selected, part).Color = red | (green << 8) | (blue << 16)

    def run(self, tool: str, args: dict) -> dict:
        if tool == "write_document":
            if args.get("app") != "Microsoft Word":
                raise OfficeUnavailable("Live document creation on Windows supports Microsoft Word.")
            text = str(args.get("text", ""))
            if len(text) > documents.MAX_CHARS:
                raise NativeError("That document is too long for one operation.")

            def create(app):
                doc = app.Documents.Add()
                doc.Content.Text = text
                app.Visible = True
                doc.Activate()
                return {"document": str(doc.Name), "text": f"Created a new document “{doc.Name}” in Microsoft Word."}
            return self._call("Word.Application", True, create)
        if args.get("app") != "Microsoft Excel":
            raise OfficeUnavailable("Live spreadsheet editing on Windows supports Microsoft Excel.")
        if tool == "sheet_read":
            def read(app):
                book, sheet = self._active(app)
                selected = sheet.Range(_range(args["range"])) if args.get("range") else sheet.UsedRange
                if int(selected.Rows.Count) * int(selected.Columns.Count) > sheets.MAX_CELLS:
                    raise NativeError("That range is too large; read at most 2000 cells at once.")
                rows = [["" if value is None else str(value) for value in row] for row in _grid(selected.Formula)]
                return {"document": str(book.Name), "summary": f"Microsoft Excel, “{book.Name}”, sheet “{sheet.Name}”",
                        "text": sheets.table_text({"first": str(selected.Address).replace("$", ""), "rows": rows})}
            return self._call("Excel.Application", False, read)
        block = _validate(args)

        def write(app):
            if args.get("new_document"):
                book = app.Workbooks.Add()
                sheet = app.ActiveSheet
            else:
                book, sheet = self._active(app)
                actual = self._target(book, sheet, args)
                if self._expected is None or actual != self._expected:
                    raise NativeError("The Excel target changed. Read it again before writing.")
            if block:
                grid = []
                for values in args["rows"]:
                    row = []
                    for j in range(block.columns):
                        value = values[j] if j < len(values) else None
                        row.append("'" + value if isinstance(value, str) and not value.startswith("=") else value)
                    grid.append(tuple(row))
                # A single SAFEARRAY assignment: hundreds of cells do not become
                # hundreds of cross-process COM round trips. Strings remain data.
                sheet.Range(block.range).Formula = tuple(grid)
            self._format(sheet, args, block)
            app.Visible = True
            book.Activate()
            document = str(book.Name)
            self._expected = None
            return {"document": document, "text": f"Updated {block.range if block else 'the formatting'} in “{document}”, sheet “{sheet.Name}”."}
        return self._call("Excel.Application", bool(args.get("new_document")), write)


class PortableOffice:
    """Create new interoperable files. This never claims to edit an open window."""

    def __init__(self, home: Path, opener: Callable[[Path, str], bool] | None = None):
        self._home, self._opener = home, opener or self._open

    @staticmethod
    def _open(path: Path, app: str) -> bool:
        executable = shutil.which("libreoffice") or shutil.which("soffice")
        if executable and app.startswith("LibreOffice"):
            subprocess.Popen([executable, "--calc" if path.suffix == ".xlsx" else "--writer", str(path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def describe(self, tool: str, args: dict) -> dict:
        if tool != "write_document" and not args.get("new_document"):
            raise OfficeUnavailable("Live spreadsheet editing needs Microsoft Excel on Windows. "
                                    "Create a new document or use the application's own interface for existing files.")
        if tool == "sheet_write":
            _validate(args)
        return {"app": args["app"], "new": True}

    def _path(self, suffix: str) -> Path:
        return new_document_path(self._home, suffix)

    @staticmethod
    def _save(document, path: Path) -> None:
        # Cancellation may kill the actor midway through ZIP output. Publish a
        # complete document only, leaving any interrupted data as a partial file.
        partial = path.with_name("." + path.name + ".partial")
        created = False
        try:
            with partial.open("xb") as output:
                created = True
                document.save(output)
            os.link(partial, path)  # atomic publication that refuses an existing destination
        finally:
            if created:
                partial.unlink(missing_ok=True)

    @staticmethod
    def _cells(sheet, reference):
        if reference == "sheet":
            return sheet.iter_rows()
        if reference == "header":
            return sheet.iter_rows(min_row=sheet.min_row, max_row=sheet.min_row,
                                   min_col=sheet.min_column, max_col=sheet.max_column)
        parts = _range(reference).split(":")
        left, top = sheets.cell(parts[0])
        right, bottom = sheets.cell(parts[-1])
        return sheet.iter_rows(min_col=left, max_col=right, min_row=top, max_row=bottom)

    def run(self, tool: str, args: dict) -> dict:
        self.describe(tool, args)
        if tool == "sheet_write":
            from openpyxl import Workbook
            from openpyxl.styles import PatternFill

            block = _validate(args)
            book = Workbook()
            sheet = book.active
            col, row = sheets.cell(block.first)
            for i, values in enumerate(args["rows"]):
                for j, value in enumerate(values):
                    cell = sheet.cell(row + i, col + j)
                    cell.value = value
                    if isinstance(value, str) and not value.startswith("="):
                        cell.data_type = "s"
            bolds = sheets.ranges(args.get("bold", ""))
            if args.get("header"):
                bolds += [f"{block.first}:{sheets.column_letters(col + block.columns - 1)}{row}"]
            for reference in bolds:
                for cells in self._cells(sheet, reference):
                    for cell in cells:
                        font = copy(cell.font)
                        font.bold = True
                        cell.font = font
            for key, number_format in (("money", sheets.excel_money(args.get("locale", ""))), ("decimals", "0.00")):
                for reference in sheets.ranges(args.get(key, "")):
                    for cells in self._cells(sheet, reference):
                        for cell in cells:
                            cell.number_format = number_format
            for key in ("fill", "font_color"):
                for reference, rgb in sheets.colours(args.get(key, "")):
                    color = "".join(f"{channel:02X}" for channel in rgb)
                    for cells in self._cells(sheet, reference):
                        for cell in cells:
                            if key == "fill":
                                cell.fill = PatternFill("solid", fgColor=color)
                            else:
                                font = copy(cell.font)
                                font.color = color
                                cell.font = font
            path = self._path(".xlsx")
            self._save(book, path)
        elif tool == "write_document":
            from docx import Document

            text = str(args.get("text", ""))
            if len(text) > documents.MAX_CHARS:
                raise NativeError("That document is too long for one operation.")
            document = Document()
            for paragraph in text.replace("\r\n", "\n").split("\n"):
                document.add_paragraph(paragraph)
            path = self._path(".docx")
            self._save(document, path)
        else:
            raise OfficeUnavailable("Reading an open spreadsheet needs a live Office integration.")
        opened = self._opener(path, str(args.get("app", "")))
        return {"document": path.name, "path": str(path), "opened": opened,
                "text": f"Created {path}. " + ("Opened it with the installed document application." if opened
                                               else "Open this file in your document application to review it.")}


class OfficeTools:
    def __init__(self, home: Path, *, windows: WindowsOffice | None = None, portable: PortableOffice | None = None,
                 platform: str = sys.platform, linux: OfficeBackend | None = None):
        self._native: OfficeBackend | None = None
        if platform.startswith("win"):
            self._native = windows or WindowsOffice()
        elif platform.startswith("linux"):
            if linux is None:
                from ._office_uno import LibreOffice
                linux = LibreOffice(home)
            self._native = linux
        self._portable = portable or PortableOffice(home)

    def describe(self, tool: str, args: dict) -> dict:
        try:
            if self._native is not None:
                try:
                    return self._native.describe(tool, args)
                except OfficeUnavailable:
                    if tool != "write_document" and not args.get("new_document"):
                        raise
            return self._portable.describe(tool, args)
        except HandsError as e:
            raise NativeError(str(e)) from None

    def run(self, tool: str, args: dict) -> dict:
        if tool not in _TOOLS:
            raise NativeError("Unknown Office operation.")
        try:
            if self._native is not None:
                try:
                    return self._native.run(tool, args)
                except OfficeUnavailable:
                    if tool != "write_document" and not args.get("new_document"):
                        raise
            return self._portable.run(tool, args)
        except HandsError as e:
            raise NativeError(str(e)) from None
