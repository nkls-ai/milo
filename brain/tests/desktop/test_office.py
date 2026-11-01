from types import SimpleNamespace

import pytest

from milo.desktop._native_types import NativeError
from milo.desktop._office import OfficeTools, OfficeUnavailable, PortableOffice, WindowsOffice, _validate


class Selection:
    def __init__(self):
        self.Rows = SimpleNamespace(Count=2)
        self.Columns = SimpleNamespace(Count=2)
        self.Address = "$A$1:$B$2"
        self.Value2 = (("Name", "Amount"), ("Rent", 950))
        self.Formula = (("Name", "Amount"), ("Rent", "=SUM(B3:B9)"))
        self.Font = SimpleNamespace(Bold=False, Color=None)
        self.Interior = SimpleNamespace(Color=None)
        self.NumberFormat = "General"


@pytest.fixture
def excel():
    selections = {}
    sheet = SimpleNamespace(Name="Budget", Range=lambda ref: selections.setdefault(ref, Selection()))
    sheet.UsedRange = Selection()
    book = SimpleNamespace(Name="Budget.xlsx", FullName="C:/Documents/Budget.xlsx", Activate=lambda: None)
    app = SimpleNamespace(ActiveWorkbook=book, ActiveSheet=sheet, Visible=False)
    created = []

    def add():
        created.append(True)
        return book

    app.Workbooks = SimpleNamespace(Add=add)
    return SimpleNamespace(app=app, ranges=selections, created=created,
                           call=lambda program, create, operation: operation(app))


def test_excel_describe_reads_target_and_write_is_one_grid_assignment(excel):
    office = WindowsOffice(excel.call)
    args = {"app": "Microsoft Excel", "rows": [["Name", "Amount"], ["Rent", "=SUM(B3:B9)"]],
            "header": True, "money": "B2", "fill": "A1:B1 blue", "font_color": "A1:B1 white"}
    description = office.describe("sheet_write", args)
    assert description["document"] == "Budget.xlsx" and description["filled"] == 4
    assert "fingerprint" in description
    result = office.run("sheet_write", args)
    assert result["document"] == "Budget.xlsx"
    assert excel.ranges["A1:B2"].Formula == (("'Name", "'Amount"), ("'Rent", "=SUM(B3:B9)"))
    assert excel.ranges["A1:B1"].Font.Bold
    assert excel.ranges["A1:B1"].Interior.Color == 0 | (112 << 8) | (192 << 16)
    assert excel.ranges["A1:B1"].Font.Color == 0xFFFFFF
    assert excel.app.Visible and not excel.created


def test_changed_excel_target_is_rejected_before_any_values_are_written(excel):
    office = WindowsOffice(excel.call)
    args = {"app": "Microsoft Excel", "rows": [["New"]]}
    office.describe("sheet_write", args)
    excel.app.ActiveWorkbook = SimpleNamespace(Name="Other.xlsx", FullName="C:/Other.xlsx")
    with pytest.raises(NativeError, match="target changed"):
        office.run("sheet_write", args)
    assert excel.ranges["A1"].Formula[0][0] == "Name"


def test_existing_excel_edit_requires_description(excel):
    with pytest.raises(NativeError, match="target changed"):
        WindowsOffice(excel.call).run("sheet_write", {"app": "Microsoft Excel", "rows": [[1]]})


def test_formula_with_an_empty_display_still_counts_as_a_populated_cell(excel):
    selected = excel.app.ActiveSheet.Range("A1")
    selected.Value2, selected.Formula = "", '=IF(B1=0,"",B1)'
    target = WindowsOffice(excel.call).describe("sheet_write", {"app": "Microsoft Excel", "rows": [[1]]})
    assert target["filled"] == 1


def test_new_excel_document_and_read_preserve_formula_text(excel):
    office = WindowsOffice(excel.call)
    args = {"app": "Microsoft Excel", "rows": [[1, 2]], "new_document": True}
    assert office.describe("sheet_write", args)["new"]
    office.run("sheet_write", args)
    assert excel.created == [True]
    read = office.run("sheet_read", {"app": "Microsoft Excel", "range": "A1:B2"})
    assert "=SUM(B3:B9)" in read["text"] and read["text"].startswith("#\tA\tB")


