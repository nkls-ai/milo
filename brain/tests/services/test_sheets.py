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
    # activate on an app that isn't running opened a blank Numbers document of its own, left open after cleanup.
    assert script.index("make new") < script.index("activate")
