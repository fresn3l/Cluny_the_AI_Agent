# Sprint 17 — Kosistenz integration (Phase A)

**Goal:** Wire Kosistenz to push journal + analytics into Cluny and pull Ask/proposals back. Cluny brain contract is ready (S13–S14); this sprint is mostly **Kosistenz app** work with a small Cluny polish pass.

**Prerequisite:** Sprint 16 complete. Deferred items live in [`futurework.md`](futurework.md).

---

## Phase A — Data plumbing

| # | Task | Owner | Done |
|---|------|-------|------|
| 1 | Journal on save → `POST /ingest/text` (`collection: journal`) | Kosistenz | |
| 2 | Weekly analytics rollup → ingest (`collection: analytics`) | Kosistenz | |
| 3 | `context_json.analytics` on every Ask/Propose | Kosistenz | |
| 4 | Task mirror on todo CRUD → `POST /tasks/sync` | Kosistenz | |
| 5 | Copy `clients/kosistenz/ClunyBrainClient.swift` into Kosistenz | Kosistenz | |
| 6 | `GET /health` probe on Kosistenz launch | Kosistenz | |

**Gate:** Save a journal in Kosistenz → `cluny library list` shows it; Ask cites it.

---

## Cluny polish (parallel, small)

| Task | Notes |
|------|-------|
| Library filter by `source` / collection in standalone GUI | Browse `journal` vs `analytics` |
| Return `sources[]` on `/propose` response | Citation chips in Kosistenz UI |

---

## Suggested PR order

1. **Kosistenz:** journal ingest + health probe  
2. **Kosistenz:** analytics in `context_json` + propose button  
3. **Cluny:** library source/collection filters  
4. **Kosistenz:** proposal accept → todo + task mirror sync  

---

## Test plan

```bash
# Cluny side (already shipped)
cluny serve
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/ingest/text -H 'Content-Type: application/json' -d '{
  "text": "journal entry", "catalog": true,
  "source": "kosistenz-journal", "title": "2026-09-01", "collection": "journal"
}'

# After Kosistenz wiring
# 1. Save journal in Kosistenz
# 2. cluny library list
# 3. Ask from Kosistenz widget → citations appear
```

See [`INTEGRATION.md`](INTEGRATION.md) for the full HTTP contract.
