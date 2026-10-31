"""The AppleScripts Milo writes for Excel and Numbers: values go in as literals, never as code."""

import pytest

from milo.core.types import HandsError
from milo.services import documents, sheets
from milo.services.sheets import EXCEL, NUMBERS, block, literal, parse, read_script, table_text, write_script

WEEK = [["Day", "Budget"]] + [[d, 214.29] for d in ("Mon", "Tue")] + [["Total", "=SUM(B2:B3)"]]


def test_values_become_literals_that_cannot_break_out_of_their_string():
    assert literal('say "hi" \\ bye') == '"say \\"hi\\" \\\\ bye"'
    assert literal("two\nlines") == '"two" & (AppleScript\'s linefeed) & "lines"'
    assert literal(3) == "3" and literal(214.29) == "214.29" and literal(None) == '""'
    attack = '" & (do shell script "rm -rf ~") & "'
    script = write_script(EXCEL, [[attack]], new_document=True)
    assert '{{"\\" & (do shell script \\"rm -rf ~\\") & \\""}}' in script


@pytest.mark.parametrize("bad", [True, {"a": 1}, float("nan")])
def test_odd_cells_are_refused(bad):
    with pytest.raises(HandsError):
        write_script(NUMBERS, [[bad]])


def test_the_block_from_a_start_cell():
    assert block(WEEK).range == "A1:B4"
    assert block([[1, 2, 3]], "Z9").range == "Z9:AB9"
    assert block([[1]], "C3").range == "C3"
    with pytest.raises(HandsError):
        block([[1]], "A0")
    with pytest.raises(HandsError):
        block([[0] * 100] * 30)


def test_excel_writes_values_in_one_go_then_formulas_header_and_money():
    script = write_script(EXCEL, WEEK, new_document=True, header=True, money="b2:b4", bold="A4:B4",
                          decimals="C1, D1", locale="en_US@rg=dezzzz")
    assert "set wb to make new workbook" in script
    assert ('set value of range "A1:B4" of ws to {{"Day", "Budget"}, {"Mon", 214.29}, {"Tue", 214.29}, '
            '{"Total", ""}}') in script
    assert 'set formula of range "B4" of ws to "=SUM(B2:B3)"' in script
    assert 'set bold of font object of range "A1:B1" of ws to true' in script
    assert 'set bold of font object of range "A4:B4" of ws to true' in script
    assert 'set number format of range "D1" of ws to "0.00"' in script
    assert 'set number format of range "B2:B4" of ws to "#,##0.00 \\"€\\""' in script
    assert "make new" not in write_script(EXCEL, WEEK)


def test_numbers_trims_a_new_table_to_the_data_and_sets_each_cell():
    script = write_script(NUMBERS, WEEK, new_document=True, header=True, money="B2:B4")
    assert "set doc to make new document" in script
    assert "set row count to 4" in script and "set column count to 2" in script
    assert "set header row count to 1" in script
    assert 'set value of cell "B4" to "=SUM(B2:B3)"' in script
    assert 'set format of range "B2:B4" to currency' in script


def test_read_and_parse():
    assert "used range of ws" in read_script(EXCEL)
    assert 'range "A1:C9"' in read_script(NUMBERS, "a1:c9")
    parsed = parse("document\tBook1\nfirst\tB2:C3\nrow\t1\t2\nrow\t\t\n")
    assert parsed["document"] == "Book1" and parsed["rows"] == [["1", "2"], ["", ""]]
    assert table_text(parsed) == "#\tB\tC\n2\t1\t2"
    assert table_text(parse("first\tA1\nrow\t")) == "The sheet is empty."


def test_app_names():
    assert sheets.app_name("excel") == EXCEL and sheets.app_name("com.apple.iWork.Numbers") == NUMBERS
    with pytest.raises(HandsError):
        sheets.app_name("Pages")


@pytest.mark.parametrize("locale, money", [
    ("en_US@rg=dezzzz", '#,##0.00 "€"'), ("de_DE", '#,##0.00 "€"'), ("en_US", '"$"#,##0.00'),
    ("en_GB", '"£"#,##0.00'), ("de_CH", '"CHF" #,##0.00'), ("en_DE@currency=USD", '"$"#,##0.00'),
    ("", "#,##0.00"), ("xx", "#,##0.00")])
