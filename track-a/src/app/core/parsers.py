"""Document parsers (Strategy Pattern) - ADR 001.

Each parser converts a raw source document into a uniform stream of
:class:`Block` objects (headings, paragraphs, tables) while tracking the
section hierarchy so the chunker can build contextual headers
(``10-K > Item 7 > MD&A > Liquidity``).

Design contracts from ADR 001:
1. Strategy Pattern - adding a format adds a parser, no pipeline changes.
2. Tables are detected at parse time and kept as atomic blocks (never split).
3. Section hierarchy is tracked for contextual headers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser as StdlibHTMLParser
from typing import Protocol

from ..schemas.common import DocumentFormat


class BlockKind(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"


@dataclass(slots=True)
class Block:
    """A semantically atomic unit produced by a parser."""

    kind: BlockKind
    text: str
    level: int = 0  # heading depth (1 == h1 / "#")
    section_path: list[str] = field(default_factory=list)
    table_rows: list[list[str]] | None = None  # rows of cells for TABLE blocks

    @property
    def is_table(self) -> bool:
        return self.kind is BlockKind.TABLE


@dataclass(slots=True)
class ParsedDocument:
    title: str
    blocks: list[Block]

    @property
    def table_count(self) -> int:
        return sum(1 for b in self.blocks if b.is_table)

    @property
    def total_table_rows(self) -> int:
        return sum(len(b.table_rows or []) for b in self.blocks if b.is_table)


class DocumentParser(Protocol):
    """Interface every parsing strategy implements (ADR 001, contract #1)."""

    def parse(self, source: str, title: str) -> ParsedDocument: ...


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


class MarkdownParser:
    """Markdown -> blocks. Headings drive the section hierarchy; pipe tables
    become single atomic :class:`Block` instances."""

    def parse(self, source: str, title: str) -> ParsedDocument:
        blocks: list[Block] = []
        section_path: list[str] = []
        lines = source.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            heading = _HEADING_RE.match(line.strip())
            if heading:
                level = len(heading.group(1))
                text = heading.group(2).strip()
                section_path = section_path[: level - 1] + [text]
                blocks.append(
                    Block(BlockKind.HEADING, text, level=level, section_path=list(section_path))
                )
                i += 1
                continue
            stripped = line.strip()
            if stripped.startswith("|"):
                table_lines: list[str] = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1
                blocks.append(self._build_table(table_lines, section_path))
                continue
            if not stripped:
                i += 1
                continue
            paragraph: list[str] = []
            while i < len(lines):
                s = lines[i].strip()
                if not s or s.startswith("|") or _HEADING_RE.match(s):
                    break
                paragraph.append(s)
                i += 1
            blocks.append(
                Block(BlockKind.PARAGRAPH, " ".join(paragraph), section_path=list(section_path))
            )
        return ParsedDocument(title=title, blocks=blocks)

    @staticmethod
    def _build_table(table_lines: list[str], section_path: list[str]) -> Block:
        rows: list[list[str]] = []
        for ln in table_lines:
            if re.fullmatch(r"\|?[\s:\-|]+\|?", ln):  # separator row |---|---|
                continue
            cells = [c.strip() for c in ln.strip("|").split("|")]
            rows.append(cells)
        return Block(
            BlockKind.TABLE,
            text="\n".join(table_lines),
            section_path=list(section_path),
            table_rows=rows,
        )


# ---------------------------------------------------------------------------
# HTML (SEC 10-K / inline XBRL filings)
# ---------------------------------------------------------------------------

_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_SKIP_TAGS = {"script", "style", "ix:header", "ix:hidden"}
_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "table", "section"}


