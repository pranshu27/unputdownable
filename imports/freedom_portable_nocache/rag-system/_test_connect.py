import os, sys, time
sys.path.insert(0, "src")
os.environ.setdefault("POSTGRES_URL", "postgresql://raguser:ragpass@localhost:5433/ragdb")
os.environ.setdefault("RAG_BACKEND", "pgvector")
os.environ.setdefault("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

print("[1] importing embedder...", flush=True)
t0 = time.time()
from rag_system.embeddings import get_embedding_provider
e = get_embedding_provider()
print(f"[2] embedder ready: dim={e.dim}  ({time.time()-t0:.1f}s)", flush=True)

from rag_system.store.vector_store import PgVectorStore
t1 = time.time()
print("[3] connecting pgvector...", flush=True)
s = PgVectorStore("postgresql://raguser:ragpass@localhost:5433/ragdb", dim=e.dim)
print(f"[4] count={s.count()}  ({time.time()-t1:.1f}s)", flush=True)
