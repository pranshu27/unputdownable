---
tags: [book, track-a]
chapter: 08
prev: "[[Ch 07 - Measurement]]"
next: "[[Ch 09 - Guardrails]]"
---
# Ch 8 — Serving: an async API that degrades gracefully

FastAPI + Pydantic v2, three routes: `GET /health`, `POST /api/v1/documents` (ingest), `POST /api/v1/search` (hybrid or dense-only).

**Design choices worth defending:**

- **Best-effort lifespan:** if Qdrant is down at startup the app still boots and `/health` reports the error - a vector store outage must not take the service down
- **Validation at the boundary:** Pydantic models reject empty titles, bad formats, bad params
- **Spans in the response:** every search returns per-stage timings (embed / dense / sparse / fuse) - observability from day one, not bolted on
- **Config as env:** `TRACKA_*` knobs (collection, dims, model, chunk shape, RRF k) - the encoder is an implementation detail behind an interface

> **Interview line:** "Async FastAPI with graceful degradation - a store outage degrades the app's capability, not its liveness - and every response carries its own latency spans."
