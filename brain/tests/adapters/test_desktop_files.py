"""The real portable Files adapter: filesystem policies and document readers, no models."""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from milo.adapters.connect import _portable_text
from milo.adapters.connect.desktop import LocalFiles, _desktop
from milo.core.control import Protected
from milo.core.ports import Files
from milo.core.registry import AdapterContext, ConfigError
from milo.core.types import ToolError
from tests.fakes import FakeClock


@pytest.fixture(autouse=True)
def _home_outside_temp(tmp_path_factory, monkeypatch):
    # Windows keeps pytest's temp folders in ~/AppData, which the Files policy rightly refuses.
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))


def put(root: Path, name: str, text: str = "hello") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def archive(path: Path, **entries) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, text in entries.items():
            output.writestr(name, text)
    return path


def test_factory_offers_real_files_without_pretending_other_connections_exist(tmp_path):
    home = tmp_path / "Milo"
    context = AdapterContext(home, home / "state", FakeClock())
    result = _desktop({"files_scope": str(tmp_path)}, context)
    assert isinstance(result.files, Files)
    assert result.calendar is None and result.reminders is None and result.mail is None
    assert result.notes is None and result.contacts is None
    with pytest.raises(ConfigError, match="files_scope"):
        _desktop({"files_scope": 42}, context)
    with pytest.raises(ConfigError, match="unknown"):
        _desktop({"invented": True}, context)


def test_find_search_and_listing_are_newest_first_and_case_insensitive(tmp_path):
    old = put(tmp_path, "Invoices/older invoice.txt", "Bananas and apples")
    new = put(tmp_path, "Invoices/New invoice.txt", "Bananas with pears")
    os.utime(old, (100, 100))
    os.utime(new, (200, 200))
    files = LocalFiles(tmp_path)
    assert [item["name"] for item in files.find("INVOICE")] == [new.name, old.name]
    assert [item["name"] for item in files.search("BANANAS pears")] == [new.name]
    assert [item["name"] for item in files.list("Invoices", "invoice", limit=1)] == [new.name]
    assert files.search("") == [] and files.find("", limit=0) == []


def test_walk_never_enters_private_hidden_protected_or_linked_directories(tmp_path, monkeypatch):
    from milo.adapters.connect import desktop

    visible = put(tmp_path, "Documents/visible.txt", "needle")
    for name in (".hidden/key.txt", "AppData/key.txt", "Library/key.txt", "node_modules/key.txt",
                 "Milo/secrets/key.txt", "Milo/config.toml"):
        put(tmp_path, name, "needle")
    (tmp_path / "Alias").symlink_to(tmp_path / "Documents", target_is_directory=True)
    original = os.scandir
    entered = []
    def record(path):
        entered.append(Path(path).name)
        return original(path)
    monkeypatch.setattr(desktop.os, "scandir", record)
    files = LocalFiles(tmp_path, Protected(tmp_path / "Milo"))
    assert [item["path"] for item in files.search("needle")] == [str(visible)]
    assert not set(entered) & {".hidden", "AppData", "Library", "node_modules", "secrets", "Alias"}
    for path in ("AppData/key.txt", "Library/key.txt", ".hidden/key.txt", "Alias/visible.txt"):
        with pytest.raises(ToolError):
            files.read(path)
    with pytest.raises(ToolError, match="Milo's own"):
        files.read("Milo/config.toml")


def test_outside_scope_and_private_destinations_are_refused(tmp_path):
    root = tmp_path / "scope"
    root.mkdir()
    put(tmp_path, "outside.txt")
    put(root, "document.txt")
    files = LocalFiles(root)
    with pytest.raises(ToolError, match="outside"):
        files.read(str(tmp_path / "outside.txt"))
    with pytest.raises(ToolError, match="outside"):
        files.move(["document.txt"], "AppData/archive")
    assert (root / "document.txt").exists() and not (root / "AppData").exists()


def test_search_budget_is_bounded_and_large_or_unsupported_files_are_skipped(tmp_path, monkeypatch):
    for index in range(30):
        put(tmp_path, f"file-{index}.txt", "needle")
    files = LocalFiles(tmp_path, max_entries=5)
    assert len(files.find("file-")) <= 5
    huge = put(tmp_path, "large.txt", "x" * 200)
    monkeypatch.setattr(_portable_text, "MAX_FILE_BYTES", 100)
    with pytest.raises(ToolError, match="too large"):
        files.read(str(huge))
    unsupported = put(tmp_path, "legacy.doc", "binary")
    with pytest.raises(ToolError, match="Save an older office"):
        files.read(str(unsupported))


