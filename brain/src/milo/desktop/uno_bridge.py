"""Data-only LibreOffice UNO bridge, compatible with the distro's Python 3.8+.

This file is intentionally standalone: bundled Python and distro python3-uno
need not share an ABI. No incoming string is evaluated as Python or a macro.
"""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

MAX_PACKET = 4 * 1024 * 1024
MAX_CELLS = 2000
SAFE_FORMULAS = frozenset((
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


class BridgeError(Exception):
    pass


class BridgeUnavailable(BridgeError):
    pass


def prop(name, value):
    import uno
    result = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    result.Name, result.Value = name, value
    return result


def _letters(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell(value):
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", value)
    if not match:
        raise BridgeError("Invalid spreadsheet range")
    column = 0
    for character in match.group(1):
        column = column * 26 + ord(character) - 64
    return column - 1, int(match.group(2)) - 1


def bounds(reference):
    parts = reference.split(":")
    if len(parts) > 2:
        raise BridgeError("Invalid spreadsheet range")
    left, top = _cell(parts[0])
    right, bottom = _cell(parts[-1])
    if right < left or bottom < top or right >= 16384 or bottom >= 1048576:
        raise BridgeError("That range is outside the spreadsheet")
    if (right - left + 1) * (bottom - top + 1) > MAX_CELLS:
        raise BridgeError("Use at most 2000 cells in one operation")
    return left, top, right, bottom


def reference(address):
    first = _letters(address[0] + 1) + str(address[1] + 1)
    last = _letters(address[2] + 1) + str(address[3] + 1)
    return first if first == last else first + ":" + last


def used_bounds(sheet):
    cursor = sheet.createCursor()
    cursor.gotoStartOfUsedArea(False)
    cursor.gotoEndOfUsedArea(True)
    area = cursor.getRangeAddress()
    result = (area.StartColumn, area.StartRow, area.EndColumn, area.EndRow)
    bounds(reference(result))
    return result


def selected(sheet, requested):
    area = bounds(requested) if requested else used_bounds(sheet)
    return sheet.getCellRangeByPosition(*area), area


def _supports(document, service):
    try:
        return document is not None and document.supportsService(service)
    except Exception:
        return False


def active_calc(desktop):
    service = "com.sun.star.sheet.SpreadsheetDocument"
    current = desktop.getCurrentComponent()
    if _supports(current, service):
        document = current
    else:
        enumeration = desktop.getComponents().createEnumeration()
        choices = []
        while enumeration.hasMoreElements():
            candidate = enumeration.nextElement()
            if _supports(candidate, service):
                choices.append(candidate)
        if len(choices) != 1:
            raise BridgeError("Bring the Calc workbook in Milo's LibreOffice instance to the front first.")
        document = choices[0]
    controller = document.getCurrentController()
    sheet = controller.getActiveSheet() if controller is not None else document.getSheets().getByIndex(0)
    return document, sheet


def _identity(document):
    try:
        identity = str(document.RuntimeUID)
    except Exception:
        identity = str(document.getURL())
    if not identity:
        raise BridgeError("Save this LibreOffice workbook before asking Milo to edit it.")
    return identity


def target(document, sheet, packet):
    cells, area = selected(sheet, packet.get("range", ""))
    values = [list(row) for row in cells.getDataArray()]
    formulas = [list(row) for row in cells.getFormulaArray()]
    styles = {}
    for name in ("CharWeight", "CellBackColor", "CharColor", "NumberFormat"):
        value = getattr(cells, name, None)
        styles[name] = value if isinstance(value, (str, int, float, bool)) or value is None else None
    try:
        title = str(document.getTitle())
    except Exception:
        title = str(document.Title)
    metadata = {"app": "LibreOffice Calc", "document": title, "sheet": str(sheet.getName()),
                "document_id": _identity(document), "range": reference(area),
                "filled": sum(value not in (None, "") for row in formulas for value in row)
                          if packet.get("has_rows") else 0}
    return metadata, {"values": values, "formulas": formulas, "styles": styles}


def calc_formula(value):
    """UNO uses English function names and semicolons between arguments."""
    result, quoted, index = [], False, 0
    while index < len(value):
        character = value[index]
        if character == '"':
            if quoted and index + 1 < len(value) and value[index + 1] == '"':
                result.append('""')
                index += 2
                continue
            quoted = not quoted
        result.append(";" if character == "," and not quoted else character)
        index += 1
    return "".join(result)


def formula_grid(rows, width):
    if not isinstance(rows, list) or not rows or len(rows) * width > MAX_CELLS:
        raise BridgeError("Invalid spreadsheet rows")
    output = []
    for row in rows:
        if not isinstance(row, list) or len(row) > width:
            raise BridgeError("Invalid spreadsheet row")
        values = []
        for index in range(width):
            value = row[index] if index < len(row) else None
            if value is None:
                values.append("")
            elif isinstance(value, bool):
                raise BridgeError("Spreadsheet cells must be text, numbers or null")
            elif isinstance(value, (int, float)):
                if not math.isfinite(value):
                    raise BridgeError("Spreadsheet numbers must be finite")
                values.append(str(value))
            elif isinstance(value, str):
                # Every non-formula string is literal, including +, -, @ and
                # apostrophes. The parent adapter validates formula functions.
                if value.startswith("="):
                    expression = re.sub(r'"(?:[^\"]|\"\")*"', '""', value)
                    functions = re.findall(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(", expression)
                    if ("|" in expression or "[" in expression or re.search(r"(?:file|https?|ftp):|'.*'\s*#", expression, re.I)
                            or any(name.upper() not in SAFE_FORMULAS for name in functions)):
                        raise BridgeError("External references, macros and executable spreadsheet formulas are unavailable")
                    values.append(calc_formula(value))
                else:
                    values.append("'" + value)
            else:
                raise BridgeError("Spreadsheet cells must be text, numbers or null")
        output.append(tuple(values))
    return tuple(output)


def apply_styles(document, sheet, styles):
    for style in styles:
        requested = style.get("range", "")
        if requested in ("sheet", "header"):
            area = used_bounds(sheet)
            if requested == "header":
                area = (area[0], area[1], area[2], area[1])
            cells = sheet.getCellRangeByPosition(*area)
        else:
            cells, _ = selected(sheet, requested)
        if style.get("bold"):
            cells.CharWeight = 150.0
        if "background" in style:
            cells.CellBackColor = int(style["background"])
        if "font_color" in style:
            cells.CharColor = int(style["font_color"])
        if "number_format" in style:
            import uno
            locale = uno.createUnoStruct("com.sun.star.lang.Locale")
            locale.Language, locale.Country = "en", "US"
            pattern = str(style["number_format"])
            formats = document.getNumberFormats()
            identity = formats.queryKey(pattern, locale, True)
            if identity < 0:
                identity = formats.addNew(pattern, locale)
            cells.NumberFormat = identity


def output_path(packet, suffix):
    home = Path(str(packet.get("home", ""))).resolve()
    folder = home / "work" / "created"
    path = Path(str(packet.get("path", ""))).absolute()
    if (path.parent != folder or path.suffix != suffix or path.exists() or
            (home / "work").is_symlink() or folder.is_symlink() or folder.resolve() != folder):
        raise BridgeError("The output must be a new file in Milo/work/created")
    folder.mkdir(parents=True, exist_ok=True)
    return path


def operation(packet, desktop, property_factory=prop):
    kind = packet.get("operation")
    if kind not in ("describe", "read", "write", "writer"):
        raise BridgeError("Unsupported Office operation")
    if kind == "writer":
        text = packet.get("text")
        if not isinstance(text, str) or len(text) > 100000:
            raise BridgeError("Invalid or oversized document text")
        path = output_path(packet, ".odt")
        document = desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0,
            (property_factory("Hidden", bool(packet.get("headless"))), property_factory("MacroExecutionMode", 0)))
        document.getText().setString(text)
        document.storeAsURL(path.as_uri(), (property_factory("FilterName", "writer8"), property_factory("Overwrite", False)))
        return {"document": path.name, "path": str(path), "opened": not packet.get("headless", False),
                "text": "Created a new document in Milo's LibreOffice Writer window."}
    if kind == "write" and packet.get("new"):
        path = output_path(packet, ".ods")
        document = desktop.loadComponentFromURL("private:factory/scalc", "_blank", 0,
            (property_factory("Hidden", bool(packet.get("headless"))), property_factory("MacroExecutionMode", 0)))
        sheet = document.getSheets().getByIndex(0)
    else:
        path = None
        document, sheet = active_calc(desktop)
    metadata, snapshot = ({}, {}) if kind == "write" and packet.get("new") else target(document, sheet, packet)
    if kind == "describe":
        return dict(metadata, snapshot=snapshot)
    if kind == "read":
        rows = []
        for values, formulas in zip(snapshot["values"], snapshot["formulas"]):
            rows.append([str(value) + " (" + formula + ")" if formula.startswith("=") else
                         "" if value is None else str(value) for value, formula in zip(values, formulas)])
        return dict(metadata, rows=rows, values=snapshot["values"], formulas=snapshot["formulas"], styles=snapshot["styles"])
    if not packet.get("new"):
        expected = packet.get("expected")
        if expected != {"target": metadata, "snapshot": snapshot}:
            raise BridgeError("The LibreOffice document, sheet or cells changed. Read the target again before writing.")
    if packet.get("rows"):
        cells, area = selected(sheet, packet.get("range", ""))
        grid = formula_grid(packet["rows"], area[2] - area[0] + 1)
        if len(grid) != area[3] - area[1] + 1:
            raise BridgeError("The rows do not match the target range")
        cells.setFormulaArray(grid)
    apply_styles(document, sheet, packet.get("styles", []))
    if path is not None:
        document.storeAsURL(path.as_uri(), (property_factory("FilterName", "calc8"), property_factory("Overwrite", False)))
    else:
        # Existing user edits stay unsaved, matching live Office behavior; Milo
        # never implicitly saves unrelated changes in an existing workbook.
        path = None
    try:
        controller = document.getCurrentController()
        if controller is not None and not packet.get("headless"):
            controller.getFrame().getContainerWindow().toFront()
    except Exception:
        pass
    result = {"document": str(document.getTitle()), "text": "Updated the requested cells and formatting in LibreOffice Calc."}
    if path is not None:
        result.update(path=str(path), opened=not packet.get("headless", False))
    return result


def connect(packet):
    try:
        import uno
    except ImportError:
        raise BridgeUnavailable("Install python3-uno for the system Python to enable live LibreOffice editing")
    pipe = packet.get("pipe", "")
    if not isinstance(pipe, str) or not re.fullmatch(r"milo-[a-f0-9]{48}", pipe):
        raise BridgeError("Invalid private LibreOffice connection")
    context = uno.getComponentContext()
    resolver = context.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", context)
    address = "uno:pipe,name=" + pipe + ";urp;StarOffice.ComponentContext"
    try:
        remote = resolver.resolve(address)
    except Exception:
        executable = str(packet.get("executable", ""))
        profile = str(packet.get("profile", ""))
        if Path(executable).name not in ("libreoffice", "soffice", "soffice.bin") or not profile.startswith("file://"):
            raise BridgeError("Invalid LibreOffice launch configuration")
        command = [executable, "--norestore", "--nodefault", "--nofirststartwizard",
                   "-env:UserInstallation=" + profile,
                   "--accept=pipe,name=" + pipe + ";urp;StarOffice.ServiceManager"]
        if packet.get("headless"):
            command.append("--headless")
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       start_new_session=True, close_fds=True)
        except OSError:
            raise BridgeUnavailable("LibreOffice could not be started")
        deadline = time.monotonic() + 8
        remote = None
        restarts = 0
        while time.monotonic() < deadline:
            try:
                remote = resolver.resolve(address)
                break
            except Exception:
                # The direct binary asks its launcher to restart after creating
                # a fresh profile. Normally oosplash handles exit81; replicate
                # only that documented bootstrap request, with a strict bound.
                if process.poll() == 81 and restarts < 2:
                    process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True, close_fds=True)
                    restarts += 1
                time.sleep(0.1)
        if remote is None:
            raise BridgeUnavailable("Milo's LibreOffice instance did not start. Check the desktop session and LibreOffice installation.")
    return remote.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", remote)


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_PACKET + 1)
        if len(raw) > MAX_PACKET:
            raise BridgeError("Office request is too large")
        packet = json.loads(raw)
        if not isinstance(packet, dict):
            raise BridgeError("Invalid Office request")
        desktop = connect(packet)
        result = operation(packet, desktop)
        answer = {"ok": True, "result": result}
    except Exception as error:
        answer = {"ok": False, "error": str(error) or "LibreOffice could not complete the operation",
                  "unavailable": isinstance(error, BridgeUnavailable)}
    sys.stdout.write(json.dumps(answer, ensure_ascii=False, allow_nan=False) + "\n")
    return 0 if answer["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
