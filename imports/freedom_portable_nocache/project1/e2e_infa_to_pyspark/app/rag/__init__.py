"""RAG layer: cross-file Informatica knowledge base for data modelling.

Public surface:
- build_knowledge_base / InformaticaKnowledgeBase — chunk + embed + index + retrieve.
- chunking (strategies + Chunk), embeddings (providers), vector_store (memory / pgvector).
"""

from app.rag.knowledge_base import (
    InformaticaKnowledgeBase,
    RagTool,
    build_knowledge_base,
)

__all__ = [
    "InformaticaKnowledgeBase",
    "RagTool",
    "build_knowledge_base",
]
