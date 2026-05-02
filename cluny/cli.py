"""CLI for ingesting notes and asking questions (local Ollama only)."""

from __future__ import annotations

from pathlib import Path

import typer

from cluny.config import Settings, load_dotenv_if_present
from cluny.documents import add_file, add_url
from cluny.extract import ExtractionError, list_ingestable_files
from cluny.ingest import ingest_string
from cluny.library_db import DocumentRow, connect, document_count, list_documents
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.store import get_collection, query_raw

app = typer.Typer(help="Cluny — local second brain (Ollama + Chroma).")

library_app = typer.Typer(help="Browse the SQLite document catalog.")
app.add_typer(library_app, name="library")


@app.command()
def add(
    path: Path = typer.Argument(..., help="PDF, Markdown, plain text, or .journal file."),
    title: str | None = typer.Option(
        None,
        "--title",
        "-t",
        help="Human-readable title stored in the catalog (defaults to filename).",
    ),
    copy: bool = typer.Option(
        False,
        "--copy",
        "-c",
        help="Copy the file into the managed library folder under your data dir (good for backups).",
    ),
    chunk_size: int = typer.Option(1200, help="Max characters per chunk."),
    overlap: int = typer.Option(200, help="Overlap between consecutive chunks."),
    pdf_ocr: str | None = typer.Option(
        None,
        "--pdf-ocr",
        help="Override CLUNY_PDF_OCR for PDFs: auto | always | never.",
    ),
) -> None:
    """Register a file in the local library DB and index it for search."""
    settings = Settings.from_env()
    collection = get_collection(settings)
    ollama = OllamaClient(settings)

    try:
        doc_id, n = add_file(
            settings,
            collection,
            ollama,
            path,
            copy_into_library=copy,
            title=title,
            chunk_size=chunk_size,
            overlap=overlap,
            pdf_ocr=pdf_ocr,
        )
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    except ExtractionError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"Indexed {n} chunk(s). doc_id={doc_id}")


@app.command("add-url")
def add_url_cmd(
    url: str = typer.Argument(..., help="Web page (HTML) or direct PDF URL."),
    title: str | None = typer.Option(
        None,
        "--title",
        "-t",
        help="Catalog title (defaults to article title or URL).",
    ),
    chunk_size: int = typer.Option(1200),
    overlap: int = typer.Option(200),
) -> None:
    """Fetch a URL, extract main article text or PDF, index with source URL metadata."""
    settings = Settings.from_env()
    collection = get_collection(settings)
    ollama = OllamaClient(settings)

    try:
        doc_id, n = add_url(
            settings,
            collection,
            ollama,
            url,
            title=title,
            chunk_size=chunk_size,
            overlap=overlap,
        )
    except ExtractionError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"Indexed {n} chunk(s) from URL. doc_id={doc_id}")


@app.command("add-dir")
def add_dir(
    directory: Path = typer.Argument(..., help="Folder to scan for PDF / Markdown / text / journal files."),
    recursive: bool = typer.Option(
        True,
        "--recursive/--flat",
        "-r/",
        help="Scan subfolders (default) or only the top-level directory.",
    ),
    copy: bool = typer.Option(
        False,
        "--copy",
        "-c",
        help="Same as cluny add --copy for every file.",
    ),
    relative_titles: bool = typer.Option(
        True,
        "--relative-titles/--basename-titles",
        help="Use paths relative to DIRECTORY as catalog titles (recommended for trees).",
    ),
    include_hidden: bool = typer.Option(
        False,
        "--include-hidden",
        help="Also ingest files inside dot-folders (e.g. .git is still skipped by extension).",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop on the first file that errors.",
    ),
    chunk_size: int = typer.Option(1200),
    overlap: int = typer.Option(200),
    pdf_ocr: str | None = typer.Option(
        None,
        "--pdf-ocr",
        help="Override CLUNY_PDF_OCR for PDFs in this folder.",
    ),
) -> None:
    """Ingest every supported file under a directory (batch `cluny add`)."""
    settings = Settings.from_env()
    collection = get_collection(settings)
    ollama = OllamaClient(settings)

    try:
        files = list_ingestable_files(
            directory,
            recursive=recursive,
            include_hidden=include_hidden,
        )
    except ExtractionError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    if not files:
        typer.echo("No matching files (.pdf, .md, .txt, .journal, …).")
        raise typer.Exit(code=0)

    root = directory.expanduser().resolve()
    ok = 0
    failed = 0
    for path in files:
        title: str | None
        if relative_titles:
            try:
                title = path.relative_to(root).as_posix()
            except ValueError:
                title = path.name
        else:
            title = None

        try:
            _, n = add_file(
                settings,
                collection,
                ollama,
                path,
                copy_into_library=copy,
                title=title,
                chunk_size=chunk_size,
                overlap=overlap,
                pdf_ocr=pdf_ocr,
            )
        except (FileNotFoundError, ExtractionError, OllamaError) as e:
            failed += 1
            typer.echo(f"[skip] {path}: {e}", err=True)
            if fail_fast:
                raise typer.Exit(code=1) from e
            continue
        ok += 1
        typer.echo(f"[ok] {n} chunks  {title or path.name}")

    typer.echo(f"Done. Indexed {ok} file(s), {failed} skipped/failed.")


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="PDF, Markdown, or plain text file."),
    chunk_size: int = typer.Option(1200, help="Max characters per chunk."),
    overlap: int = typer.Option(200, help="Overlap between consecutive chunks."),
    pdf_ocr: str | None = typer.Option(
        None,
        "--pdf-ocr",
        help="Override CLUNY_PDF_OCR for PDFs: auto | always | never.",
    ),
) -> None:
    """Same as `add` without --copy (kept for backward compatibility)."""
    settings = Settings.from_env()
    collection = get_collection(settings)
    ollama = OllamaClient(settings)

    try:
        doc_id, n = add_file(
            settings,
            collection,
            ollama,
            path,
            copy_into_library=False,
            title=None,
            chunk_size=chunk_size,
            overlap=overlap,
            pdf_ocr=pdf_ocr,
        )
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    except ExtractionError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"Indexed {n} chunk(s) from {path} (doc_id={doc_id})")


