# Track A — Agentic RAG

Autonomous Agentic RAG & Inference Platform (FastAPI, LangGraph, vLLM, Qdrant, Redis,
PostgreSQL, Phoenix, Ragas). Week 1 Day 3 state:

- Async **FastAPI** app with **Pydantic v2** schemas
- **Qdrant** collection: **dense (HNSW, BGE-small 384-d cosine) + sparse (BM25/IDF)**
- **Ingestion pipeline (ADR 001):** Strategy-Pattern parsers (Markdown / SEC 10-K HTML /
  plain text) → semantic chunking with contextual headers → table-aware atomic chunks →
  embed → upsert
- **Hybrid search (ADR 002):** dense + sparse retrieval fused with **RRF (k=60,
  implemented from scratch)**

## Layout

```
track-a/
├── docker-compose.yml       # local Qdrant
├── pyproject.toml
├── data/                    # real ingest batch (Apple FY2023 10-K + notes)
├── scripts/day3_benchmark.py  # Day-3 measurement run (quality/latency/cost)
├── src/app/
│   ├── main.py              # app factory + lifespan
│   ├── config.py            # pydantic-settings (TRACKA_* env)
│   ├── api/routes/          # health / documents / search
│   ├── schemas/             # Pydantic v2 models
│   └── core/
│       ├── parsers.py       # Strategy-Pattern parsing (ADR 001 #1)
│       ├── chunker.py       # semantic chunking + contextual headers (ADR 001 #2-4)
│       ├── embeddings.py    # fastembed dense + hashed BM25-style sparse
│       ├── ingest_service.py# parse → chunk → embed → upsert, per-stage spans
│       ├── search_service.py# dense + sparse + RRF hybrid retrieval (ADR 002)
│       ├── rrf.py           # reciprocal rank fusion, from scratch
│       └── qdrant.py        # dense + sparse collection config
└── tests/                   # pytest (pythonpath=src)
```

## Quickstart

```bash
# 1. Start Qdrant (dense + sparse vector index)
docker-compose up -d

# 2. Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # adds fastembed (ONNX embeddings) on first run

# 3. Run the API
uvicorn app.main:app --app-dir src --reload

# 4. Verify
curl -s localhost:8000/health
```

## Endpoints

| Method | Path | Status |
| :--- | :--- | :--- |
| GET | `/health` | live |
| POST | `/api/v1/documents` | **live** — full ADR-001 pipeline (parse → chunk → embed → upsert) |
| POST | `/api/v1/search` | **live** — hybrid dense+sparse+RRF; `use_hybrid=false` for dense-only |

## Day-3 measurement run

```bash
python scripts/day3_benchmark.py --reset   # wipes + rebuilds the collection, ingests the batch
```

Captures: parse-failure + table-corruption rate, Δ Recall@5 (hybrid vs dense),
ingest p95/throughput, search span latencies (embed/retrieve/fuse), index storage +
embedding tokens per 1k pages. Results land in `scripts/day3_results.json` and
`../measurements.md`.
