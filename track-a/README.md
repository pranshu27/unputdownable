# Track A — Agentic RAG

Autonomous Agentic RAG & Inference Platform (FastAPI, LangGraph, vLLM, Qdrant, Redis,
PostgreSQL, Phoenix, Ragas). This is the **Week 1 Day 2 skeleton**:

- Async **FastAPI** app with **Pydantic v2** schemas
- **Qdrant** collection config for **dense (HNSW) + sparse (BM25/IDF)** vectors

## Layout

```
track-a/
├── docker-compose.yml       # local Qdrant
├── pyproject.toml
├── src/app/
│   ├── main.py              # app factory + lifespan
│   ├── config.py            # pydantic-settings (TRACKA_* env)
│   ├── api/routes/          # health / documents / search
│   ├── schemas/             # Pydantic v2 models
│   └── core/qdrant.py       # dense + sparse collection config
└── tests/                   # pytest (pythonpath=src)
```

## Quickstart

```bash
# 1. Start Qdrant (dense + sparse vector index)
docker-compose up -d

# 2. Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # or: pip install fastapi uvicorn pydantic pydantic-settings qdrant-client pytest httpx

# 3. Run the API
uvicorn app.main:app --app-dir src --reload

# 4. Verify
curl -s localhost:8000/health
```

## Endpoints (skeleton)

| Method | Path | Status |
| :--- | :--- | :--- |
| GET | `/health` | live |
| POST | `/api/v1/documents` | 202 stub (chunking lands Day 3) |
| POST | `/api/v1/search` | stub (hybrid retrieval lands Week 2) |
