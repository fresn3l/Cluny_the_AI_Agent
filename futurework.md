# Future work (deferred)

Items captured here for later. Not in active development.

---

## Kosistenz integration — Phase A (highest priority)

| Task | Owner | Notes |
|------|-------|-------|
| Journal on save → `POST /ingest/text` | Kosistenz | `source: kosistenz-journal`, `collection: journal`, title = date |
| Weekly analytics rollup ingest | Kosistenz | `source: kosistenz-analytics`, `collection: analytics` |
| `context_json.analytics` on every Ask/Propose | Kosistenz | Build from dashboard metrics each session |
| Task mirror on todo CRUD | Kosistenz | `POST /tasks/sync` with stable `external_id` |
| Copy updated `ClunyBrainClient.swift` | Kosistenz | From `clients/kosistenz/`; includes analytics models |

**Gate:** Save a journal entry in Kosistenz → `cluny library list` shows it; Ask cites it.

---

## Kosistenz integration — Phase B (UI)

| Task | Owner | Notes |
|------|-------|-------|
| Streaming Ask panel with citation chips | Kosistenz | `/chat/stream` + links back to journal entries |
| “Suggest work” → `/propose` → accept creates real todo | Kosistenz | User packs on week clock; Cluny never schedules |
| Offline state on launch | Kosistenz | `GET /health`; disable brain buttons when `brain_ready: false` |

**Gate:** User asks “Why did I slip tasks?” and sees answer + journal citations + optional proposals.

---

## Cluny standalone polish — Phase C

| Task | Owner | Notes |
|------|-------|-------|
| Library filter by `source` / collection | Cluny | Browse `journal` vs `analytics` in full GUI |
| Glance tab Kosistenz snapshot | Cluny | Show last synced analytics when HTTP context provided |
| Multi-collection propose | Cluny | e.g. `collections: ["journal", "analytics"]` on `/propose` |
| Proposal citations in API response | Cluny | Return `sources[]` alongside `proposals[]` for UI chips |

---

## Deeper patterns — Phase D (stretch)

| Task | Notes |
|------|-------|
| “Review my quarter” agent mode | `/agent` with `collection=journal` + analytics context |
| Scheduled analytics ingest | Cron in Kosistenz or `cluny watch` on export dir |
| Eval golden cases | Kosistenz-shaped `context_json` + expected proposal themes |

---

## Suggested PR order (when resumed)

1. **Kosistenz PR:** journal ingest + health probe
2. **Kosistenz PR:** analytics in `context_json` + propose button
3. **Cluny PR:** library source/collection filters
4. **Kosistenz PR:** proposal accept → todo + task mirror sync

---

## Env reference

```bash
CLUNY_DATA_DIR=~/Library/Application\ Support/Cluny   # packaged app
CLUNY_BRAIN_URL=http://127.0.0.1:8787
CLUNY_KOSISTENZ_JOURNAL_DIR=/path/to/kosistenz/journals   # optional watch fallback
```