class _HtmlTreeBuilder(StdlibHTMLParser):
    """Extract headings, paragraphs and table rows from SEC-style HTML.

    Uses only the standard library so ingestion has no heavyweight HTML dep.
    Inline-XBRL cruft (ix:*) is treated as invisible text.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._section_path: list[str] = []
        self._buf: list[str] = []
        self._capture_text = False
        self._skip_depth = 0
        self._heading_level = 1
        # table state
        self._in_table = 0
        self._rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] = []

    def _flush_paragraph(self) -> None:
        text = re.sub(r"\s+", " ", " ".join(self._buf)).strip()
        self._buf = []
        if text:
            self.blocks.append(
                Block(BlockKind.PARAGRAPH, text, section_path=list(self._section_path))
            )

    def _flush_table(self) -> None:
        if self._rows:
            self.blocks.append(
                Block(
                    BlockKind.TABLE,
                    text="",
                    section_path=list(self._section_path),
                    table_rows=self._rows,
                )
            )
        self._rows = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _HEADING_TAGS:
            self._flush_paragraph()
            self._capture_text = True
            self._heading_level = _HEADING_TAGS[tag]
        elif tag == "table":
            self._flush_paragraph()
            self._in_table += 1
            if self._in_table == 1:
                self._flush_table()
        elif tag == "tr" and self._in_table:
            if self._row:
                self._rows.append(self._row)
            self._row = []
        elif tag in {"td", "th"} and self._in_table:
            self._cell = []
            self._capture_text = True
        elif tag in _BLOCK_TAGS:
            self._flush_paragraph()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "tr" and self._in_table:
            if self._row:
                self._rows.append(self._row)
            self._row = []
            return
        if tag in _HEADING_TAGS:
            text = re.sub(r"\s+", " ", " ".join(self._buf)).strip()
            self._buf = []
            self._capture_text = False
            if text:
                level = self._heading_level
                self._section_path = self._section_path[: level - 1] + [text]
                self.blocks.append(
                    Block(
                        BlockKind.HEADING,
                        text,
                        level=level,
                        section_path=list(self._section_path),
                    )
                )
        elif tag == "table":
            self._in_table = max(0, self._in_table - 1)
            if self._in_table == 0:
                self._flush_paragraph()
                self._flush_table()
        elif tag in {"td", "th"} and self._in_table:
            self._row.append(re.sub(r"\s+", " ", " ".join(self._cell)).strip())
            self._capture_text = False
        elif tag in _BLOCK_TAGS:
            self._flush_paragraph()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data.strip():
            return
        if self._in_table and self._capture_text:
            self._cell.append(data)
        else:
            self._buf.append(data)

    def close(self) -> None:
        self._flush_paragraph()
        self._flush_table()
        super().close()


class HtmlParser:
    """HTML (SEC 10-K, inline XBRL) -> blocks with tables as atomic units."""

    def parse(self, source: str, title: str) -> ParsedDocument:
        builder = _HtmlTreeBuilder()
        builder.feed(source)
        builder.close()
        # Drop trivial tables (fewer than 2 rows) that are layout artifacts.
        blocks = [b for b in builder.blocks if not (b.is_table and len(b.table_rows or []) < 2)]
        # Serialize tables as markdown so they are searchable as text too.
        for b in blocks:
            if b.is_table:
                lines = ["| " + " | ".join(row) + " |" for row in b.table_rows or []]
                b.text = "\n".join(lines)
        return ParsedDocument(title=title, blocks=blocks)


# ---------------------------------------------------------------------------
# Plain text + registry
# ---------------------------------------------------------------------------


class PlainTextParser:
    """Plain text -> paragraph blocks (blank-line separated)."""

    def parse(self, source: str, title: str) -> ParsedDocument:
        blocks: list[Block] = []
        for para in re.split(r"\n\s*\n", source):
            text = re.sub(r"\s+", " ", para).strip()
            if text:
                blocks.append(Block(BlockKind.PARAGRAPH, text))
        return ParsedDocument(title=title, blocks=blocks)


_PARSERS: dict[DocumentFormat, type] = {
    DocumentFormat.MARKDOWN: MarkdownParser,
    DocumentFormat.PDF: HtmlParser,  # SEC filings arrive as HTML; PDF strategy lands later
    DocumentFormat.DOCX: PlainTextParser,  # placeholder until the docx strategy lands
}


def get_parser(source_format: DocumentFormat) -> DocumentParser:
    """Route a document format to its parsing strategy (ADR 001, contract #1)."""
    return _PARSERS[source_format]()  # type: ignore[return-value]
