# Cluny — build checklist

Use this file to track progress. Check boxes as you complete items.

---

## Phase 0 — Goals and constraints

- [ ] **Define the agent’s job** (e.g. coding assistant, research, ops, creative)
- [ ] **Pick interaction surface** (CLI, web UI, API, IDE plugin, Slack, etc.)
- [ ] **Set boundaries** (what it must never do, data it must not send externally)
- [ ] **Choose primary model(s)** (hosted API vs local; one model vs router)
- [ ] **Budget and latency** expectations (tokens/month, max response time)

---

## Phase 1 — Project skeleton

- [ ] **Language and runtime** (e.g. Python 3.11+, Node, etc.)
- [ ] **Dependency management** (`pyproject.toml`, `package.json`, lockfile)
- [ ] **Single entrypoint** (e.g. `python -m cluny` or `npm start`)
- [ ] **Configuration** (env vars, optional config file; no secrets in git)
- [ ] **`.env.example`** documenting required keys (no real secrets)
- [ ] **Basic logging** (structured or plain; levels for debug vs prod)

---

## Phase 2 — Model and conversation loop

- [ ] **Chat/completions client** for your provider (OpenAI-compatible or native SDK)
- [ ] **Message schema** (system / user / assistant / tool roles; timestamps optional)
- [ ] **Streaming** (optional but recommended for UX)
- [ ] **Retries and backoff** on transient API errors
- [ ] **Token or length limits** (truncate history or summarize when needed)
- [ ] **Cost/telemetry hooks** (optional: log usage per request)

---

## Phase 3 — Tools (function calling)

- [ ] **Tool registry** (name, description, JSON schema for arguments)
- [ ] **Executor** that maps tool name → Python/async function (or subprocess with guards)
- [ ] **Tool loop**: model requests tool → you run it → feed result back → repeat until done
- [ ] **Timeouts and output size limits** for tool results
- [ ] **Allowlist** of commands/paths if tools touch shell or filesystem

---

## Phase 4 — Memory and context

- [ ] **Session memory** (current conversation in RAM)
- [ ] **Optional persistence** (SQLite, JSON, or vector DB for long-term memory)
- [ ] **Policy for what gets stored** (PII, secrets, user opt-in)
- [ ] **Retrieval** (if needed: chunking, embeddings, top-k search)

---

## Phase 5 — Safety and quality

- [ ] **Input validation** on tool arguments and user uploads
- [ ] **Secret hygiene** (never log API keys; redact in traces)
- [ ] **Rate limiting** (per user/session if multi-user)
- [ ] **Human-in-the-loop** for destructive or high-risk tools (optional)
- [ ] **Regression tests** for critical tools and the agent loop

---

## Phase 6 — UX polish

- [ ] **Clear errors** to the user when tools or APIs fail
- [ ] **Progress indicators** during long tool runs or streaming
- [ ] **Optional**: slash commands, presets, or “modes” (e.g. plan vs execute)

---

## Prompt checklist (check off as you stabilize behavior)

Use this when drafting or revising **system prompts**, **tool descriptions**, and **user-facing instructions**.

### Identity and scope

- [ ] **Role** is one sentence (“You are …”)
- [ ] **Primary tasks** are listed explicitly
- [ ] **Out of scope** is stated (what to refuse or hand off)

### Reasoning and style

- [ ] **When to think step-by-step** vs answer directly
- [ ] **Tone and verbosity** (concise vs tutorial)
- [ ] **Citation policy** (when to quote sources; avoid fabrication)

### Tools

- [ ] **When to call tools** vs answer from context
- [ ] **One tool at a time vs parallel** (match your runtime)
- [ ] **What to do if a tool fails** (retry, explain, ask user)
- [ ] **Each tool description** states purpose, inputs, and failure modes in plain language

### Safety and privacy

- [ ] **No secrets** in prompts or logs
- [ ] **User data** handling is aligned with your policy
- [ ] **Destructive actions** require confirmation if applicable

### Evaluation

- [ ] **5–10 golden prompts** you rerun after prompt changes
- [ ] **Edge cases** (empty input, ambiguous request, tool timeout)
- [ ] **Version or date** noted when you change the system prompt (changelog or git)

---

## Optional later

- [ ] Multi-agent or supervisor pattern
- [ ] Eval harness (CI or nightly runs on golden set)
- [ ] Observability (OpenTelemetry, Langfuse, or similar)
- [ ] Packaging (Docker) for deployment
