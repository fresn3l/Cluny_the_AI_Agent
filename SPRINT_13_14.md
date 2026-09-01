# Sprint 13–14 — Kosistenz analytics + historical propose

**Status:** Cluny side complete on `sprint-12-standalone-app` branch.

## S13 — Data feed (Cluny)

- [x] `AnalyticsSnapshot` + `GoalProgress` in `KosistenzContext`
- [x] `format_analytics_snapshot()` for prompt merge
- [x] `POST /ingest/text` accepts optional `collection` (tags doc in library)
- [x] `add_inline_text(..., collection_name=…)` assigns collection after catalog upsert
- [x] Swift `KosistenzContextPayload.analytics` + `propose(collection:)`

### Kosistenz app (next — not in this repo)

- [ ] On journal save → `POST /ingest/text` with `collection: "journal"`
- [ ] Weekly (or on dashboard open) → ingest analytics rollup with `collection: "analytics"`
- [ ] Pass `analytics` in `context_json` on every Ask/Propose from the widget

## S14 — Historical propose (Cluny)

- [x] `run_proposals()` calls `retrieve()` before LLM
- [x] Retrieved snippets merged into propose prompt
- [x] `POST /propose` accepts `collection` and `k`
- [x] Widget Propose tab passes selected collection
- [x] Tests: context analytics, RAG propose, ingest collection API

## Test plan

```bash
.venv/bin/python -m pytest tests/test_kosistenz_context.py tests/test_proposals.py \
  tests/test_kosistenz_ingest_propose.py -q
```

## Example Kosistenz calls

```bash
# Journal on save
curl -s http://127.0.0.1:8787/ingest/text -H 'Content-Type: application/json' -d '{
  "text": "Today I shipped the packer fix…",
  "catalog": true,
  "source": "kosistenz-journal",
  "title": "2026-09-01 journal",
  "collection": "journal"
}'

# Propose from history + live analytics
curl -s http://127.0.0.1:8787/propose -H 'Content-Type: application/json' -d '{
  "question": "What should I change next week?",
  "collection": "journal",
  "context_json": {
    "analytics": { "period": "2026-W35", "tasks_slipped": 3, "tasks_completed": 12 }
  }
}'
```
