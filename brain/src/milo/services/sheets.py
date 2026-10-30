"""Spreadsheets in Excel and Numbers through AppleScript that Milo writes himself.

The worker hands over the cells (`sheet_write`) or asks for them (`sheet_read`); this module turns that into
one tested AppleScript per step, which the app runs like any other script. Every value goes in as an
AppleScript literal (strings escaped, numbers as numbers), never pasted into the code, so a cell can't
become a command. Pure: building scripts and reading their output, no I/O.

A script prints `key<TAB>value` lines; `parse` reads them back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from milo.core.types import HandsError

EXCEL, NUMBERS = "Microsoft Excel", "Numbers"
APPS = (EXCEL, NUMBERS)
MAX_CELLS = 2000

_CELL = re.compile(r"^([A-Za-z]{1,3})([1-9][0-9]{0,6})$")
_RANGE = re.compile(r"^([A-Za-z]{1,3}[1-9][0-9]{0,6})(?::([A-Za-z]{1,3}[1-9][0-9]{0,6}))?$")


@dataclass(frozen=True)
class Block:
    """Where the cells go: `first` and `last` like "A1" and "B9"."""

    first: str
    last: str
    rows: int
    columns: int

    @property
    def range(self) -> str:
        return self.first if self.first == self.last else f"{self.first}:{self.last}"


def app_name(app: str) -> str:
    """"excel", "Microsoft Excel", "com.microsoft.Excel" -> "Microsoft Excel"; same for Numbers."""
    key = app.strip().lower().removesuffix(".app")
    if "excel" in key:
        return EXCEL
    if "numbers" in key:
        return NUMBERS
    raise HandsError(f"sheet tools work in Microsoft Excel and Numbers, not {app!r}.")


def column_number(letters: str) -> int:
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n


def column_letters(n: int) -> str:
    out = ""
    while n:
        n, rest = divmod(n - 1, 26)
        out = chr(65 + rest) + out
    return out


def cell(ref: str) -> tuple[int, int]:
    """"B3" -> (column 2, row 3). Raises HandsError."""
    m = _CELL.match(ref.strip())
    if not m:
        raise HandsError(f"{ref!r} is not a cell like A1 or C12.")
    return column_number(m.group(1)), int(m.group(2))


def check_range(ref: str) -> str:
    """"b2:b9" -> "B2:B9". Raises HandsError."""
    m = _RANGE.match(ref.strip())
    if not m:
        raise HandsError(f"{ref!r} is not a range like B2:B9.")
    return ref.strip().upper()


def block(rows: list, start: str = "A1") -> Block:
    """The block `rows` fill from `start`. Rows may be ragged; the block is as wide as the widest."""
    if not rows or not all(isinstance(r, list) for r in rows):
        raise HandsError("rows must be a list of rows, each a list of cells, like [[\"Day\", \"Budget\"]].")
    width = max(len(r) for r in rows)
    if width == 0:
        raise HandsError("rows are empty.")
    if len(rows) * width > MAX_CELLS:
        raise HandsError(f"That is more than {MAX_CELLS} cells; write it in parts.")
    for r in rows:
        for value in r:
            if isinstance(value, bool) or not isinstance(value, (str, int, float)) and value is not None:
                raise HandsError("Each cell must be text, a number or null.")
    col, row = cell(start)
    first = f"{column_letters(col)}{row}"
    last = f"{column_letters(col + width - 1)}{row + len(rows) - 1}"
    return Block(first, last, len(rows), width)


def literal(value: object) -> str:
    """A cell value as an AppleScript literal. Text is quoted and escaped; numbers stay numbers."""
    if value is None:
        return '""'
    if isinstance(value, bool):
        raise HandsError("Each cell must be text, a number or null.")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise HandsError("A cell can't be NaN or infinite.")
        return repr(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\r\n", "\n").replace("\r", "\n")
    # Literals sit inside an app's `tell`, where a bare `linefeed` could mean the app's own term.
    return '"' + text.replace("\n", '" & (AppleScript\'s linefeed) & "') + '"'


def _is_formula(value: object) -> bool:
    return isinstance(value, str) and value.startswith("=") and len(value) > 1


def _grid(rows: list, width: int, *, formulas: bool) -> str:
    """{{...}, {...}}: every row padded to `width`. Formula cells are left empty unless `formulas`."""
    out = []
    for r in rows:
        cells = [v if formulas or not _is_formula(v) else None for v in r] + [None] * (width - len(r))
        out.append("{" + ", ".join(literal(v) for v in cells) + "}")
    return "{" + ", ".join(out) + "}"


def _formula_cells(rows: list, start: str) -> list[tuple[str, str]]:
    col, row = cell(start)
    return [(f"{column_letters(col + j)}{row + i}", v) for i, r in enumerate(rows) for j, v in enumerate(r)
            if _is_formula(v)]


_EURO = {"at", "be", "cy", "de", "ee", "es", "fi", "fr", "gr", "hr", "ie", "it", "lt", "lu", "lv", "mt", "nl", "pt",
         "si", "sk"}
_MONEY = {"EUR": '#,##0.00 "€"', "USD": '"$"#,##0.00', "GBP": '"£"#,##0.00', "CHF": '"CHF" #,##0.00',
          "JPY": '"¥"#,##0', "SEK": '#,##0.00 "kr"', "DKK": '#,##0.00 "kr."', "NOK": '"kr" #,##0.00',
          "PLN": '#,##0.00 "zł"', "CAD": '"$"#,##0.00', "AUD": '"$"#,##0.00'}
_REGION_CURRENCY = {"us": "USD", "gb": "GBP", "ch": "CHF", "li": "CHF", "jp": "JPY", "se": "SEK", "dk": "DKK",
                    "no": "NOK", "pl": "PLN", "ca": "CAD", "au": "AUD"}


def currency(locale_id: str) -> str:
    """The currency of a macOS locale like "de_DE", "en_US@rg=dezzzz" or "en_DE@currency=EUR"; "" if unknown."""
    base, _, extras = locale_id.partition("@")
    options = dict(part.split("=", 1) for part in extras.split(";") if "=" in part)
    if options.get("currency"):
        return options["currency"].upper()
    region = (options.get("rg", "")[:2] or (base.split("_")[1] if "_" in base else "")).lower()
    return "EUR" if region in _EURO else _REGION_CURRENCY.get(region, "")


def excel_money(locale_id: str) -> str:
    """Excel's number format for money in the user's currency, two decimals."""
    return _MONEY.get(currency(locale_id), "#,##0.00")


def ranges(text: str) -> list[str]:
    """"A1:B1, A9:B9" -> ["A1:B1", "A9:B9"]. Raises HandsError."""
    return [check_range(r) for r in text.split(",") if r.strip()]

_RUNNING = 'if application "{app}" is not running then error "{app} isn\'t open."\n'


def describe_script(app: str, rows: list, start: str) -> str:
    """Which document a write would go into, and how many of its target cells already hold something."""
    b = block(rows, start)
    col, row = cell(b.first)
    last_col, last_row = col + b.columns - 1, row + b.rows - 1
    if app == EXCEL:
        return (_RUNNING.format(app=EXCEL)
                + 'tell application "Microsoft Excel"\n'
                + '  if (count of workbooks) is 0 then error "Excel has no workbook open."\n'
                + '  set ws to active sheet\n'
                + f'  set vals to value of range "{b.range}" of ws\n'
                + "  set docName to name of active workbook\n  set sheetName to name of ws\n"
                + "end tell\n"
                + _NAMES + _COUNT_FILLED)
    return (_RUNNING.format(app=NUMBERS)
            + 'tell application "Numbers"\n'
            + '  if (count of documents) is 0 then error "Numbers has no document open."\n'
            + '  set doc to front document\n'
            + '  tell table 1 of active sheet of doc\n'
            # Numbers refuses a range beyond the table, so only the part inside it is read.
            + f'    set r2 to {last_row}\n    if r2 > (row count) then set r2 to row count\n'
            + f'    set c2 to {last_col}\n    if c2 > (column count) then set c2 to column count\n'
            + f'    if r2 < {row} or c2 < {col} then\n      set vals to {{}}\n    else\n'
            + f'      set vals to value of every cell of range ((name of cell {col} of row {row}) & ":" & '
            + '(name of cell c2 of row r2))\n    end if\n'
            + "  end tell\n"
            + "  set docName to name of doc\n  set sheetName to name of active sheet of doc\n"
            + "end tell\n"
            + _NAMES + _COUNT_FILLED)


# Outside any `tell`: an app's own `tab` or `linefeed` would win inside one (Excel's `tab` did).
_NAMES = 'set out to "document" & tab & docName & linefeed & "sheet" & tab & sheetName\n'
_ADDRESS = 'set out to out & linefeed & "first" & tab & addr\n'

# Counts non-empty values in `vals` (a value, a list, or a list of lists) and prints the result.
_COUNT_FILLED = """\
set filled to 0
if class of vals is not list then set vals to {vals}
repeat with v in vals
  set v to contents of v
  if class of v is list then
    repeat with w in v
      set w to contents of w
      if w is not missing value and w is not "" then set filled to filled + 1
    end repeat
  else if v is not missing value and v is not "" then
    set filled to filled + 1
  end if
