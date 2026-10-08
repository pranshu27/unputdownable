# Portable Runbook

## Daily
1. update week plan from template
2. execute one delivery block and one interview block
3. capture evidence links

## Weekly
1. run tests
2. run eval reports
3. update top3 closeout state
4. publish weekly close note

## Standard Commands

From `rag-system/`:

```powershell
python -m pytest -q
python -m rag_system.eval.retrieval_eval --help
python -m rag_system.eval.ragas_eval --help
```

## Project Closure Checklist
- [ ] P1 closure evidence linked
- [ ] P2 benchmark report published
- [ ] P3 week+2 ops/gates implemented and validated
- [ ] interview packet updated

## Artifact Placement Convention
- P2 artifacts: `study_plan_4m/05_artifacts/p2/`
- P3 artifacts: `study_plan_4m/05_artifacts/p3/`
- weekly close notes: `study_plan_4m/05_artifacts/weekly/`

