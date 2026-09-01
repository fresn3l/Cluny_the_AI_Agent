# Sprint 12 — Standalone Cluny App (macOS)

**Goal:** Double-clickable Mac menu-bar app that talks to the brain over HTTP (`127.0.0.1:8787`), auto-starts `cluny serve`, and aligns the widget with Kosistenz’s thin-client model.

## Locked decisions

| Area | Choice |
|------|--------|
| Packaging | **py2app** (Mac-native `.app`) |
| Default UX | **Menu bar only** + one-time welcome (“Open library” / “Stay in menu bar”) |
| Brain | **HTTP** to local serve; app manages lifecycle |
| Tasks | **Propose** tab by default; **Task** tab when `standalone_mode` |

## Phases

### A — Brain lifecycle ✅ (this branch)
- [x] `cluny/app_mode.py` — packaged detection, App Support data dir, default `CLUNY_BRAIN_URL`
- [x] `cluny/brain_service.py` — ensure serve running, health probe
- [x] Widget startup calls `ensure_brain_running()`

### B — Widget thin client
- [x] Streaming Ask via `/chat/stream`
- [x] Propose tab (`POST /propose`)
- [x] Collection dropdown
- [x] Brain status in panel + tray tooltip
- [ ] Session id persistence in widget (optional follow-up)

### C — First-run polish
- [x] Welcome dialog (first launch once)
- [x] `standalone_mode` in user config (Task vs Propose tab)

### D — py2app ship
- [x] `macos/setup_py2app.py` + `build_py2app.sh`
- [x] `macos/py2app_options.py` — hidden imports, Qt plugins, excludes
- [x] `macos/verify_bundle.py` — post-build import/size check
- [x] `macos/create_dmg.sh` — drag-to-Applications DMG
- [ ] Full dependency bake-off on a clean Mac (manual smoke test)

### E — Docs / GUI
- [x] README py2app + DMG instructions
- [x] Full GUI (`cluny gui`) forces HTTP brain when packaged / `CLUNY_USE_HTTP_BRAIN`
- [x] Settings UI toggle for `standalone_mode`

## Test plan

```bash
.venv/bin/python -m pytest tests/test_app_mode.py tests/test_brain_service.py tests/ -q
./macos/build_py2app.sh   # requires: pip install py2app
open dist/Cluny.app
```

## Out of scope

- Windows/Linux (Briefcase later)
- Notarization / App Store
- Kosistenz in-app integration (separate repo)
