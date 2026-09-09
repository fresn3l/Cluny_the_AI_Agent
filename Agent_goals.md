## CLUNY

Cluny is to serve as a Knowledge RAG. I will have more than one agent, and Cluny is to be the private, local-only RAG — a personal knowledge base for summarizing articles, books, and notes into a searchable second brain.

## Goals

The goal is for this to be coded and customizable, so API + custom code (self-hosted). This is also a learning project for me. We should focus on thorough explanations and aim to develop my understanding of AI agents, architecture, tools, etc.

---

## Planning — current baseline (Sprints 1–11)

**Cluny** is a local-first **brain**:

| Layer | What ships |
|-------|------------|
| **Stores** | SQLite catalog + FTS5, Chroma vectors, chat sessions; optional scratch `tasks.sqlite` / `calendar.sqlite` (CLI/widget only — **not** Kosistenz SoT) |
| **Retrieval** | Hybrid vector + keyword, optional LLM or cross-encoder rerank |
| **Entry points** | CLI (`ask`, `agent`, `chat`, `serve`), optional PySide6 GUI, menu-bar widget (Ask + Capture), localhost HTTP API |
| **Agents** | Knowledge / planner tool namespaces; LLM supervisor — **propose** work, do not place it on the week |
| **Ops** | Export/import zip, `cluny backup run`, optional AES export (`--password`) |
| **Quality** | Golden eval harness + CI (FTS-only + optional full eval on `golden-local.yaml`) |

Self-hosted, customizable, aligned with “coded and customizable.”

---

## Platform — Kosistenz + Cluny

**Kosistenz is the life you live in. Cluny is the brain you ask.**

**[Kosistenz](https://github.com/fresn3l/ToDo-Desktop_Application)** (repo `fresn3l/ToDo-Desktop_Application`; product name Kosistenz) owns the week clock, hard events, deadline to-dos / All Work, packing, goals, workouts, journal **files**, and iPhone pack — usable even when Cluny is quit.

**Cluny** (this repo) owns PDFs/notes, hybrid RAG, Ask/chat/agent, Ollama, and indexing a **copy** of journal / check-in / life text. It may **propose** work (title, estimate, due **date**, keywords, citations); it never picks clock slots, never Fill week, never writes packed blocks or Apple Calendar, and never maintains a second authoritative todo/calendar list for Kosistenz.

| Repo | Role |
|------|------|
| **ToDo-Desktop_Application** (Kosistenz) | Daily Mac home base — scheduling, todos, journal, pack, Ask/Brain/Library UI, `cluny serve` supervisor |
| **Cluny_the_AI_Agent** | Optional local brain — `cluny serve` on `127.0.0.1:8787` |

**Canonical contract (wins if this file disagrees):**  
[Kosistenz `docs/cluny-integration.md`](https://github.com/fresn3l/ToDo-Desktop_Application/blob/cursor/cluny-run-ingest-7484/docs/cluny-integration.md) ([PR #59](https://github.com/fresn3l/ToDo-Desktop_Application/pull/59)). Cluny mirror: [INTEGRATION.md](INTEGRATION.md).

**UX:** Ask / Brain / Library / proposal inbox live in Kosistenz. Cluny’s PySide GUI and menu-bar widget are optional **admin** (library + capture notes), not a second Today.

**Runtimes stay separate.** Do not vendor Cluny into Kosistenz. Do not embed Ollama/Chroma in Kosistenz. Do not merge apps or migrate Kosistenz DBs into Cluny.

---

## Vocabulary

| Say | Do not say |
|-----|------------|
| Kosistenz **commits** a to-do / block / journal | Cluny “saves the todo” |
| Cluny **proposes** work | Cluny “schedules” / “places” / “fills the week” |
| Kosistenz **publishes** a snapshot | Cluny “owns calendar.sqlite for Kosistenz” |
| Cluny **indexes** the journal | Cluny “is the journal database” |

---

## Next steps (brainstorm — second brain / knowledge)

- **Life context:** Consume Kosistenz life snapshot (`context_json` / `GET :18741/api/cluny/life`) in chat and agent tools; prefer it over scratch tasks/calendar SQLite.
- **Proposals:** Stable ids, day-only dues, `kosistenz:{uuid}` pointers after accept; optional `citations` / `goal_id` fields (backward compatible).
- **Retrieval:** Tune cross-encoder model; collection-scoped eval; more golden cases on your real index.
- **API clients:** Shortcuts, scripts, capture via `cluny serve` — still local-first.
- **Verticals:** Finance / health schemas (local-first, minimal cloud) — separate from the Kosistenz week.

---

## Task / productivity — current shape

**Kosistenz owns the live list.** Cluny may emit proposals; accept creates Kosistenz work items. Placement (weekday + packer) is Kosistenz-only.

**Implemented in Cluny:** Option C lite — one repo, `cluny agent` modes, `cluny chat` supervisor, RAG tools. Planner-style flows should **`search_brain` then create/emit a proposal**, not treat `create_task` as the canonical Kosistenz to-do.

Standalone CLI `cluny tasks` / `cluny calendar` remain for **scratch** when Cluny runs alone. They must not be documented or wired as the phone’s list or the week clock.

**Never:** spawn weekly goals (“3h spanish”) — that is Kosistenz Sunday spawn. Never mark a Kosistenz to-do done as a side effect of chat. Never emit `HH:MM` as a start time.

---

## Personal life management (later phases)

Calendar / travel / finance / health each imply **integrations + permissions + sometimes cloud APIs** — treat each as a **vertical slice**: design the local schema and tools first, then add one integration. Keep sensitive aggregates out of the raw LLM context where possible.

For the **week you live**, Kosistenz is already the vertical. Do not rebuild it inside Cluny.

---

## Learning milestones (aligned with “thorough explanations”)

1. Solid **RAG** mental model (chunking, retrieval failure modes, when to cite vs hallucinate).
2. **Tool-calling loop** (one tool at a time vs parallel; validation; timeouts).
3. **Memory layers:** session vs persistent catalog vs vector store — what belongs where; life week lives in Kosistenz’s snapshot, not Cluny’s scratch DBs.
4. **Router vs planner:** intent classification vs multi-step orchestration — planner **proposes**, does not place.
5. **API vs CLI:** same domain logic, different transport (SSE for streaming).
6. **Safety/privacy** for local vs API keys and for finance/health-shaped data; no cloud LLM for planning this stack.

---

## Open questions (fill in as you decide)

- [x] Primary life UI: **Kosistenz** (Ask/Brain/Library inside it); Cluny GUI optional admin.
- [ ] Single machine only, or sync second brain (library) across devices (and how)?
- [ ] Which knowledge vertical after syllabus proposals: **language practice notes** vs **finance**?
- [x] Cloud LLM for planning — **no**; stay local-only (Ollama) for this integration.