def test_word_creation_only_creates_a_new_document_with_literal_text():
    content = SimpleNamespace(Text="")
    document = SimpleNamespace(Name="Document1", Content=content, Activate=lambda: None)
    app = SimpleNamespace(Documents=SimpleNamespace(Add=lambda: document), Visible=False)
    calls = []

    def gateway(program, create, operation):
        calls.append((program, create))
        return operation(app)

    result = WindowsOffice(gateway).run("write_document", {"app": "Microsoft Word", "text": "Hello\nWorld"})
    assert content.Text == "Hello\nWorld" and app.Visible
    assert result["document"] == "Document1" and calls == [("Word.Application", True)]


@pytest.mark.parametrize("formula", ["=WEBSERVICE(\"https://example.test\")", "=cmd|'/C calc'!A0",
                                    "='[external.xlsx]Sheet1'!A1", "=HYPERLINK(\"file:///x\")"])
def test_external_and_executable_formulas_are_refused(formula):
    with pytest.raises(NativeError, match="External data"):
        _validate({"rows": [[formula]]})


def test_custom_executable_functions_are_refused_but_quoted_text_is_literal():
    with pytest.raises(NativeError, match="outside Milo's supported"):
        _validate({"rows": [["=CustomMacro(A1)"]]})
    assert _validate({"rows": [['=IF(A1=1,"CustomMacro()",SUM(B2:B9))']]})


def test_portable_spreadsheet_is_a_real_formatted_xlsx_and_never_overwrites(tmp_path):
    from openpyxl import load_workbook

    opened = []
    office = PortableOffice(tmp_path, lambda path, app: opened.append((path, app)) or True)
    args = {"app": "LibreOffice Calc", "rows": [["Item", "Amount"], ["Rent", 950], ["Total", "=SUM(B2:B2)"]],
            "new_document": True, "header": True, "bold": "A3:B3", "money": "B2:B3", "locale": "de_DE",
            "fill": "A1:B1 blue", "font_color": "A1:B1 white"}
    result = office.run("sheet_write", args)
    book = load_workbook(result["path"])
    sheet = book.active
    assert sheet["A1"].value == "Item" and sheet["B2"].value == 950
    assert sheet["B3"].value == "=SUM(B2:B2)" and sheet["A1"].font.bold and sheet["B3"].font.bold
    assert sheet["A1"].fill.fgColor.rgb.endswith("0070C0")
    assert "€" in sheet["B2"].number_format
    assert opened and result["opened"] and result["document"].endswith(".xlsx")
    second = office.run("sheet_write", args)
    assert second["path"] != result["path"]


def test_portable_document_is_a_real_docx_and_reports_opening_failure(tmp_path):
    from docx import Document

    office = PortableOffice(tmp_path, lambda path, app: False)
    result = office.run("write_document", {"app": "LibreOffice Writer", "text": "Hello\nWorld"})
    assert [p.text for p in Document(result["path"]).paragraphs] == ["Hello", "World"]
    assert not result["opened"] and "Open this file" in result["text"]


def test_new_document_publication_never_overwrites_an_existing_file(tmp_path):
    path = tmp_path / "existing.docx"
    path.write_bytes(b"user document")
    with pytest.raises(FileExistsError):
        PortableOffice._save(SimpleNamespace(save=lambda output: output.write(b"new document")), path)
    assert path.read_bytes() == b"user document"


def test_failed_document_output_never_appears_as_a_complete_document(tmp_path):
    path = tmp_path / "new.docx"

    def interrupted(output):
        output.write(b"partial ZIP")
        raise OSError("write interrupted")

    with pytest.raises(OSError, match="interrupted"):
        PortableOffice._save(SimpleNamespace(save=interrupted), path)
    assert not path.exists()


def test_linux_does_not_pretend_to_edit_an_existing_spreadsheet(tmp_path):
    class Unavailable:
        def describe(self, tool, args):
            raise OfficeUnavailable("Live spreadsheet editing unavailable")

        run = describe

    office = OfficeTools(tmp_path, platform="linux", linux=Unavailable())
    with pytest.raises(NativeError, match="Live spreadsheet editing"):
        office.describe("sheet_write", {"app": "LibreOffice Calc", "rows": [[1]]})
    with pytest.raises(NativeError, match="Live spreadsheet editing"):
        office.run("sheet_read", {"app": "LibreOffice Calc"})
