"""Markdown as blocks the window lays out (MiloKit/MarkdownBlocks.swift): headings, paragraphs, bullets, numbered
items, to-dos, quotes, rules, code. Inline styles become Qt rich text with every tag escaped first, so text from
other people never turns into markup; a link stays a link only when `keep` says so.
"""
from __future__ import annotations

import html
import re
from typing import Callable

_INLINE = re.compile(r"(`[^`]+`)|\*\*(.+?)\*\*|__(.+?)__|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)|"
                     r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?!\w)|\[([^\]]+)\]\(([^)\s]+)\)")


def own_link(url: str) -> bool:
    """The one link notes have of their own: "[The whole transcript](transcript.md)"."""
    return url == "transcript.md"


def block(kind: str, text: str = "", **extra) -> dict:
    return {"kind": kind, "text": text, "level": 0, "depth": 0, "number": 0, "done": False, **extra}


def parse(markdown: str) -> list[dict]:
    """Lines of one paragraph join with a space; a blank line ends it."""
    blocks: list[dict] = []
    paragraph: list[str] = []
    quote: list[str] = []
    code: list[str] | None = None

    def flush():
        if paragraph:
            blocks.append(block("paragraph", " ".join(paragraph)))
        if quote:
            blocks.append(block("quote", " ".join(quote)))
        paragraph.clear()
        quote.clear()

    for raw in markdown.replace("\r\n", "\n").split("\n"):
        if code is not None:
            if raw.strip().startswith("```"):
                blocks.append(block("code", "\n".join(code)))
                code = None
            else:
                code.append(raw)
            continue
        line = raw.strip()
        lead = raw[:len(raw) - len(raw.lstrip(" \t"))]
        depth = min(1, sum(4 if c == "\t" else 1 for c in lead) // 2)
        if not line:
            flush()
            continue
        if line.startswith("```"):
            flush()
            code = []
            continue
        heading = _heading(line)
        if heading:
            flush()
            blocks.append(heading)
            continue
        bare = line.replace(" ", "")
        if len(line) >= 3 and bare and (set(bare) == {"-"} or set(bare) == {"*"}):
            flush()
            blocks.append(block("rule"))
            continue
        if line.startswith(">"):
            if paragraph:
                flush()
            quote.append(line[1:].strip())
            continue
        item = _item(line, depth)
        if item:
            flush()
            blocks.append(item)
            continue
        if quote:
            flush()
        # A line under a list item, indented, goes on with that item.
        if depth > 0 and not paragraph and blocks and blocks[-1]["kind"] in ("bullet", "numbered", "todo"):
            blocks[-1]["text"] += " " + line
            continue
        paragraph.append(line)
    if code is not None:
        blocks.append(block("code", "\n".join(code)))
    flush()
    for i, b in enumerate(blocks):
        b["gap"] = 0 if i == 0 else _gap(blocks[i - 1], b)
        # Code shows as written; everything else gets its bold, italics and links as Qt rich text.
        b["html"] = html.escape(b["text"]).replace("\n", "<br>") if b["kind"] == "code" else inline(b["text"])
    return blocks


def _heading(line: str) -> dict | None:
    hashes = len(line) - len(line.lstrip("#"))
    if 1 <= hashes <= 6 and line[hashes:hashes + 1] == " ":
        return block("heading", line[hashes:].strip(), level=hashes)
    return None


def _item(line: str, depth: int) -> dict | None:
    for mark in ("- ", "* ", "+ "):
        if line.startswith(mark):
            rest = line[2:]
            lower = rest.lower()
            if lower.startswith("[ ] ") or lower.startswith("[x] "):
                return block("todo", rest[4:], done=lower.startswith("[x]"), depth=depth)
            return block("bullet", rest, depth=depth)
    match = re.match(r"(\d{1,3})[.)] (.*)", line)
    if match:
        return block("numbered", match.group(2), number=int(match.group(1)), depth=depth)
    return None


def _gap(previous: dict, current: dict) -> int:
    """Air between blocks: more before a heading, little between items of one list."""
    if current["kind"] == "heading":
        return 22 if current["level"] <= 2 else 16
    if previous["kind"] == "heading":
        return 8
    if previous["kind"] in ("bullet", "numbered", "todo") and current["kind"] in ("bullet", "numbered", "todo"):
        return 6
    return 11


def inline(text: str, keep: Callable[[str], bool] = own_link, link_color: str = "") -> str:
    """Inline Markdown as Qt rich text (bold, italics, code, links)."""
    out, at = [], 0
    for match in _INLINE.finditer(text):
        out.append(html.escape(text[at:match.start()]))
        code, bold, bold2, italic, italic2, label, url = match.groups()
        if code:
            out.append(f"<code>{html.escape(code[1:-1])}</code>")
        elif bold or bold2:
            out.append(f"<b>{inline(bold or bold2, keep, link_color)}</b>")
        elif italic or italic2:
            out.append(f"<i>{inline(italic or italic2, keep, link_color)}</i>")
        elif keep(url):
            style = f' style="color:{link_color}"' if link_color else ""
            out.append(f'<a href="{html.escape(url, quote=True)}"{style}>{html.escape(label)}</a>')
        else:
            out.append(html.escape(label))
        at = match.end()
    out.append(html.escape(text[at:]))
    return "".join(out).replace("\n", "<br>")


def has_markup(text: str) -> bool:
    """Whether a reply is worth laying out as blocks rather than one line of prose."""
    return bool(re.search(r"(^|\n)\s*(#{1,6} |[-*+] |\d{1,3}[.)] |> |```)|\*\*|`", text))
