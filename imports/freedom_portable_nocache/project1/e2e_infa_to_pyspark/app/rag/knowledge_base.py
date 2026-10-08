"""Retrieval-Augmented Generation knowledge base over the Informatica dump.

Purpose
-------
After reverse-engineering extracts canonical metadata, and BEFORE PySpark is generated, a
data-model advisor needs *cross-file* context: every source/target, every SQL override,
every join and lookup across ALL Informatica exports — not just the one mapping in flight.
This module builds that corpus once and serves semantic retrieval over it.

Pipeline (proper RAG)
---------------------
1. Parse every PowerCenter XML -> canonical nodes (`flatten_mapping_to_nodes`).
2. **Chunk** each node with a structure-aware strategy (`app.rag.chunking`).
3. **Embed** each chunk into a vector (`app.rag.embeddings` — Azure or hashing fallback).
4. **Index** the vectors in a vector store (`app.rag.vector_store` — pgvector or in-memory).
5. **Retrieve** by embedding the query and running nearest-neighbour search.

Backends are interchangeable: set ``RAG_BACKEND=pgvector`` (with ``POSTGRES_URL``) for the
production vector DB, or ``memory`` for an offline, deterministic in-process store (tests).

RAG-as-a-tool
-------------
`as_tool()` exposes a single ``search(query, k)`` callable that the DataModellerAgent uses
like a tool: it issues targeted queries (sources, targets, lookups for a given mapping/file)
and assembles the retrieved context into a field-level source-to-target mapping.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

from app.rag.chunking import Chunk, chunk_node
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.rag.vector_store import InMemoryVectorStore, PgVectorStore, VectorStore
from app.utils.logger import get_logger
from app.utils.pc_file_processor import flatten_mapping_to_nodes
from app.utils.xml_parser import parse_powercenter_xml

load_dotenv()
logger = get_logger(__name__)


@dataclass
class RagTool:
    """A minimal RAG tool the data modeller can call (RAG-as-a-tool pattern)."""

    name: str
    description: str
    search: Callable[[str, int], List[Dict[str, Any]]]


class InformaticaKnowledgeBase:
    """Chunk + embed + index every canonical node in an Informatica dump folder."""

    def __init__(
        self,
        backend: Optional[str] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ) -> None:
        self._embedder = embedding_provider or get_embedding_provider()
        self.backend = (backend or os.getenv("RAG_BACKEND", "memory")).lower()
        self.chunks: List[Chunk] = []
        self._store: Optional[VectorStore] = None

    # Back-compat alias: earlier code/tests referenced ``documents``.
    @property
    def documents(self) -> List[Chunk]:
        return self.chunks

    # -- ingestion ---------------------------------------------------------

    def _make_store(self) -> VectorStore:
        if self.backend == "pgvector":
            dsn = os.getenv("POSTGRES_URL", "")
            if not dsn:
                logger.warning("RAG_BACKEND=pgvector but POSTGRES_URL unset; using memory")
            else:
                try:
                    store = PgVectorStore(dsn, dim=self._embedder.dim)
                    logger.info("RAG vector store: pgvector (dim=%s)", self._embedder.dim)
                    return store
                except Exception as exc:  # graceful fallback keeps the pipeline alive
                    logger.warning("pgvector unavailable (%s); using in-memory store", exc)
        logger.info("RAG vector store: in-memory (dim=%s)", self._embedder.dim)
        return InMemoryVectorStore(dim=self._embedder.dim)

    def build_from_folder(self, folder_path: str) -> "InformaticaKnowledgeBase":
        """Parse, chunk, embed and index every PowerCenter XML in ``folder_path``."""
        for root, _dirs, files in os.walk(folder_path):
            for fname in files:
                if not fname.lower().endswith(".xml"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    parsed = parse_powercenter_xml(fpath)
                except Exception as exc:  # skip unreadable files, keep building
                    logger.warning("KB skip %s: %s", fname, exc)
                    continue
                for node in flatten_mapping_to_nodes(parsed):
                    self.chunks.extend(chunk_node(node, fname))

        self._store = self._make_store()
        if self.chunks:
            vectors = self._embedder.embed([c.text for c in self.chunks])
            self._store.upsert(self.chunks, vectors)
        logger.info(
            "Knowledge base built: %s chunks indexed (%s)", len(self.chunks), self.backend
        )
        return self

    # -- retrieval ---------------------------------------------------------

    def retrieve(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Embed the query and return the top-``k`` nearest chunks."""
        if self._store is None:
            raise RuntimeError("Knowledge base not built. Call build_from_folder first.")
        q_vec = self._embedder.embed_one(query)
        return self._store.search(q_vec, k=k)

    def build_context(self, query: str, k: int = 5, max_chars: int = 4000) -> str:
        """Concatenate the top-k retrieved chunks into a grounding context string."""
        hits = self.retrieve(query, k=k)
        blocks: List[str] = []
        budget = max_chars
        for h in hits:
            block = f"[{h['source_file']} · {h['node_class']} · {h['name']}]\n{h['text']}"
            if len(block) > budget:
                block = block[:budget]
            blocks.append(block)
            budget -= len(block)
            if budget <= 0:
                break
        return "\n\n---\n\n".join(blocks)

    # -- RAG as a tool -----------------------------------------------------

    def as_tool(self) -> RagTool:
        """Expose retrieval as a callable tool for the DataModellerAgent."""
        return RagTool(
            name="informatica_rag_search",
            description=(
                "Search the Informatica knowledge base for sources, targets, "
                "transformations, SQL overrides, joins and lookups across all files. "
                "Returns the most relevant metadata chunks for a natural-language query."
            ),
            search=self.retrieve,
        )


def build_knowledge_base(
    folder_path: str,
    backend: Optional[str] = None,
    embedding_provider: Optional[EmbeddingProvider] = None,
) -> InformaticaKnowledgeBase:
    return InformaticaKnowledgeBase(
        backend=backend, embedding_provider=embedding_provider
    ).build_from_folder(folder_path)
