# Sprint 15+ — Kosistenz integration (next steps)

Cluny brain work for S13–S14 is done. Remaining work splits between **Kosistenz app** (data push + UI) and **Cluny polish**.

---

## Phase A — Kosistenz data plumbing (highest priority)

| Task | Owner | Notes |
|------|-------|-------|
| Journal on save → `/ingest/text` | Kosistenz | `source: kosistenz-journal`, `collection: journal`, title = date |
| Weekly analytics rollup ingest | Kosistenz | `source: kosistenz-analytics`, `collection: analytics` |
| `context_json.analytics` on Ask/Propose | Kosistenz | Build from dashboard metrics each session |
| Task mirror on todo CRUD | Kosistenz | `POST /tasks/sync` with stable `external_id` |
| Copy `ClunyBrainClient.swift` | Kosistenz | From `clients/kosistenz/`; includes analytics models |

**Acceptance:** Save a journal entry in Kosistenz → `cluny library list` shows it; Ask cites that entry.

---

## Phase B — Kosistenz UI (insights surface)

| Task | Owner | Notes |
|------|-------|-------|
| “Talk to Cluny” panel | Kosistenz | `/chat/stream` + citation chips linking to journal |
| “Suggest work” button | Kosistenz | `/propose` with full `context_json`; show proposals list |
| Accept proposal → create todo | Kosistenz | User picks day; packer places on clock (Cluny never schedules) |
| Offline state | Kosistenz | `GET /health` on launch; disable brain buttons when `brain_ready: false` |

**Acceptance:** User asks “Why did I slip tasks?” and sees answer + journal citations + optional proposals.

---

## Phase C — Cluny standalone polish

| Task | Owner | Notes |
|------|-------|-------|
| Library filter by `source` / collection | Cluny | Browse `journal` vs `analytics` in full GUI |
| Glance tab Kosistenz snapshot | Cluny | Optional: show last synced analytics if HTTP context provided |
| Multi-collection propose | Cluny | e.g. `collections: ["journal", "analytics"]` on `/propose` |
| Proposal citations in API response | Cluny | Return `sources[]` alongside `proposals[]` for UI chips |

---

## Phase D — Deeper patterns (stretch)

| Task | Notes |
|------|-------|
| “Review my quarter” agent mode | `/agent` with `collection=journal` + analytics context |
| Scheduled analytics ingest | Cron in Kosistenz or `cluny watch` on export dir |
| Eval golden cases | Kosistenz-shaped `context_json` + expected proposal themes |

---

## Suggested PR order

1. **Kosistenz PR:** journal ingest on save + health probe
2. **Kosistenz PR:** analytics in `context_json` + propose button
3. **Cluny PR:** library source/collection filters (standalone)
4. **Kosistenz PR:** proposal accept → todo + task mirror sync

---

## Env reference

```bash
CLUNY_DATA_DIR=~/Library/Application\ Support/Cluny   # packaged app
CLUNY_BRAIN_URL=http://127.0.0.1:8787
CLUNY_KOSISTENZ_JOURNAL_DIR=/path/to/kosistenz/journals   # optional watch fallback
```