def test_money_is_in_the_currency_of_the_macs_region(locale, money):
    assert sheets.excel_money(locale) == money


def _inside_tell(script: str) -> list[str]:
    depth, inside = 0, []
    for line in script.splitlines():
        words = line.split()
        if words[:2] == ["end", "tell"]:
            depth -= 1
        elif words[:1] == ["tell"]:
            depth += 1
        elif depth:
            inside.append(line)
    return inside


@pytest.mark.parametrize("script", [
    write_script(EXCEL, WEEK, new_document=True), write_script(NUMBERS, WEEK, new_document=True),
    sheets.describe_script(EXCEL, WEEK, "A1"), sheets.describe_script(NUMBERS, WEEK, "A1"),
    read_script(EXCEL), read_script(NUMBERS), documents.write_script("TextEdit", "two\nlines"),
    documents.write_script("Pages", "hi")])
def test_tab_and_linefeed_are_never_said_to_an_app(script):
    # Inside `tell application "Microsoft Excel"`, `tab` is Excel's and the document name came back empty.
    import re
    said = [line for line in _inside_tell(script) if re.search(r"(?<!AppleScript's )\b(tab|linefeed)\b", line)]
    assert said == []


@pytest.mark.parametrize("script", [
    write_script(EXCEL, WEEK, new_document=True), write_script(NUMBERS, WEEK, new_document=True),
    documents.write_script("TextEdit", "hi"), documents.write_script("Pages", "hi")])
def test_the_app_comes_to_the_front_only_after_the_new_document_is_made(script):
    assert script.index("make new") < script.index("activate")


# ---- colours (ADR 0032)


def test_colours_are_named_or_hex_in_english_or_german():
    assert sheets.colours("A1:D1 blue, sheet light green") == [("A1:D1", (0, 112, 192)), ("sheet", (146, 208, 80))]
    assert sheets.colours("header rot") == [("header", (255, 0, 0))]
    assert sheets.colours("b2:b9 #FFCC00") == [("B2:B9", (255, 204, 0))]
    for bad in ("A1 blurple", "everything red", "A1:B2"):
        with pytest.raises(HandsError):
            sheets.colours(bad)


def test_the_whole_sheet_is_its_used_range_never_every_cell():
    script = write_script(EXCEL, [], fill="sheet red", font_color="sheet white")
    assert "set color of interior object of (used range of ws) to {255, 0, 0}" in script
    assert "set color of font object of (used range of ws) to {255, 255, 255}" in script
    assert "XFD" not in script and "set value of" not in script, "no cells are written"


def test_the_header_is_the_first_row_of_what_is_used():
    script = write_script(EXCEL, [], fill="header blue")
    assert "set color of interior object of (row 1 of (used range of ws)) to {0, 112, 192}" in script
    numbers = write_script(NUMBERS, [], fill="header blue, A2:B3 yellow", font_color="sheet black")
    assert "set background color of row 1 to {0, 28784, 49344}" in numbers
    assert 'set background color of range "A2:B3" to {65535, 65535, 0}' in numbers
    assert "set text color of cell range to {0, 0, 0}" in numbers


def test_cells_and_colours_go_in_one_call():
    script = write_script(EXCEL, WEEK, new_document=True, header=True, fill="A1:B1 blue")
    assert script.index("set value of") < script.index("interior object") < script.index("activate")


def test_a_write_with_nothing_to_do_is_refused():
    with pytest.raises(HandsError, match="rows or a colour"):
        write_script(EXCEL, [])


@pytest.mark.parametrize("script", [write_script(EXCEL, [], fill="sheet red"),
                                    write_script(NUMBERS, [], font_color="header blue"),
                                    sheets.describe_script(EXCEL, [], "A1"), sheets.describe_script(NUMBERS, [], "A1")])
def test_colour_scripts_never_say_tab_or_linefeed_to_an_app(script):
    import re
    assert [line for line in _inside_tell(script) if re.search(r"(?<!AppleScript's )\b(tab|linefeed)\b", line)] == []
