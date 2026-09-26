# Product Notes: Payments Platform
## Architecture
The payments platform is an event-driven service built on Kafka with idempotent consumers.
Each ledger entry is written twice: once to the append-only journal and once to the materialized balance view.
## Latency Budget
The end-to-end authorization budget is 150ms at p95.
The fraud scoring span must complete within 40ms; the remaining time is split between routing and persistence.
## Fee Schedule
| Tier | Domestic fee | Cross-border fee |
|---|---|---|
| Standard | 1.9% | 3.1% |
| Premium | 1.2% | 2.4% |
| Enterprise | 0.8% | 1.6% |

Disputes are handled by a separate reconciliation worker with a 30-day window.
