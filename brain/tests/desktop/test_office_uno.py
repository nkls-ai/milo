"""Pure UNO boundary tests; no installed LibreOffice or desktop is required."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from milo.desktop._native_types import NativeError
from milo.desktop._office import OfficeUnavailable, _FORMULA_FUNCTIONS
from milo.desktop._office_uno import LibreOffice
from milo.desktop import uno_bridge as bridge


class Cells:
    def __init__(self, sheet, area):
        object.__setattr__(self, "sheet", sheet)
        object.__setattr__(self, "area", area)

    def getFormulaArray(self):
        x, y, right, bottom = self.area
        return tuple(tuple(str(self.sheet.data.get((column, row), "")) for column in range(x, right + 1))
                     for row in range(y, bottom + 1))

    def getDataArray(self):
        return self.getFormulaArray()

    def setFormulaArray(self, rows):
        self.sheet.writes += 1
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                self.sheet.data[(self.area[0] + column_index, self.area[1] + row_index)] = value.removeprefix("'")

    def __setattr__(self, name, value):
        self.sheet.styles[(self.area, name)] = value

    def __getattr__(self, name):
        return self.sheet.styles.get((self.area, name), 0)


class Sheet:
    def __init__(self):
        self.data, self.styles, self.writes = {(0, 0): "old", (1, 0): "2"}, {}, 0

    def getName(self):
        return "Budget"

    def getCellRangeByPosition(self, *area):
        return Cells(self, area)

    def createCursor(self):
        return SimpleNamespace(gotoStartOfUsedArea=lambda *_: None, gotoEndOfUsedArea=lambda *_: None,
            getRangeAddress=lambda: SimpleNamespace(StartColumn=0, StartRow=0, EndColumn=1, EndRow=0))


class Document:
    RuntimeUID = "document-one"

    def __init__(self):
        self.sheet = Sheet()
        self.saved = None
        self.text = ""

    def supportsService(self, name):
        return name == "com.sun.star.sheet.SpreadsheetDocument"

    def getTitle(self):
        return "Budget.ods"

    def getCurrentController(self):
        return SimpleNamespace(getActiveSheet=lambda: self.sheet)

    def getSheets(self):
        return SimpleNamespace(getByIndex=lambda _: self.sheet)

    def getText(self):
        return SimpleNamespace(setString=lambda value: setattr(self, "text", value))

    def storeAsURL(self, url, properties):
        self.saved = (url, {item.Name: item.Value for item in properties})


class Desktop:
    def __init__(self):
        self.document = Document()
        self.loaded = []

    def getCurrentComponent(self):
        return self.document

    def loadComponentFromURL(self, url, target, flags, properties):
        self.loaded.append((url, {item.Name: item.Value for item in properties}))
        self.document = Document()
        return self.document


def property_value(name, value):
    return SimpleNamespace(Name=name, Value=value)


def test_bridge_formula_allowlist_stays_in_step_with_parent_validator():
    # The standalone script runs under distro Python and cannot import Milo's
    # newer-Python package. This data equality check prevents policy drift.
    assert bridge.SAFE_FORMULAS == _FORMULA_FUNCTIONS


def test_bulk_formula_grid_keeps_literal_text_and_translates_only_argument_commas():
    grid = bridge.formula_grid([["+literal", "-literal", "@literal", "0012", "=SUM(1,2)", '=IF(A1="a,b",1,2)']], 6)
    assert grid == (("'+literal", "'-literal", "'@literal", "'0012", "=SUM(1;2)", '=IF(A1="a,b";1;2)'),)
    for formula in ("=WEBSERVICE(\"https://example.com\")", "=MYMACRO()", "='file:///tmp/a.ods'#$Sheet1.A1", "=[other.xlsx]A1"):
        with pytest.raises(bridge.BridgeError):
            bridge.formula_grid([[formula]], 1)


def test_live_adapter_describes_and_writes_once_with_stale_target_refusal(tmp_path):
    desktop = Desktop()
    def transport(packet):
        return bridge.operation(packet, desktop, property_value)
    office = LibreOffice(tmp_path, transport=transport)
    args = {"app": "LibreOffice Calc", "rows": [["new", 42]], "start": "A1", "bold": "A1:B1"}
    description = office.describe("sheet_write", args)
    assert description["filled"] == 2 and description["fingerprint"]
    desktop.document.sheet.data[(0, 0)] = "user changed this"
    with pytest.raises(bridge.BridgeError, match="changed"):
        office.run("sheet_write", args)
    assert desktop.document.sheet.writes == 0
    office.describe("sheet_write", args)
    office.run("sheet_write", args)
    assert desktop.document.sheet.writes == 1
    assert desktop.document.sheet.data[(0, 0)] == "new"
    assert desktop.document.sheet.styles[((0, 0, 1, 0), "CharWeight")] == 150.0
    with pytest.raises(NativeError, match="Read.*again"):
        office.run("sheet_write", args)


def test_same_cells_in_a_different_document_do_not_pass_the_target_guard(tmp_path):
    desktop = Desktop()
    office = LibreOffice(tmp_path, transport=lambda packet: bridge.operation(packet, desktop, property_value))
    args = {"app": "LibreOffice Calc", "rows": [["new"]]}
    office.describe("sheet_write", args)
    desktop.document.RuntimeUID = "another-document"
    with pytest.raises(bridge.BridgeError, match="changed"):
        office.run("sheet_write", args)
    assert desktop.document.sheet.writes == 0


def test_new_writer_document_disables_macros_and_saves_unicode_to_managed_path(tmp_path):
    desktop = Desktop()
    office = LibreOffice(tmp_path, transport=lambda packet: bridge.operation({"home": str(tmp_path), **packet}, desktop, property_value))
    text = "Grüße, Milo.\n日本語 and emojis 🐦"
    result = office.run("write_document", {"app": "LibreOffice Writer", "text": text})
    assert desktop.document.text == text
    assert desktop.loaded[0][1]["MacroExecutionMode"] == 0
    assert desktop.document.saved[1] == {"FilterName": "writer8", "Overwrite": False}
    assert result["path"].endswith(".odt")


def test_unsupported_apps_and_dangerous_formulas_never_connect(tmp_path):
    calls = []
    office = LibreOffice(tmp_path, transport=lambda packet: calls.append(packet))
    with pytest.raises(OfficeUnavailable):
        office.run("write_document", {"app": "TextEdit", "text": "hello"})
    with pytest.raises(NativeError):
        office.describe("sheet_write", {"app": "LibreOffice Calc", "new_document": True, "rows": [["=MYMACRO()"]]})
    assert calls == []


def test_bridge_rejects_oversized_ranges_and_output_replacement(tmp_path):
    with pytest.raises(bridge.BridgeError, match="2000"):
        bridge.bounds("A1:Z1000")
    folder = tmp_path / "work/created"
    folder.mkdir(parents=True)
    existing = folder / "existing.ods"
    existing.write_text("keep me", encoding="utf-8")
    with pytest.raises(bridge.BridgeError, match="new file"):
        bridge.output_path({"home": str(tmp_path), "path": str(existing)}, ".ods")
    assert existing.read_text(encoding="utf-8") == "keep me"
