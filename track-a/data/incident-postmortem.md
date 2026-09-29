# Incident Postmortem: Payment Authorization Degradation (SEV-1)

## Incident Summary

On 2026-09-14 between 14:02 and 14:47 UTC, authorization latency breached the 150ms p95
budget, peaking at 940ms, with a card-auth error rate of 2.3% against the 0.1% SLO.
The incident was declared SEV-1 under runbook RB-114 and tracked as ticket RAG-482.

## Timeline

- 14:02 UTC — deploy-de7a2b91 promotes build 2026.09.14-r3 to the auth fleet (canary 5%).
- 14:06 UTC — first ERR-4021 (ledger journal write timeout) events appear in Phoenix traces.
- 14:11 UTC — trace id 8f3a9c2e41d7 shows fraud-scoring span at 310ms (budget: 40ms).
- 14:19 UTC — pager escalation to on-call secondary; incident channel #inc-2026-0914 opened.
- 14:31 UTC — canary frozen at 5%; rollback of deploy-de7a2b91 initiated by sre-bot.
- 14:41 UTC — journal write p99 recovers to 9ms; ERR-4021 rate back to baseline.
- 14:47 UTC — incident resolved; error rate 0.04%, p95 authorization latency 148ms.

## Root Cause

The deploy-de7a2b91 build enabled the new idempotency-key cache with a 30-second TTL.
Under burst traffic the cache stampede saturated the journal writer connection pool
(24 connections), causing ERR-4021 timeouts. The retry policy in `retry.py` amplified
load 4x because the circuit breaker (see ADR-003) did not trip on timeout-class errors:

```
2026-09-14T14:11:03Z WARN journal_pool exhausted pool=ledger-writer in_flight=24/24
2026-09-14T14:11:03Z ERR  journal_write timeout after 5000ms trace=8f3a9c2e41d7 code=ERR-4021
2026-09-14T14:11:04Z WARN retry_scheduled attempt=2 backoff=120ms policy=exponential
```

> Note: the same stampede pattern was observed in the September 3 load test (report
> LT-2026-0903) but was dismissed as an artifact of the synthetic traffic shape.

## Contributing Factors

1. **Cache stampede** — no single-flight dedup; 12,000 concurrent requests rebuilt the same key.
2. **Circuit breaker gap** — timeout errors bypassed the breaker (fixed in build 2026.09.15-r1).
3. **Canary blast radius** — 5% of the auth fleet is above the 2% threshold in RB-114 for SEV-1 services.
4. **Missing alert** — the journal pool saturation gauge had no alert rule; detection came from user-facing SLO burn.

## Remediation Plan

| ID | Action | Owner | Due | Status |
|---|---|---|---|---|
| RAG-482-1 | Add single-flight dedup to idempotency cache | @payments-core | 2026-09-28 | done |
| RAG-482-2 | Trip breaker on timeout-class errors | @sre-platform | 2026-09-28 | done |
| RAG-482-3 | Reduce canary blast radius to 2% for Tier-0 | @release-eng | 2026-10-09 | in progress |
| RAG-482-4 | Alert on journal_pool saturation > 80% for 5m | @observability | 2026-10-02 | open |

## Lessons Learned

- Load-test traffic must replay production key distributions; the LT-2026-0903 gap shows
  synthetic uniform keys hide stampede amplification.
- The 40ms fraud-scoring span budget is coupled to journal write p99; budget reviews must
  cover the full dependency chain, not per-service in isolation.
- See also the runbook addendum RB-114-A2 (journal pool triage) and the design doc
  [Idempotency Cache RFC-77](https://wiki.internal/rfc/77) for the follow-up design.
