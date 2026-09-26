"""Semantic chunking with contextual headers - ADR 001, contracts #2 and #3.

Chunks align to complete semantic units (paragraphs, list items, tables):
- prose blocks are greedily packed to a target token size with overlap;
- table blocks are NEVER split or merged (contract #4, table-aware rules);
- every chunk carries ``title > section hierarchy`` so it is self-describing
  out of context.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

from .parsers import Block, BlockKind, ParsedDocument
from ..schemas.common import DocumentFormat
from ..schemas.documents import Chunk

_TOKEN_RE = re.compile(r"\S+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def count_tokens(text: str) -> int:
    """Whitespace-token approximation (no tokenizer dependency at ingest)."""
    return len(_TOKEN_RE.findall(text))


def _word_window(text: str, max_tokens: int) -> str:
    return " ".join(text.split()[:max_tokens])


def _split_long_paragraph(text: str, target_tokens: int) -> list[str]:
    """Split an oversized paragraph on sentence boundaries (semantic units)."""
    if count_tokens(text) <= target_tokens:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in _SENTENCE_RE.split(text):
        s_tokens = count_tokens(sentence)
        if current and current_tokens + s_tokens > target_tokens:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += s_tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def chunk_document(
    parsed: ParsedDocument,
    document_id: UUID,
    source_format: DocumentFormat,
    *,
    target_tokens: int = 250,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """Build semantically coherent, self-describing chunks from parsed blocks.

    - Prose paragraphs are packed up to ``target_tokens`` with ``overlap_tokens``
      carried between consecutive chunks.
    - Tables are emitted as single atomic chunks regardless of size.
    - Headings update the section path and act as hard chunk boundaries.
    """
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_tokens = 0
    buffer_section: list[str] = []

    def _header(section_path: list[str]) -> str:
        parts = [parsed.title, *section_path]
        return " > ".join(p for p in parts if p)

    def _emit(section_path: list[str]) -> None:
        nonlocal buffer, buffer_tokens
        if not buffer:
            return
        body = "\n\n".join(buffer)
        header = _header(section_path)
        chunks.append(
            Chunk(
                chunk_id=uuid4(),
                document_id=document_id,
                text=body,
                contextual_header=header,
                start_index=0,
                end_index=len(body),
                token_count=count_tokens(header) + count_tokens(body),
                is_table=False,
                table_rows=None,
                metadata={"section_path": list(section_path), "source_format": source_format.value},
            )
        )
        buffer, buffer_tokens = [], 0

    for block in parsed.blocks:
        if block.kind is BlockKind.HEADING:
            _emit(buffer_section)  # heading = hard boundary
            buffer_section = list(block.section_path)
            continue

        if block.is_table:
            _emit(buffer_section)  # never merge tables with prose
            _emit_table_chunk(block, document_id, source_format, _header(buffer_section), chunks)
            continue

        for piece in _split_long_paragraph(block.text, target_tokens):
            piece_tokens = count_tokens(piece)
            if buffer and buffer_tokens + piece_tokens > target_tokens:
                overlap = _word_window(buffer[-1], overlap_tokens)
                section = buffer_section
                _emit(section)
                if overlap:
                    buffer = [overlap]
                    buffer_tokens = count_tokens(overlap)
                else:
                    buffer, buffer_tokens = [], 0
            buffer.append(piece)
            buffer_tokens += piece_tokens

    _emit(buffer_section)
    return chunks


def _emit_table_chunk(
    block: Block,
    document_id: UUID,
    source_format: DocumentFormat,
    header: str,
    chunks: list[Chunk],
) -> None:
    """A table is one atomic chunk: markdown serialization + structured rows."""
    rows = block.table_rows or []
    chunks.append(
        Chunk(
            chunk_id=uuid4(),
            document_id=document_id,
            text=block.text,
            contextual_header=header,
            start_index=0,
            end_index=len(block.text),
            token_count=count_tokens(header) + count_tokens(block.text),
            is_table=True,
            table_rows=[list(r) for r in rows],
            metadata={"source_format": source_format.value},
        )
    )


def chunk_source(
    source: str,
    title: str,
    document_id: UUID,
    source_format: DocumentFormat,
    *,
    target_tokens: int = 250,
    overlap_tokens: int = 50,
) -> tuple[ParsedDocument, list[Chunk]]:
    """Convenience: parse then chunk in one call (used by the ingest service)."""
    from .parsers import get_parser

    parsed = get_parser(source_format).parse(source, title)
    chunks = chunk_document(
        parsed,
        document_id,
        source_format,
        target_tokens=target_tokens,
        overlap_tokens=overlap_tokens,
    )
    return parsed, chunks
