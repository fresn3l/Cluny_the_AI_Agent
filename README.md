# Cluny_the_AI_Agent

Local-first **second brain**: index PDFs, notes, and journal-style files into a **SQLite catalog** plus a **local vector index**, then ask questions with **Ollama** (no cloud LLM required). Everything lives under `.cluny/` by default.

## Prerequisites

- Python **3.11+**
- [Ollama](https://ollama.com/) running locally

Pull models once:

```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```

Adjust names in `.env` if you prefer other models.

## Setup

```bash
cd Cluny_the_AI_Agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

### Moved the project folder?

- Recreate or reinstall the virtualenv and run **`pip install -e .` again** from the new path (editable installs remember the old directory).
- Default **`.cluny`** is resolved **next to `pyproject.toml`**, so you can run `cluny` from subfolders without writing data to the wrong place.
- **`.env`** is loaded from the repo root first (then the current directory). If you used an **absolute** `CLUNY_DATA_DIR`, update it to the new location—or use the default relative `.cluny`.
- Copy your old **`.cluny`** directory into the repo if you want to keep the existing index and SQLite catalog.

## Usage

### Add files to your library (recommended)

Registers the document in **`library.sqlite`** and indexes chunks into Chroma for search.

Supported extensions: **`.pdf`**, **`.md`**, **`.txt`**, **`.journal`** (same as text).

```bash
cluny add ~/Research/paper.pdf --title "Smith 2024 — attention limits"
cluny add ./journal/2026-05-01.md --title "Journal — travel prep"
```

Keep a **stable backup copy** inside your data directory (deduped by content hash):

```bash
cluny add ./article.pdf --copy
```

List everything in the catalog:

```bash
cluny library list
```

**Batch a whole folder** (every `.pdf`, `.md`, `.txt`, `.journal` under the path; skips dot-folders like `.git` unless you pass `--include-hidden`):

```bash
cluny add-dir ~/Research/papers
cluny add-dir ./notes --flat                 # only files directly in ./notes
cluny add-dir ~/Inbox --copy --fail-fast    # stop on first error
```

By default, **`--relative-titles`** uses paths like `subdir/paper.pdf` as the catalog title so names stay unique.

The legacy command **`cluny ingest`** does the same indexing without `--copy` (still writes to the SQLite catalog).

### Paste text (no catalog row)

```bash
cluny ingest-text "Quick capture..." --source "inline-note"
```

### Ask questions (RAG)

```bash
cluny ask "What did the Smith paper say about working memory?"
```

### Stats

```bash
cluny stats
```

Shows chunk count (vectors) and document count (SQLite).

## Where data lives

| Piece | Location (default) |
|--------|---------------------|
| SQLite catalog | `.cluny/library/library.sqlite` by default; folder via `CLUNY_CATALOG_DIR` (e.g. `BRAIN`); filename via `CLUNY_LIBRARY_SQLITE` (e.g. `brain.sqlite`) |
| Managed file copies (`--copy`) | `<CLUNY_DATA_DIR>/<CLUNY_CATALOG_DIR>/files/<sha256>.pdf` |
| Vector index (Chroma) | `.cluny/chroma/` |

Set `CLUNY_DATA_DIR` in `.env` to move the whole tree (e.g. an external drive).

## PDF notes

- Text is extracted from the PDF **text layer**. Scanned pages only contain images — you’ll see an error until you add OCR (not included yet).
- Very large PDFs are split into overlapping **chunks** before embedding.

## Privacy

- Embeddings and chat go to **your machine** via Ollama.
- Back up `CLUNY_DATA_DIR` if you care about the catalog and index.

## Docs

- `Agent_goals.md` — product goals  
- `BUILD_CHECKLIST.md` — engineering checklist  
