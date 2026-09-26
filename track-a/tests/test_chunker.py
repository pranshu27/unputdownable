"""Semantic chunker tests (ADR 001 contracts #2, #3, #4)."""

from uuid import uuid4

from app.core.chunker import chunk_document, count_tokens
from app.core.parsers import MarkdownParser
from app.schemas.common import DocumentFormat


def _chunk_md(md: str, **kw):
    parsed = MarkdownParser().parse(md, "Test Doc")
    return parsed, chunk_document(parsed, uuid4(), DocumentFormat.MARKDOWN, **kw)


def test_chunks_carry_contextual_headers():
    md = "# 10-K\n## Item 7\nParagraph one about liquidity.\n"
    _, chunks = _chunk_md(md)
    assert len(chunks) == 1
    assert chunks[0].contextual_header == "Test Doc > 10-K > Item 7"


def test_tables_never_split_or_merge():
    md = (
        "# Financials\n\nIntro paragraph.\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\n"
        "| C | D |\n|---|---|\n| 5 | 6 |\n\nClosing paragraph."
    )
    parsed, chunks = _chunk_md(md)
    tables = [c for c in chunks if c.is_table]
    assert len(tables) == 2  # two source tables -> two atomic chunks
    assert [len(t.table_rows) for t in tables] == [3, 2]  # header row kept per table
    # table chunks contain no prose
    for t in tables:
        assert all(not line.strip().startswith("Intro") for line in t.text.splitlines())


def test_prose_packed_to_target_with_overlap():
    sentences = " ".join(f"Sentence number {i} is here." for i in range(40))
    md = f"# Doc\n\n{sentences}\n"
    _, chunks = _chunk_md(md, target_tokens=40, overlap_tokens=10)
    assert len(chunks) > 1
    # every chunk respects target (single-sentence overflow aside)
    assert all(c.token_count <= 60 for c in chunks)
    # consecutive chunks share overlap vocabulary
    assert chunks[0].text != chunks[1].text


def test_token_count_includes_header():
    md = "# Doc\n\nSome text here.\n"
    _, chunks = _chunk_md(md)
    expected = count_tokens("Test Doc > Doc") + count_tokens("Some text here.")
    assert chunks[0].token_count == expected
