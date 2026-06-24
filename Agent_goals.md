

## Goals
The goal is for this to be coded and customizable, so API + custom code (self-hosted)
This is also a learning project  for me. We should focus on thorough explanations and aim to develop my understanding of AI agents, architecture, tools, etc. 

# Second Brain / Knowledge
Personal knowledge base — summarizing articles, books, and notes into a searchable second brain

# Task management
breaking goals into steps, assigning deadlines, and tracking progress

# Personal Life Management
Calendar optimization — scheduling meetings, blocking focus time, managing conflicts
Travel planning — end-to-end trip research, booking coordination, and itinerary building
Finance tracking — monitoring spending, summarizing statements, flagging anomalies
Health & habit coaching — logging workouts, meals, or moods and giving personalized feedback

---

## Planning — current baseline

What exists today (**Cluny**): local **RAG** second brain — Ollama for embeddings + chat, **Chroma** for vectors, **SQLite** catalog, CLI ingest / `add-dir` / `ask`. Self-hosted, customizable, aligned with “coded and customizable.”

---

## Next steps (brainstorm — second brain / knowledge)

- **Ingestion quality:** URL capture (with your own rules), better PDF pipeline (OCR for scans), optional HTML/Markdown from web with source URL stored in metadata.
- **Retrieval quality:** hybrid search (keyword + vector), re-ranking, optional small cross-encoder; tune chunking per doc type.
- **Organization:** tags / collections in SQLite, “projects” or notebooks, light dedup and “replace document” UX.
- **Interaction:** small **TUI or web UI** on top of the same Python core (still local); optional streaming answers.
- **Evaluation:** a fixed set of “golden questions” you rerun after prompt or pipeline changes so quality doesn’t drift silently.
- **Ops:** backup story for `CLUNY_DATA_DIR`, export snapshots, optional encryption at rest for the data dir.

---

## Task / productivity goals — one agent vs separate agent?

**Option A — one Cluny with tool namespaces**  
Single orchestrator (Ollama + tool loop): **knowledge tools** (`search_brain`, `add_note`) vs **task tools** (`create_task`, `list_tasks`, `update_deadline`) backed by SQLite (or CalDAV later). One personality, shared memory of “you,” simpler deployment; risk is prompt complexity and accidental tool misuse if scopes blur.

**Option B — separate “task agent”**  
Second small service or CLI (e.g. **Cluny-tasks** or a worker) that only handles goals/steps/deadlines and talks to its own DB schema; Cluny stays **retrieve-then-answer** for knowledge. Clear separation of concerns, easier to test tasks without touching RAG; you glue them in a **supervisor** later if you want one chat entrypoint.

**Option C — same repo, two modes**  
One codebase, `cluny brain …` vs `cluny tasks …` (or `--mode`), shared config but **no** mixing of tools in a single LLM call until you explicitly add a “planner” mode that calls both.

**Rough recommendation for learning:** finish **second brain** retrieval + catalog until it feels boringly reliable, then add **task storage + CRUD as explicit tools** (Option A lite or C). Split a dedicated task agent (B) only if task logic (recurrence, calendar sync) starts dominating the codebase.

---

## Personal life management (later phases)

Calendar / travel / finance / health each imply **integrations + permissions + sometimes cloud APIs** — treat each as a **vertical slice**: design the local schema and tools first, then add one integration (e.g. export calendar as ICS first, Google Calendar API later). Keep sensitive aggregates out of the raw LLM context where possible.

---

## Learning milestones (aligned with “thorough explanations”)

1. Solid **RAG** mental model (chunking, retrieval failure modes, when to cite vs hallucinate).
2. **Tool-calling loop** (one tool at a time vs parallel; validation; timeouts).
3. **Memory layers:** session vs persistent catalog vs vector store — what belongs where.
4. **Safety/privacy** for local vs API keys and for finance/health-shaped data.

---

## Open questions (fill in as you decide)

- [ ] Primary UI for the next year: CLI only, TUI, or local web?
- [ ] Single machine only, or sync second brain across devices (and how)?
- [ ] Task agent: separate binary/repo or submodule of this repo?
- [ ] Which vertical after second brain: **tasks** vs **calendar** vs **language practice**?

