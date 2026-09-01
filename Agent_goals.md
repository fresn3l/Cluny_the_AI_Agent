
## CLUNY
 Cluny is to serve as a Knowledge RAG. I will have more than one agent, and cluny is to be the private, local only RAG.
 Personal knowledge base — summarizing articles, books, and notes into a searchable second brain

## Goals
The goal is for this to be coded and customizable, so API + custom code (self-hosted)
This is also a learning project  for me. We should focus on thorough explanations and aim to develop my understanding of AI agents, architecture, tools, etc. 

---

## Planning — current baseline (Sprints 1–9)

**Cluny** is a local-first platform:

| Layer | What ships |
|-------|------------|
| **Stores** | SQLite catalog + FTS5, Chroma vectors, `tasks.sqlite`, `calendar.sqlite`, chat sessions |
| **Retrieval** | Hybrid vector + keyword, optional LLM or cross-encoder rerank |
| **Entry points** | CLI (`ask`, `agent`, `chat`, `tasks`, `serve`), PySide6 GUI, localhost HTTP API |
| **Agents** | Knowledge / tasks / all / **planner** tool namespaces; LLM supervisor with regex fallback |
| **Ops** | Export/import zip, `cluny backup run`, optional AES export (`--password`) |
| **Quality** | Golden eval harness + CI (FTS-only + optional full eval on `golden-local.yaml`) |

Self-hosted, customizable, aligned with “coded and customizable.”

---

## Platform — Kosistenz + Cluny

**Kosistenz is the life you live in. Cluny is the brain you ask.**

**[Kosistenz](https://github.com/fresn3l/Kosistenz)** owns the week clock, hard events, deadline to-dos, packing, goals, workouts, journal **files**, and iPhone pack — usable even when Cluny is quit.

**Cluny** (this repo) owns PDFs/notes, hybrid RAG, Ask/chat/agent, and indexing a **copy** of journal text. It may **propose** work (title, estimate, due, keyword); it never picks clock slots, never Fill week, and never maintains a second authoritative todo/calendar list for Kosistenz.

| Repo | Role |
|------|------|
| **Kosistenz** | Daily Mac home base — scheduling, todos, journal, pack |
| **Cluny_the_AI_Agent** | Optional local brain — `cluny serve` on localhost |

Integration contract: [INTEGRATION.md](INTEGRATION.md) (aligned with Kosistenz `docs/cluny-integration.md`). Cluny widget and full GUI remain for quick capture and deep library browse alongside Kosistenz.

---

## Next steps (brainstorm — second brain / knowledge)

- **Integrations:** CalDAV / Google Calendar two-way sync; multi-device sync (Syncthing or manifest-based).
- **Retrieval:** Tune cross-encoder model; collection-scoped eval; more golden cases on your real index.
- **API clients:** Shortcuts, scripts, future mobile capture via `cluny serve`.
- **Verticals:** Finance / health schemas (local-first, minimal cloud).

---

## Task / productivity — current shape

**Implemented:** Option C lite — one repo, `cluny agent --mode knowledge|tasks|all|planner`, plus `cluny chat` supervisor and task/calendar tools. Task recurrence (`--every daily|weekly|monthly`), natural due dates (`tomorrow`, `+3d`).

**Planner mode** orchestrates search_brain then create_task in one agent session (max 12 turns). Supervisor routes compound questions to planner.

---

## Personal life management (later phases)

Calendar / travel / finance / health each imply **integrations + permissions + sometimes cloud APIs** — treat each as a **vertical slice**: design the local schema and tools first, then add one integration (e.g. export calendar as ICS first, Google Calendar API later). Keep sensitive aggregates out of the raw LLM context where possible.

---

## Learning milestones (aligned with “thorough explanations”)

1. Solid **RAG** mental model (chunking, retrieval failure modes, when to cite vs hallucinate).
2. **Tool-calling loop** (one tool at a time vs parallel; validation; timeouts).
3. **Memory layers:** session vs persistent catalog vs vector store — what belongs where.
4. **Router vs planner:** intent classification vs multi-step orchestration in one session.
5. **API vs CLI:** same domain logic, different transport (SSE for streaming).
6. **Safety/privacy** for local vs API keys and for finance/health-shaped data.

---

## Open questions (fill in as you decide)

- [ ] Primary UI for the next year: CLI, GUI, or API clients?
- [ ] Single machine only, or sync second brain across devices (and how)?
- [ ] Which vertical after tasks+calendar: **language practice** vs **finance**?
- [ ] Cloud LLM providers (OpenAI/Anthropic) — stay local-only or optional?
