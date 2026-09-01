# Cluny — Sprint 10

**Theme:** *“Ask, capture, and glance — without Terminal or the full chat window.”*

**Decision:** One unified **`Cluny.app`** — **Widget mode (default)** + **Full window** from tray menu.

---

## Goals

- Menu bar popover for daily Cluny use (replaces most CLI for ask/capture/tasks).
- Unified app: same process opens full PySide6 window when needed.
- Reuse core: `run_chat`, `add_inline_text`, `create_task`, `Settings.load()`.

---

## Deliverables

| Area | Work | Key files |
|------|------|-----------|
| **Widget entry** | `cluny widget` | `cluny/widget/app.py`, `cluny/cli.py` |
| **Menu bar + popover** | Tray icon, 420×520 panel | `cluny/widget/tray.py`, `cluny/widget/panel.py` |
| **Ask tab** | Supervisor chat auto-route, route badge | `cluny/widget/workers.py` |
| **Capture tab** | `add_inline_text` catalog capture | `cluny/widget/workers.py` |
| **Task tab** | Title + due → `create_task` | `cluny/widget/workers.py` |
| **Glance tab** | Docs, chunks, due-week tasks, next event | `cluny/widget/glance.py` |
| **Unified app** | `Cluny.app` → widget; tray → full window | `macos/cluny-gui`, `macos/Info.plist` |
| **Tests** | Glance helpers (no Qt in CI) | `tests/test_widget.py` |

---

## Acceptance criteria

- `cluny widget` shows menu bar icon; click opens popover.
- Ask tab returns `[route: …]` and answer via supervisor.
- Capture indexes text with catalog registration.
- Task tab creates task visible in `cluny tasks list --due-week`.
- Glance loads without Ollama.
- Tray → “Open full window” opens existing MainWindow in same process.
- `./macos/install_app.sh` installs unified app (LSUIElement, no Dock tile by default).

---

## Explicitly deferred (Sprint 10.1+)

- Global hotkey
- Selection capture
- WidgetKit Home Screen widget
- Auto-start `cluny serve`