@app.command("ingest-text")
def ingest_text(
    text: str = typer.Argument(..., help="Raw text to index."),
    source: str = typer.Option(
        "inline",
        "--source",
        "-s",
        help="Short label stored as metadata (e.g. book title).",
    ),
    chunk_size: int = typer.Option(1200),
    overlap: int = typer.Option(200),
) -> None:
    """Index a string (paste, shell heredoc, etc.). Not stored in the SQLite catalog."""
    settings = Settings.from_env()
    collection = get_collection(settings)
    ollama = OllamaClient(settings)

    try:
        n = ingest_string(
            collection,
            ollama,
            text,
            source_label=source,
            max_chars=chunk_size,
            overlap=overlap,
        )
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    typer.echo(f"Indexed {n} chunk(s) under source={source!r}")


@app.command()
def ask(
    question: str = typer.Argument(...),
    k: int = typer.Option(5, help="Number of chunks to retrieve."),
) -> None:
    """Ask using retrieved context (RAG)."""
    settings = Settings.from_env()
    collection = get_collection(settings)
    ollama = OllamaClient(settings)

    try:
        q_emb = ollama.embed(question)
        raw = query_raw(collection, q_emb, n_results=k)
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]

    if not docs:
        typer.echo(
            "No documents in the index yet. Use `cluny add` or `cluny ingest-text` first.",
            err=True,
        )
        raise typer.Exit(code=1)

    context_blocks: list[str] = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        src = ""
        if isinstance(meta, dict):
            src = str(meta.get("source", ""))
            surl = meta.get("source_url")
            if surl:
                src = f"{src} | {surl}" if src else str(surl)
        prefix = f"[{src}]\n" if src else ""
        context_blocks.append(f"{prefix}{doc}")

    context = "\n\n---\n\n".join(context_blocks)
    system = (
        "You are Cluny, a helpful assistant. Answer using the provided context snippets. "
        "If the answer is not in the context, say you do not have that information in the "
        "indexed notes. Be concise and cite which snippet supports each claim when possible."
    )
    user = f"Context from indexed notes:\n\n{context}\n\nQuestion: {question}"

    try:
        answer = ollama.chat(system=system, user=user)
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    typer.echo(answer)


@app.command()
def stats() -> None:
    """Show how many chunks are stored."""
    settings = Settings.from_env()
    collection = get_collection(settings)
    n = collection.count()
    conn = connect(settings)
    nd = document_count(conn)
    conn.close()
    typer.echo(f"Chunks in vector index: {n}")
    typer.echo(f"Documents in library DB: {nd}")
    typer.echo(f"Data directory: {settings.data_dir}")
    typer.echo(f"Chat model: {settings.chat_model} | Embed model: {settings.embed_model}")


def _format_doc_row(d: DocumentRow) -> str:
    title = d.title or "(no title)"
    return f"{d.id[:8]}…  {d.kind:9}  chunks={d.chunk_count:4}  {title}\n    {d.path}"


@library_app.command("list")
def library_list() -> None:
    """List documents registered in the SQLite catalog."""
    settings = Settings.from_env()
    conn = connect(settings)
    rows = list_documents(conn)
    conn.close()
    if not rows:
        typer.echo("No documents in the library catalog yet. Use `cluny add`.")
        return
    for d in rows:
        typer.echo(_format_doc_row(d))


def main() -> None:
    load_dotenv_if_present()
    app()


if __name__ == "__main__":
    main()
