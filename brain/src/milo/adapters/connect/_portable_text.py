"""Bounded document readers that do not require desktop office applications.

ZIP/XML documents are inspected, never extracted or executed. PDF support loads
pypdf only when a PDF is read; all other readers use the Python standard library.
"""
from __future__ import annotations

import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as XML

from milo.core.types import ToolError

SUFFIXES = frozenset({".pdf", ".docx", ".odt", ".html", ".htm"})
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_XML_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 30 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5000
MAX_CHARS = 200_000
MAX_PDF_PAGES = 1000


class _Text:
    def __init__(self, limit: int):
        self.limit = limit + 1  # Retain one extra character to report truncation.
        self.parts: list[str] = []
        self.size = 0

    @property
    def full(self) -> bool:
        return self.size >= self.limit

    def add(self, value: str):
        value = value[:max(0, self.limit - self.size)]
        self.parts.append(value)
        self.size += len(value)

    def result(self) -> str:
        return "".join(self.parts)


def _xml(archive: zipfile.ZipFile, name: str):
    info = archive.getinfo(name)
    if info.file_size > MAX_XML_BYTES:
        raise ToolError("That document contains too much text to read safely.")
    raw = archive.read(name)
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", raw, flags=re.IGNORECASE):
        raise ToolError("That document uses XML declarations this reader does not support.")
    return XML.fromstring(raw)


def _check_archive(archive: zipfile.ZipFile):
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_ENTRIES or sum(info.file_size for info in entries) > MAX_ARCHIVE_BYTES:
        raise ToolError("That document is too large to read safely.")
    if any(info.flag_bits & 1 for info in entries):
        raise ToolError("That document is encrypted. Open an unencrypted copy instead.")


def _docx(path: Path, output: _Text):
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        _check_archive(archive)
        names = ["word/document.xml"] + sorted(name for name in archive.namelist()
            if re.fullmatch(r"word/(header|footer)\d+\.xml", name))
        for name in names:
            root = _xml(archive, name)
            for paragraph in root.iter(namespace + "p"):
                for node in paragraph.iter():
                    if node.tag == namespace + "t":
                        output.add(node.text or "")
                    elif node.tag == namespace + "tab":
                        output.add("\t")
                    elif node.tag in (namespace + "br", namespace + "cr"):
                        output.add("\n")
                    if output.full:
                        return
                output.add("\n")
                if output.full:
                    return


def _odt(path: Path, output: _Text):
    namespace = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"

    def content(node):
        if output.full:
            return
        if node.tag == namespace + "tab":
            output.add("\t")
        elif node.tag == namespace + "line-break":
            output.add("\n")
        elif node.tag == namespace + "s":
            try:
                count = max(1, min(1000, int(node.get(namespace + "c", "1"))))
            except ValueError:
                count = 1
            output.add(" " * count)
        else:
            output.add(node.text or "")
            for child in node:
                content(child)
                output.add(child.tail or "")
                if output.full:
                    return

    with zipfile.ZipFile(path) as archive:
        _check_archive(archive)
        root = _xml(archive, "content.xml")
        for paragraph in root.iter():
            if paragraph.tag not in (namespace + "p", namespace + "h"):
                continue
            content(paragraph)
            output.add("\n")
            if output.full:
                return


class _HTML(HTMLParser):
    _skip = frozenset({"script", "style", "noscript", "template", "head"})
    _block = frozenset({"p", "div", "li", "tr", "table", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self, output: _Text):
        super().__init__(convert_charrefs=True)
        self.output = output
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._skip:
            self.hidden.append(tag)
        if not self.hidden and tag in self._block | {"br"}:
            self.output.add("\n")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        elif tag in self._block:
            self.output.add("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.output.add(data)


def _pdf(path: Path, output: _Text):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ToolError("PDF reading needs the desktop extra (pypdf).") from None
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ToolError("That PDF is password-protected. Open an unencrypted copy instead.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ToolError("That PDF has too many pages to read at once.")
        for page in reader.pages:
            output.add(page.extract_text() or "")
            if output.full:
                break
            output.add("\n")
        if not output.result().strip():
            raise ToolError("That PDF has no readable text. It may be a scan.")
    except ToolError:
        raise
    except Exception as error:
        raise ToolError("That PDF could not be read. It may be damaged or use unsupported encryption.") from error


def read(path: Path, max_chars: int = 20_000) -> dict:
    """The Files.read wire shape, with resource limits and an accurate truncation flag."""
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise ToolError("The text length must be a positive number.")
    max_chars = min(max_chars, MAX_CHARS)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ToolError("That file is too large to read at once.")
    output = _Text(max_chars)
    try:
        match path.suffix.casefold():
            case ".docx":
                _docx(path, output)
            case ".odt":
                _odt(path, output)
            case ".html" | ".htm":
                parser = _HTML(output)
                with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
                    while not output.full and (part := stream.read(64 * 1024)):
                        parser.feed(part)
                parser.close()
            case ".pdf":
                _pdf(path, output)
            case _:
                raise ToolError("That document format is not supported by the portable reader.")
    except (zipfile.BadZipFile, KeyError, XML.ParseError, RecursionError, RuntimeError, NotImplementedError) as error:
        raise ToolError("That document could not be read. It may be damaged.") from error
    text = output.result()
    return {"path": str(path), "name": path.name, "text": text[:max_chars], "truncated": len(text) > max_chars}
