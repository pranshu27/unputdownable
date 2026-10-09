import pathlib, json

p = pathlib.Path(r"c:\Users\PranshuSahijwani\OneDrive - DataEconomy Inc\Desktop\freedom\apps\genai-portfolio-tracker-react\src\data.js")
t = p.read_text(encoding="utf-8")

WEEKS = [
  {"week":1,"project":1,"focus":"P1 - Ingestion + Chunking + Index","notes":"","tasks":[
    {"id":"w1-1","done":True,"label":"Set up mono-repo project structure and CI skeleton"},
    {"id":"w1-2","done":False,"label":"Ingest PDF/MD/HTML pipeline with metadata enrichment"},
    {"id":"w1-3","done":True,"label":"Chunking strategy: 500-800 tokens, ~100 token overlap"},
    {"id":"w1-4","done":True,"label":"Embedding + vector index baseline (pgvector or Chroma)"},
    {"id":"w1-5","done":True,"label":"Baseline retrieval API (top-k chunks)"}]},
  {"week":2,"project":1,"focus":"P1 - Hybrid Retrieval + Lineage","notes":"","tasks":[
    {"id":"w2-1","done":True,"label":"Field-level lineage parser (13237 CONNECTOR edges from XML)"},
    {"id":"w2-2","done":False,"label":"BM25 keyword index alongside vector index (hybrid retrieval)"},
    {"id":"w2-3","done":False,"label":"Cross-encoder reranker for top-k results"},
    {"id":"w2-4","done":False,"label":"Citation output: chunk_id and source field in LLM response"},
    {"id":"w2-5","done":False,"label":"Mapping-level summary chunks for lineage queries"}]},
  {"week":3,"project":1,"focus":"P1 - Evaluation + Refusal Policy","notes":"","tasks":[
    {"id":"w3-1","done":False,"label":"Refusal policy for out-of-domain queries (score threshold)"},
    {"id":"w3-2","done":False,"label":"Prompt versioning - every LLM call traceable to template version"},
    {"id":"w3-3","done":False,"label":"Golden dataset: 50-200 query/expected_chunk pairs"},
    {"id":"w3-4","done":False,"label":"RAGAS harness: retrieval hit rate, citation correctness, hallucination rate"}]},
  {"week":4,"project":1,"focus":"P1 - RAGAS Scorecard + CI Gates","notes":"","tasks":[
    {"id":"w4-1","done":False,"label":"Baseline RAGAS scorecard: hit rate >= 0.85, hallucination <= 0.08"},
    {"id":"w4-2","done":False,"label":"CI quality gates - block PR on metric regression"},
    {"id":"w4-3","done":False,"label":"Staging deployment + dashboard (P95 latency, hit rate trend)"},
    {"id":"w4-4","done":False,"label":"Canary release, incident drill, final README + architecture diagram"}]},
  {"week":5,"project":2,"focus":"P2 - Offline Runtime + JSON Enforcement","notes":"","tasks":[
    {"id":"w5-1","done":False,"label":"Offline runtime setup: Ollama + 3 small models"},
    {"id":"w5-2","done":False,"label":"JSON schema enforcement for structured output"},
    {"id":"w5-3","done":False,"label":"Benchmark harness: 30-50 representative prompts per task type"},
    {"id":"w5-4","done":False,"label":"Latency + memory profiling at each quantization level"}]},
  {"week":6,"project":2,"focus":"P2 - Model Comparison + Scorecard","notes":"","tasks":[
    {"id":"w6-1","done":False,"label":"3-model comparison on quality, latency, memory"},
    {"id":"w6-2","done":False,"label":"Q4 vs Q5 quantization trade-off analysis"},
    {"id":"w6-3","done":False,"label":"Final model selection scorecard + README"},
    {"id":"w6-4","done":False,"label":"CLI assistant wrapping the winning model + config system"}]},
  {"week":7,"project":3,"focus":"P3 - Distributed Tracing","notes":"","tasks":[
    {"id":"w7-1","done":False,"label":"OTel trace context and span IDs through retrieval to LLM"},
    {"id":"w7-2","done":False,"label":"Structured log: chunk_id, score, query, latency per request"},
    {"id":"w7-3","done":False,"label":"Trace storage: Jaeger or Tempo in Docker"},
    {"id":"w7-4","done":False,"label":"Sampling strategy: 100% dev, 10% prod"}]},
  {"week":8,"project":3,"focus":"P3 - Dashboards + Alerting","notes":"","tasks":[
    {"id":"w8-1","done":False,"label":"Dashboards: P50/P95 latency, hit rate trend, hallucination rate"},
    {"id":"w8-2","done":False,"label":"Alerting thresholds + on-call runbook"},
    {"id":"w8-3","done":False,"label":"Regression gate: CI fails if P95 > 2.5s or hallucination > 0.08"},
    {"id":"w8-4","done":False,"label":"Incident drill: simulate latency spike + document response"}]},
  {"week":9,"project":4,"focus":"P4 - SFT Dataset + LoRA Setup","notes":"","tasks":[
    {"id":"w9-1","done":False,"label":"Define task: instruction-following on Informatica domain"},
    {"id":"w9-2","done":False,"label":"Curate 2k-10k SFT examples: query, context, answer triplets"},
    {"id":"w9-3","done":False,"label":"SFT with LoRA/QLoRA - baseline training run"},
    {"id":"w9-4","done":False,"label":"Eval on golden dataset: base vs fine-tuned hit rate"}]},
  {"week":10,"project":4,"focus":"P4 - DPO + Scorecard","notes":"","tasks":[
    {"id":"w10-1","done":False,"label":"DPO preference tuning on 200-500 preference pairs"},
    {"id":"w10-2","done":False,"label":"Scorecard: base vs SFT vs DPO on all RAGAS metrics"},
    {"id":"w10-3","done":False,"label":"Overfitting check + early stopping strategy"},
    {"id":"w10-4","done":False,"label":"Model card + reproducible training script"}]},
  {"week":11,"project":4,"focus":"P4 - Production Promotion","notes":"","tasks":[
    {"id":"w11-1","done":False,"label":"Quantize best model to Q4/Q5 with quality check"},
    {"id":"w11-2","done":False,"label":"A/B test: fine-tuned vs base on live traffic (10 pct canary)"},
    {"id":"w11-3","done":False,"label":"Promotion decision: metric threshold + rollback plan"},
    {"id":"w11-4","done":False,"label":"Final model registry entry + changelog"}]},
  {"week":12,"project":5,"focus":"P5 - Audio + Vision Pipeline","notes":"","tasks":[
    {"id":"w12-1","done":False,"label":"Whisper-based audio transcription pipeline (streaming mode)"},
    {"id":"w12-2","done":False,"label":"Vision: frame extraction + CLIP/LLaVA visual grounding"},
    {"id":"w12-3","done":False,"label":"Multimodal fusion: audio + vision to unified context window"},
    {"id":"w12-4","done":False,"label":"Latency budget: sub 500ms audio, sub 200ms vision"}]},
  {"week":13,"project":5,"focus":"P5 - Orchestration + Queue","notes":"","tasks":[
    {"id":"w13-1","done":False,"label":"Redis Streams message queue for multimodal events"},
    {"id":"w13-2","done":False,"label":"Worker pool: auto-scale on queue depth"},
    {"id":"w13-3","done":False,"label":"Back-pressure handling + graceful degradation"},
    {"id":"w13-4","done":False,"label":"Load test: 10 concurrent streams x 5 minutes"}]},
  {"week":14,"project":5,"focus":"P5 - Resilience + Demo","notes":"","tasks":[
    {"id":"w14-1","done":False,"label":"Circuit breaker + graceful fallback for each service failure mode"},
    {"id":"w14-2","done":False,"label":"Chaos test matrix: network jitter, dropped frames, model timeout, queue overflow"},
    {"id":"w14-3","done":False,"label":"Replay mode for deterministic debugging with recorded inputs"},
    {"id":"w14-4","done":False,"label":"30-minute soak test - confirm no memory leak"},
    {"id":"w14-5","done":False,"label":"Demo video: normal path + failure-path behavior with measured latency"}]}
]

needle = "  ],\n\n  interview:"
idx = t.find(needle)
print("needle idx:", idx)
if idx != -1:
    weeks_js = json.dumps(WEEKS, indent=2, ensure_ascii=True)
    new_t = t[:idx] + "  ],\n\n  weeks: " + weeks_js + ",\n\n  interview:" + t[idx+len(needle):]
    p.write_text(new_t, encoding="utf-8")
    total = sum(len(w["tasks"]) for w in WEEKS)
    done  = sum(1 for w in WEEKS for task in w["tasks"] if task["done"])
    print(f"Done. Size={p.stat().st_size}, weeks=14, tasks={total}, done={done}")
else:
    # Try alternate
    for n in ["  ],\n\n  interview:", "  ],\r\n\r\n  interview:"]:
        idx2 = t.find(n)
        if idx2 != -1:
            print(f"Found alt needle: {n!r} at {idx2}")
            break
    print("Context around interview:", repr(t[t.find("interview:")-30:t.find("interview:")+20]))