def test_read_and_move_use_the_shared_file_contract_and_never_replace(tmp_path):
    source = put(tmp_path, "report.txt", "hello world")
    files = LocalFiles(tmp_path)
    assert files.read("report.txt", 5) == {"path": str(source), "name": "report.txt", "text": "hello", "truncated": True}
    moved = files.move(["report.txt"], "Archive")
    assert Path(moved["moved"][0]["path"]).read_text(encoding="utf-8") == "hello world"
    put(tmp_path, "report.txt", "another")
    with pytest.raises(ToolError, match="already a file"):
        files.move(["report.txt"], "Archive")
    assert (tmp_path / "report.txt").read_text(encoding="utf-8") == "another"
    assert (tmp_path / "Archive/report.txt").read_text(encoding="utf-8") == "hello world"


def test_invalid_lengths_fail_instead_of_negative_slicing(tmp_path):
    put(tmp_path, "report.txt")
    files = LocalFiles(tmp_path)
    for length in (-1, 0, True, "20"):
        with pytest.raises(ToolError, match="positive"):
            files.read("report.txt", length)
    with pytest.raises(ToolError, match="positive"):
        files.find("", -1)


def test_shared_move_policy_refuses_home_cloud_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    put(tmp_path, "report.txt")
    files = LocalFiles(tmp_path)
    with pytest.raises(ToolError, match="shared or synced"):
        files.move(["report.txt"], "OneDrive - Work")


def test_docx_and_odt_are_read_without_office_programs(tmp_path):
    docx = archive(tmp_path / "letter.docx", **{"word/document.xml":
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        '<w:p><w:r><w:t>Hello Milo</w:t><w:tab/><w:t>one</w:t><w:br/><w:t>two</w:t></w:r></w:p>'
        '</w:body></w:document>'})
    odt = archive(tmp_path / "notes.odt", **{"content.xml":
        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
        '<text:p>Hello <text:span>Milo</text:span><text:s text:c="2"/>one<text:line-break/>two</text:p>'
        '</office:text></office:body></office:document-content>'})
    files = LocalFiles(tmp_path)
    assert "Hello Milo\tone\ntwo" in files.read(str(docx))["text"]
    assert "Hello Milo  one\ntwo" in files.read(str(odt))["text"]
    short = files.read(str(docx), 5)
    assert short["text"] == "Hello" and short["truncated"]


def test_html_strips_scripts_styles_and_tags_and_decodes_entities(tmp_path):
    path = put(tmp_path, "page.html", '<html><head><style>hidden</style></head><body><h1>Title</h1>'
        '<p>Hello <b>Milo</b> &amp; friends.</p><script>send_secrets()</script></body></html>')
    text = LocalFiles(tmp_path).read(str(path))["text"]
    assert "Hello Milo & friends." in text and "Title" in text
    assert "send_secrets" not in text and "hidden" not in text and "<b>" not in text


def test_zip_xml_limits_and_entities_fail_cleanly(tmp_path, monkeypatch):
    files = LocalFiles(tmp_path)
    broken = put(tmp_path, "broken.docx", "not a zip")
    with pytest.raises(ToolError, match="damaged"):
        files.read(str(broken))
    entity = archive(tmp_path / "entity.docx", **{"word/document.xml":
        '<!DOCTYPE a [<!ENTITY steal SYSTEM "file:///does-not-exist">]><a>&steal;</a>'})
    with pytest.raises(ToolError, match="XML declarations"):
        files.read(str(entity))
    monkeypatch.setattr(_portable_text, "MAX_ARCHIVE_BYTES", 10)
    oversized = archive(tmp_path / "large.odt", **{"content.xml": "x" * 100})
    with pytest.raises(ToolError, match="too large"):
        files.read(str(oversized))


def test_pdf_reader_extracts_text_and_refuses_scanned_pages(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import (DecodedStreamObject, DictionaryObject, NameObject)

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
        DictionaryObject({NameObject("/F1"): font})})
    contents = DecodedStreamObject()
    contents.set_data(b"BT /F1 12 Tf 72 720 Td (Hello portable Milo) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(contents)
    path = tmp_path / "document.pdf"
    with path.open("wb") as output:
        writer.write(output)
    assert "Hello portable Milo" in LocalFiles(tmp_path).read(str(path))["text"]
    empty = pypdf.PdfWriter()
    empty.add_blank_page(width=100, height=100)
    scanned = tmp_path / "scan.pdf"
    with scanned.open("wb") as output:
        empty.write(output)
    with pytest.raises(ToolError, match="scan"):
        LocalFiles(tmp_path).read(str(scanned))
