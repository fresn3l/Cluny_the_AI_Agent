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

**Easiest (recommended if `source .venv/bin/activate` does not put `cluny` on your PATH):**

```bash
cd Cluny_the_AI_Agent
chmod +x setup_venv.sh run_cluny.sh
./setup_venv.sh
cp .env.example .env
./run_cluny.sh stats
./run_cluny.sh ask "What is indexed in Cluny?"
```

Manual venv:

```bash
cd Cluny_the_AI_Agent
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e .
cp .env.example .env
```

Then either `./run_cluny.sh …` or `source .venv/bin/activate` and `cluny …`. If `cluny` is “not found” after activate, your shell left Homebrew’s Python first on `PATH` — keep using **`./run_cluny.sh`**.

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

### URLs (HTML or PDF)

Fetches a page, extracts the main article with **trafilatura** (HTML) or the text layer / **OCR** (PDF), and stores **`source_url`**, fetch time, and MIME type in chunk metadata.

```bash
cluny add-url "https://example.com/article"
cluny add-url "https://arxiv.org/pdf/…" --title "Paper title"
```

**Rules** (see `.env.example`): `CLUNY_URL_MODE=open` (default) or `restricted` with `CLUNY_URL_ALLOWLIST`, optional `CLUNY_URL_BLOCKLIST`, `CLUNY_URL_MAX_BYTES`, `CLUNY_URL_TIMEOUT_SEC`.

### Scanned PDFs (OCR)

For local PDFs, `CLUNY_PDF_OCR=auto` tries a normal text layer first, then **Tesseract** via PyMuPDF if the layer is empty. Set `always` to OCR every page, or `never` to reject scans. Install **Tesseract** on the system (e.g. `brew install tesseract`) in addition to Python deps.

```bash
cluny add scan.pdf
cluny add scan.pdf --pdf-ocr always
```

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
