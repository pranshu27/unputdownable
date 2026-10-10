---
tags: [book, track-a]
chapter: 08
prev: "[[Ch 07 - Measurement]]"
next: "[[Ch 09 - Guardrails]]"
---
# Ch 8 — Serving: what happens when the store dies at 3 a.m.

It is 3 a.m. Qdrant has crashed. Does the whole service fall over with it?

In this build, no - and that is a deliberate choice made in the lifespan hook. The app **boots** with the store down, `/health` honestly reports what is broken, and the capability degrades instead of the liveness. A vector-store outage should cost you search, not your pager escalating an app that will not start.

The rest of the serving story is quiet discipline:

- **Pydantic at the boundary** - empty titles, bad formats and nonsense parameters are rejected before they reach any component that could be hurt by them.
- **Spans in every response** - embed, dense, sparse, fuse, each timed, returned to the caller. Observability is not a Week-14 project; it ships on day one, in the payload.
- **Config as environment** - collection name, vector size, model, chunk shape, RRF k. The encoder is an implementation detail behind an interface, which is why the 1024-dimension upgrade later is a config swap and not a fire drill.

> **Walk off stage with:** "Async API, graceful degradation - an outage costs capability, never liveness - and every response carries its own latency spans."
