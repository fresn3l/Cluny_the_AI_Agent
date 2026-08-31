# Cluny API — Kosistenz integration

Cluny is the **brain service** behind **[Kosistenz](https://github.com/fresn3l/Kosistenz)** (journal, calendar, to-dos). Kosistenz is the Mac home-base app; **do not** duplicate task DB, calendar DB, or RAG inside Kosistenz.

## Quick start

1. Install Cluny: `pip install -e ".[api]"` in [Cluny_the_AI_Agent](https://github.com/fresn3l/Cluny_the_AI_Agent).
2. Start Ollama locally (for Ask / Chat / ingest embeddings).
3. Start API:
   ```bash
   cluny serve
   ```
4. Default base URL: **`http://127.0.0.1:8787`**
5. On Kosistenz launch, probe:
   ```bash
   curl -s http://127.0.0.1:8787/health
   ```

## Authentication

| Setting | Default |
|---------|---------|
| `CLUNY_API_BIND` | `127.0.0.1` |
| `CLUNY_API_PORT` | `8787` |
| `CLUNY_API_TOKEN` | empty |

If `CLUNY_API_TOKEN` is set, send:

```
X-Cluny-Token: your-token
```

or

```
Authorization: Bearer your-token
```

Non-localhost clients **require** a token.

## Health

```http
GET /health
```

```json
{
  "status": "ok",
  "ollama_ok": true,
  "doc_count": 42,
  "task_count": 7,
  "chunk_count": 1200
}
```

- If `ollama_ok` is false: Kosistenz can still show tasks/calendar; disable LLM buttons.
- OpenAPI docs: `http://127.0.0.1:8787/docs`

## Kosistenz module → endpoints

| Module | Endpoints |
|--------|-----------|
| **Todos** | `GET/POST/PATCH/DELETE /tasks`, `POST /tasks/{id}/complete` |
| **Calendar** | `GET /calendar/events`, `POST /calendar/import`, `POST /context/meeting` |
| **Journal** | `POST /ingest/text` (`catalog: true`), `POST /search`, `POST /chat` |
| **Day view** | `POST /context/day` |
| **Ask Cluny** | `POST /chat` (supervisor routes intent) |

## Tasks

### List

```http
GET /tasks?status=open&due_week=true
GET /tasks?external_id=kosistenz:550e8400-e29b-41d4-a716-446655440000
```

### Create

```http
POST /tasks
Content-Type: application/json

{
  "title": "Send agenda",
  "due_at": "tomorrow",
  "external_id": "kosistenz:550e8400-e29b-41d4-a716-446655440000"
}
```

Use **`kosistenz:{uuid}`** for `external_id` on every task Kosistenz creates.

### Update / complete / delete

```http
PATCH /tasks/{id}
POST /tasks/{id}/complete
DELETE /tasks/{id}
```

`{id}` accepts full id or unique prefix.

## Calendar

```http
GET /calendar/events?date=2026-09-01
GET /calendar/events?limit=20
```

Import ICS (local path on Mac):

```http
POST /calendar/import
{ "path": "/Users/you/Downloads/calendar.ics" }
```

## Journal save

When user saves a journal entry in Kosistenz:

```http
POST /ingest/text
{
  "text": "Today I worked on…",
  "catalog": true,
  "source": "kosistenz-journal",
  "title": "2026-09-01 journal"
}
```

Requires Ollama for embedding. Entry becomes searchable via `/search` and `/chat`.

## Context bundles (structured UI)

### Day agenda

```http
POST /context/day
{ "date": "2026-09-01" }
```

Returns `{ date, tasks[], events[], snippets[] }` — no LLM.

### Meeting prep

```http
POST /context/meeting
{ "title": "Product sync", "date": "2026-09-02" }
```

Returns matching events, related open tasks, and note snippets (FTS-only retrieval).

## Brain / chat

```http
POST /chat
{ "question": "What's due this week?" }

POST /search
{ "query": "Smith project", "k": 5 }

POST /agent
{ "question": "…", "mode": "planner" }
```

Streaming RAG: `POST /ask` (SSE).

## Swift client sketch

```swift
struct ClunyClient {
    let base = URL(string: "http://127.0.0.1:8787")!
    var token: String?

    func health() async throws -> HealthResponse {
        var req = URLRequest(url: base.appendingPathComponent("health"))
        return try await decode(GET req)
    }

    func createTask(title: String, dueAt: String?, externalId: String) async throws -> TaskRow {
        var req = URLRequest(url: base.appendingPathComponent("tasks"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { req.setValue(token, forHTTPHeaderField: "X-Cluny-Token") }
        req.httpBody = try JSONEncoder().encode([
            "title": title,
            "due_at": dueAt as Any,
            "external_id": externalId
        ])
        return try await decode(req)
    }
}
```

## Errors

| Code | Meaning |
|------|---------|
| 401 | Bad/missing token |
| 403 | Non-localhost without token |
| 404 | Task/event/file not found |
| 502 | Ollama unreachable or model error |

## Service at login (optional)

Copy and edit `macos/com.cluny.serve.plist`, then:

```bash
cp macos/com.cluny.serve.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cluny.serve.plist
```

Point `ProgramArguments` at your repo’s `run_cluny.sh serve`.

## Data directory

Kosistenz and Cluny share one brain when they use the same `CLUNY_DATA_DIR` (default `.cluny` next to Cluny’s repo). Document the path in Kosistenz settings if Cluny runs from a non-default location.
