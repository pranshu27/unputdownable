"""Parser strategy tests (ADR 001 contract #1: Strategy Pattern dispatch)."""

from app.core.parsers import BlockKind, HtmlParser, MarkdownParser, PlainTextParser, get_parser
from app.schemas.common import DocumentFormat


def test_get_parser_routes_by_format():
    assert type(get_parser(DocumentFormat.MARKDOWN)) is MarkdownParser
    assert type(get_parser(DocumentFormat.PDF)) is HtmlParser


def test_markdown_headings_drive_section_path():
    md = "# 10-K\n## Item 7\n### Liquidity\nCash was strong.\n"
    parsed = MarkdownParser().parse(md, "Test 10-K")
    kinds = [b.kind for b in parsed.blocks]
    assert kinds == [BlockKind.HEADING, BlockKind.HEADING, BlockKind.HEADING, BlockKind.PARAGRAPH]
    assert parsed.blocks[-1].section_path == ["10-K", "Item 7", "Liquidity"]


def test_markdown_table_is_atomic_block():
    md = (
        "# Results\n\n| Year | Revenue |\n|---|---|\n| 2022 | $394B |\n| 2023 | $383B |\n\n"
        "Revenue declined slightly.\n"
    )
    parsed = MarkdownParser().parse(md, "Report")
    tables = [b for b in parsed.blocks if b.is_table]
    assert len(tables) == 1
    assert tables[0].table_rows == [
        ["Year", "Revenue"],
        ["2022", "$394B"],
        ["2023", "$383B"],
    ]
    assert tables[0].section_path == ["Results"]


def test_html_parser_extracts_table_rows_and_headings():
    html = (
        "<html><body><h2>Item 7</h2><p>MD&A overview text.</p>"
        "<table><tr><th>Metric</th><th>2023</th></tr>"
        "<tr><td>Net sales</td><td>$383,285</td></tr>"
        "<tr><td>Gross margin</td><td>44.1%</td></tr></table></body></html>"
    )
    parsed = HtmlParser().parse(html, "Apple 10-K")
    tables = [b for b in parsed.blocks if b.is_table]
    paras = [b for b in parsed.blocks if b.kind is BlockKind.PARAGRAPH]
    assert len(tables) == 1
    assert tables[0].table_rows == [
        ["Metric", "2023"],
        ["Net sales", "$383,285"],
        ["Gross margin", "44.1%"],
    ]
    assert tables[0].section_path == ["Item 7"]
    assert any("MD&A overview text." == p.text for p in paras)


def test_html_parser_ignores_tiny_layout_tables():
    html = "<table><tr><td>x</td></tr></table><p>after</p>"
    parsed = HtmlParser().parse(html, "t")
    assert not any(b.is_table for b in parsed.blocks)


def test_plain_text_paragraphs():
    parsed = PlainTextParser().parse("First para.\n\nSecond para.", "t")
    assert [b.text for b in parsed.blocks] == ["First para.", "Second para."]