end repeat
return out & linefeed & "filled" & tab & filled
"""


# Each script brings the app to the front only at the end: `activate` on an app that isn't running yet makes it
# open its own blank document too, which nobody would close.


def write_script(app: str, rows: list, start: str = "A1", *, new_document: bool = False, header: bool = False,
                 bold: str = "", money: str = "", decimals: str = "", locale: str = "") -> str:
    """Fill the front sheet (of a new document if asked) with `rows` from `start`. Formula cells start with =.

    `bold`, `money` and `decimals` are ranges, several joined with commas. Money is in the currency of
    `locale` (the Mac's region, like "en_US@rg=dezzzz"), with two decimals.
    """
    b = block(rows, start)
    col, row = cell(b.first)
    bolds = ([f"{b.first}:{column_letters(col + b.columns - 1)}{row}"] if header else []) + ranges(bold)
    moneys, decimal_ranges = ranges(money), ranges(decimals)
    formulas = _formula_cells(rows, start)
    if app == EXCEL:
        lines = ['tell application "Microsoft Excel"']
        if new_document:
            lines.append("  set wb to make new workbook")
        else:
            lines += ['  if (count of workbooks) is 0 then error "Excel has no workbook open."',
                      "  set wb to active workbook"]
        lines += ["  set ws to active sheet of wb",
                  f'  set value of range "{b.range}" of ws to {_grid(rows, b.columns, formulas=False)}']
        lines += [f'  set formula of range "{ref}" of ws to {literal(f)}' for ref, f in formulas]
        lines += [f'  set bold of font object of range "{r}" of ws to true' for r in bolds]
        lines += [f'  set number format of range "{r}" of ws to {literal("0.00")}' for r in decimal_ranges]
        lines += [f'  set number format of range "{r}" of ws to {literal(excel_money(locale))}' for r in moneys]
        lines += [f'  autofit columns of range "{b.range}" of ws', "  activate",
                  "  set docName to name of wb", "  set sheetName to name of ws", "end tell"]
        return "\n".join(lines) + "\n" + _NAMES + "return out\n"
    lines = ['tell application "Numbers"']
    if new_document:
        lines = [_NUMBERS_STARTS, 'tell application "Numbers"',
                 "  if blankDoc is missing value then", "    set doc to make new document",
                 "  else", "    set doc to blankDoc", "  end if"]
    else:
        lines += ['  if (count of documents) is 0 then error "Numbers has no document open."',
                  "  set doc to front document"]
    lines += ["  tell table 1 of active sheet of doc",
              f"    if (row count) < {row + b.rows - 1} then set row count to {row + b.rows - 1}",
              f"    if (column count) < {col + b.columns - 1} then set column count to {col + b.columns - 1}"]
    if new_document:
        # A new table is bigger than the data: trim it, and keep a header row only if asked.
        lines += [f"    set row count to {row + b.rows - 1}", f"    set column count to {col + b.columns - 1}",
                  "    set header column count to 0", f"    set header row count to {1 if header else 0}",
                  "    set footer row count to 0"]
    for i, r in enumerate(rows):
        for j in range(b.columns):
            value = r[j] if j < len(r) else None
            if value is None and not new_document:
                continue
            lines.append(f'    set value of cell "{column_letters(col + j)}{row + i}" to {literal(value)}')
    # A new table's header row is bold already.
    lines += [f'    set font name of range "{r}" to "HelveticaNeue-Bold"' for r in bolds[1 if header and new_document
                                                                                          else 0:]]
    lines += [f'    set format of range "{r}" to number' for r in decimal_ranges]
    lines += [f'    set format of range "{r}" to currency' for r in moneys]
    lines += ["  end tell", "  activate", "  set docName to name of doc", "  set sheetName to name of active sheet of doc",
              "end tell"]
    return "\n".join(lines) + "\n" + _NAMES + "return out\n"


# Numbers opens a blank document of its own a few seconds after it starts. When the script is what starts it,
# that document is the new one: a second would stay open after Milo closes his. It counts only if it is the
# only document and empty, so a document Numbers brings back from last time is never written into.
_NUMBERS_STARTS = """\
set blankDoc to missing value
if application "Numbers" is not running then
  tell application "Numbers"
    repeat 80 times
      if (count of documents) > 0 then exit repeat
      delay 0.1
    end repeat
    if (count of documents) is 1 then
      set d to document 1
      set filled to false
      repeat with v in (value of every cell of table 1 of active sheet of d)
        if contents of v is not missing value then set filled to true
      end repeat
      if not filled then set blankDoc to d
    end if
  end tell
end if"""


def read_script(app: str, range: str = "") -> str:
    """The used cells of the front sheet (or `range`), one line per row, cells joined with tabs."""
    target = f'range "{check_range(range)}" of ws' if range else "used range of ws"
    if app == EXCEL:
        return (_RUNNING.format(app=EXCEL)
                + 'tell application "Microsoft Excel"\n'
                + '  if (count of workbooks) is 0 then error "Excel has no workbook open."\n'
                + "  set ws to active sheet\n"
                + f"  set r to {target}\n"
                + "  set vals to formula of r\n"
                + "  set docName to name of active workbook\n  set sheetName to name of ws\n"
                + "  set addr to get address of r without row absolute and column absolute\n"
                + "end tell\n"
                + _NAMES + _ADDRESS + _ROWS)
    target = f'range "{check_range(range)}"' if range else "cell range"
    return (_RUNNING.format(app=NUMBERS)
            + 'tell application "Numbers"\n'
            + '  if (count of documents) is 0 then error "Numbers has no document open."\n'
            + "  set doc to front document\n"
            + "  tell table 1 of active sheet of doc\n"
            + f"    set r to {target}\n"
            + "    set vals to {}\n"
            + "    repeat with rw in rows of r\n"
            + "      set end of vals to formatted value of every cell of rw\n"
            + "    end repeat\n"
            + "    set addr to name of r\n"
            + "  end tell\n"
            + "  set docName to name of doc\n  set sheetName to name of active sheet of doc\n"
            + "end tell\n"
            + _NAMES + _ADDRESS + _ROWS)


# Prints `vals` (a value, a row or rows) as "row<TAB>cell<TAB>cell" lines after `out`.
_ROWS = """\
if class of vals is not list then set vals to {{vals}}
if (count of vals) > 0 and class of item 1 of vals is not list then set vals to {vals}
set AppleScript's text item delimiters to tab
repeat with v in vals
  set cells to {}
  repeat with w in (contents of v)
    set w to contents of w
    if w is missing value then set w to ""
    set end of cells to (w as text)
  end repeat
  set out to out & linefeed & "row" & tab & (cells as text)
end repeat
set AppleScript's text item delimiters to ""
return out
"""


def parse(text: str) -> dict:
    """`key<TAB>value` lines into a dict; `row` lines into a list under "rows"."""
    out: dict = {"rows": []}
    for line in text.splitlines():
        key, _, value = line.partition("\t")
        if key == "row":
            out["rows"].append(value.split("\t"))
        elif key:
            out[key] = value
    return out


def table_text(parsed: dict) -> str:
    """The rows read back, with column letters and row numbers, for the worker."""
    rows = parsed.get("rows", [])
    first = str(parsed.get("first", "A1")).split(":")[0].replace("$", "") or "A1"
    try:
        col, row = cell(first)
    except HandsError:
        col, row = 1, 1
    while rows and not any(c.strip() for c in rows[-1]):
        rows = rows[:-1]
    if not rows:
        return "The sheet is empty."
    width = max(len(r) for r in rows)
    lines = ["#\t" + "\t".join(column_letters(col + j) for j in range(width))]
    lines += [f"{row + i}\t" + "\t".join(r) for i, r in enumerate(rows)]
    return "\n".join(lines)
