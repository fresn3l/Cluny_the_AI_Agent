"""CLI for ingesting notes and asking questions (local Ollama only)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import typer

from cluny.agent import run_agent
from cluny.backup import export_data, restore_data, run_scheduled_backup
from cluny.config import Settings, load_dotenv_if_present
from cluny.documents import add_file, add_inline_text, add_url, delete_document
from cluny.eval import default_golden_path, default_report_path, load_cases, run_eval, write_report
from cluny.extract import ExtractionError, list_ingestable_files
from cluny.ingest import ingest_string
from cluny.library_db import (
    DocumentRow,
    add_doc_to_collection,
    add_tag_to_doc,
    connect,
    create_collection,
    doc_ids_in_collection,
    document_count,
    duplicate_hash_groups,
    get_collections_for_doc,
    get_tags_for_doc,
    list_collections,
    list_documents,
    list_tags,
    resolve_document,
)
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.query import rag_answer, rag_answer_stream, retrieve
from cluny.sessions import add_message, connect as sessions_connect, get_or_create_last_session
from cluny.store import get_collection
from cluny.supervisor import run_chat
from cluny.tasks_db import (
    TaskRow,
    complete_task as db_complete_task,
    connect as tasks_connect,
    create_task as db_create_task,
    delete_task as db_delete_task,
    list_tasks as db_list_tasks,
    resolve_task,
    update_task as db_update_task,
)
from cluny.watcher import watch_directory

app = typer.Typer(help="Cluny — local second brain (Ollama + Chroma).")

library_app = typer.Typer(help="Browse the SQLite document catalog.")
tag_app = typer.Typer(help="Tag documents for organization.")
tasks_app = typer.Typer(help="Manage tasks (separate from knowledge index).")
collection_app = typer.Typer(help="Organize documents into collections.")
calendar_app = typer.Typer(help="Read-only calendar from imported ICS files.")
backup_app = typer.Typer(help="Backup and restore data snapshots.")
app.add_typer(library_app, name="library")
app.add_typer(tag_app, name="tag")
app.add_typer(tasks_app, name="tasks")
app.add_typer(collection_app, name="collection")
app.add_typer(calendar_app, name="calendar")
app.add_typer(backup_app, name="backup")


def _echo_index_result(n: int, doc_id: str, unchanged: bool) -> None:
    if unchanged:
        typer.echo(f"Unchanged (skipped re-embed). doc_id={doc_id} chunks={n}")
    else:
        typer.echo(f"Indexed {n} chunk(s). doc_id={doc_id}")


@app.command()
def add(
    path: Path = typer.Argument(..., help="PDF, Markdown, plain text, JSON, or .journal file."),
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
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Replace other catalog entries with the same content hash.",
    ),
) -> None:
    """Register a file in the local library DB and index it for search."""
    settings = Settings.from_env()
    collection = get_collection(settings)
    ollama = OllamaClient(settings)

    try:
        result = add_file(
            settings,
            collection,
            ollama,
            path,
            copy_into_library=copy,
            title=title,
            chunk_size=chunk_size,
            overlap=overlap,
            pdf_ocr=pdf_ocr,
            replace=replace,
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

    _echo_index_result(result.chunk_count, result.doc_id, result.unchanged)


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
        result = add_url(
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

    _echo_index_result(result.chunk_count, result.doc_id, result.unchanged)
    if not result.unchanged:
        typer.echo(f"Source URL indexed.")


@app.command("add-dir")
def add_dir(
    directory: Path = typer.Argument(..., help="Folder to scan for PDF / Markdown / text / JSON / journal files."),
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
        typer.echo("No matching files (.pdf, .md, .txt, .json, .journal, …).")
        raise typer.Exit(code=0)

    root = directory.expanduser().resolve()
    ok = 0
    skipped = 0
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
            result = add_file(
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
        if result.unchanged:
            skipped += 1
            typer.echo(f"[unchanged] {title or path.name}")
        else:
            ok += 1
            typer.echo(f"[ok] {result.chunk_count} chunks  {title or path.name}")

    typer.echo(f"Done. Indexed {ok} file(s), {skipped} unchanged, {failed} skipped/failed.")


@app.command()
def watch(
    directory: Path | None = typer.Argument(
        None,
        help="Folder to watch (default: CLUNY_WATCH_PATH). Same ingest rules as add-dir.",
    ),
    debounce: float = typer.Option(
        1.5,
        "--debounce",
        "-d",
        min=0.2,
        help="Seconds to wait after file activity before re-indexing (batches rapid saves).",
    ),
    include_hidden: bool = typer.Option(
        False,
        "--include-hidden",
        help="Also ingest files inside dot-folders.",
    ),
    chunk_size: int = typer.Option(1200),
    overlap: int = typer.Option(200),
    pdf_ocr: str | None = typer.Option(
        None,
        "--pdf-ocr",
        help="Override CLUNY_PDF_OCR for PDFs in this tree.",
    ),
) -> None:
    """Watch a directory and re-index when files are added or changed (Ctrl+C to stop)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings.from_env()
    root = directory
    if root is None:
        raw = os.environ.get("CLUNY_WATCH_PATH", "").strip()
        root = Path(raw).expanduser() if raw else None
    if root is None:
        typer.echo(
            "Pass a DIRECTORY or set CLUNY_WATCH_PATH in the environment.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        watch_directory(
            root,
            settings,
            debounce_sec=debounce,
            chunk_size=chunk_size,
            overlap=overlap,
            pdf_ocr=pdf_ocr,
            include_hidden=include_hidden,
        )
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    except RuntimeError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e


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
        result = add_file(
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

    _echo_index_result(result.chunk_count, result.doc_id, result.unchanged)


@app.command("ingest-text")
def ingest_text(
    text: str = typer.Argument(..., help="Raw text to index."),
    source: str = typer.Option(
        "inline",
        "--source",
        "-s",
        help="Short label stored as metadata (e.g. book title).",
    ),
    catalog: bool = typer.Option(
        False,
        "--catalog",
        help="Register in SQLite catalog as kind=inline (not orphan chunks).",
    ),
    title: str | None = typer.Option(None, "--title", "-t", help="Catalog title when --catalog."),
    chunk_size: int = typer.Option(1200),
    overlap: int = typer.Option(200),
) -> None:
    """Index a string (paste, shell heredoc, etc.)."""
    settings = Settings.load()
    collection = get_collection(settings)
    ollama = OllamaClient(settings)

    try:
        if catalog:
            result = add_inline_text(
                settings,
                collection,
                ollama,
                text,
                source_label=source,
                title=title,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            _echo_index_result(result.chunk_count, result.doc_id, result.unchanged)
            return

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

    if isinstance(n, tuple):
        n = n[0]
    typer.echo(f"Indexed {n} chunk(s) under source={source!r}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Retrieval query (no LLM)."),
    k: int = typer.Option(5, help="Number of chunks to retrieve."),
    collection: str | None = typer.Option(
        None, "--collection", "-c", help="Limit to a named collection."
    ),
) -> None:
    """Hybrid search over indexed chunks (debug / retrieval-only)."""
    settings = Settings.from_env()
    doc_ids = None
    if collection:
        conn = connect(settings)
        doc_ids = doc_ids_in_collection(conn, collection)
        conn.close()
        if not doc_ids:
            typer.echo(f"No documents in collection {collection!r}.", err=True)
            raise typer.Exit(code=1)
    try:
        chunks = retrieve(query, k=k, settings=settings, doc_ids=doc_ids)
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    if not chunks:
        typer.echo("No results.")
        raise typer.Exit(code=1)

    for i, ch in enumerate(chunks, 1):
        typer.echo(f"\n--- [{i}] score={ch.score:.4f}  {ch.label} ---")
        if ch.doc_path:
            typer.echo(f"path: {ch.doc_path}")
        preview = ch.text.strip().replace("\n", " ")
        if len(preview) > 500:
            preview = preview[:499] + "…"
        typer.echo(preview)


@app.command()
def ask(
    question: str = typer.Argument(...),
    k: int = typer.Option(5, help="Number of chunks to retrieve."),
    no_stream: bool = typer.Option(
        False,
        "--no-stream",
        help="Wait for the full answer instead of streaming tokens.",
    ),
    session: bool = typer.Option(
        False,
        "--session",
        help="Append question/answer to the persistent chat session.",
    ),
) -> None:
    """Ask using retrieved context (RAG)."""
    settings = Settings.load()
    sess_conn = None
    session_id = None
    if session:
        sess_conn = sessions_connect(settings)
        session_id = get_or_create_last_session(sess_conn)
        add_message(sess_conn, session_id, "user", question)
    try:
        if no_stream:
            result = rag_answer(question, k=k, settings=settings)
            if result.empty_index:
                typer.echo(result.answer, err=True)
                raise typer.Exit(code=1)
            typer.echo(result.answer)
            if sess_conn and session_id:
                add_message(sess_conn, session_id, "assistant", result.answer)
            return

        stream, sources, empty = rag_answer_stream(question, k=k, settings=settings)
        if empty:
            msg = "".join(stream)
            typer.echo(msg, err=True)
            raise typer.Exit(code=1)
        parts: list[str] = []
        for token in stream:
            typer.echo(token, nl=False)
            parts.append(token)
        typer.echo()
        answer = "".join(parts)
        if sess_conn and session_id:
            add_message(sess_conn, session_id, "assistant", answer)
        if sources:
            typer.echo("\nSources:")
            for s in sources:
                typer.echo(f"  • {s.label}")
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    finally:
        if sess_conn:
            sess_conn.close()


@app.command()
def chat(
    question: str = typer.Argument(..., help="Question routed by intent classifier."),
) -> None:
    """Supervisor entrypoint — routes to ask, knowledge agent, tasks, or calendar."""
    try:
        result = run_chat(question, settings=Settings.load())
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"[route: {result.route}]")
    if result.tool_calls:
        typer.echo("Tools: " + "; ".join(result.tool_calls))
    typer.echo(result.answer)


@app.command()
def agent(
    question: str = typer.Argument(..., help="Question for the tool-calling agent."),
    mode: str = typer.Option(
        "knowledge",
        "--mode",
        "-m",
        help="Tool namespace: knowledge | tasks | all | planner",
    ),
) -> None:
    """Ask using the agent loop (search_brain / add_note / task tools)."""
    if mode not in ("knowledge", "tasks", "all", "planner"):
        typer.echo("mode must be knowledge, tasks, all, or planner", err=True)
        raise typer.Exit(code=1)
    try:
        result = run_agent(question, mode=mode, settings=Settings.load())  # type: ignore[arg-type]
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    if result.tool_calls:
        typer.echo("Tools used: " + "; ".join(result.tool_calls))
        typer.echo()
    typer.echo(result.answer)


@app.command("eval")
def eval_run(
    golden: Path | None = typer.Option(
        None,
        "--golden",
        "-g",
        help="Path to golden.yaml (default: eval/golden.yaml in repo).",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write JSON report to this path.",
    ),
    retrieval_only: bool = typer.Option(
        False,
        "--retrieval-only",
        help="Skip LLM answers; check retrieval hits only.",
    ),
    fts_only: bool = typer.Option(
        False,
        "--fts-only",
        help="FTS retrieval only (no Ollama embeddings; for CI).",
    ),
) -> None:
    """Run golden questions and report pass/fail (RAG regression harness)."""
    path = golden or default_golden_path()
    if not path.is_file():
        typer.echo(f"Golden file not found: {path}", err=True)
        raise typer.Exit(code=1)

    cases = load_cases(path)
    if len(cases) < 1:
        typer.echo("No cases in golden file.", err=True)
        raise typer.Exit(code=1)

    try:
        report = run_eval(cases, skip_llm=retrieval_only, fts_only=fts_only)
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    typer.echo(
        f"Eval: {report.passed}/{report.total} passed | "
        f"retrieval_hit={report.retrieval_hit_rate:.0%} | "
        f"avg_latency={report.avg_latency_ms:.0f}ms ({report.run_at})"
    )
    if report.refusal_rate is not None:
        typer.echo(f"  refusal_rate={report.refusal_rate:.0%}")
    for case in report.cases:
        status = "PASS" if case.passed else "FAIL"
        q = case.question if len(case.question) <= 60 else case.question[:57] + "…"
        typer.echo(f"  [{status}] {q} ({case.latency_ms:.0f}ms)")

    out_path = output or default_report_path()
    write_report(report, out_path)
    typer.echo(f"Report written to {out_path}")

    if report.passed < report.total:
        raise typer.Exit(code=1)


@app.command()
def export(
    out: Path = typer.Argument(..., help="Output .zip path."),
    no_files: bool = typer.Option(
        False,
        "--no-files",
        help="Omit managed file copies from the archive.",
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        help="AES-encrypt the zip (requires pyzipper).",
    ),
) -> None:
    """Export catalog, vectors, and optional managed copies to a zip archive."""
    settings = Settings.load()
    try:
        path = export_data(out, settings, include_files=not no_files, password=password)
    except (OSError, RuntimeError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"Exported to {path}")


@backup_app.command("run")
def backup_run(
    no_files: bool = typer.Option(False, "--no-files", help="Omit managed file copies."),
) -> None:
    """Write a timestamped backup zip to CLUNY_BACKUP_DIR."""
    settings = Settings.load()
    try:
        path = run_scheduled_backup(settings, include_files=not no_files)
    except OSError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"Backup written to {path}")


@app.command()
def import_data(
    archive: Path = typer.Argument(..., help="Cluny export .zip to restore."),
    merge: bool = typer.Option(
        False,
        "--merge",
        help="Merge into existing data dir instead of replacing chroma/sqlite.",
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        help="Password for AES-encrypted archives.",
    ),
) -> None:
    """Restore catalog and vector index from a Cluny export archive."""
    settings = Settings.load()
    try:
        restore_data(archive, settings, merge=merge, password=password)
    except (FileNotFoundError, OSError, RuntimeError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"Restored from {archive} into {settings.data_dir}")


@app.command()
def widget(
    full: bool = typer.Option(
        False,
        "--full",
        help="Also open the full chat window on launch.",
    ),
) -> None:
    """Menu bar widget: compact Ask / Capture / Task / Glance panel."""
    try:
        from cluny.widget.app import run_widget_app
    except ImportError as e:
        typer.echo(
            "PySide6 is required for the widget. Install dependencies: pip install -e .",
            err=True,
        )
        raise typer.Exit(code=1) from e

    run_widget_app(start_full=full)


@app.command()
def gui() -> None:
    """Open the native desktop chat window (PySide6)."""
    try:
        from cluny.gui.app import run_app
    except ImportError as e:
        typer.echo(
            "PySide6 is required for the GUI. Install dependencies: pip install -e .",
            err=True,
        )
        raise typer.Exit(code=1) from e

    run_app()


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


def _format_doc_row(d: DocumentRow, tags: list[str] | None = None) -> str:
    title = d.title or "(no title)"
    tag_str = f"  tags=[{', '.join(tags)}]" if tags else ""
    return f"{d.id[:8]}…  {d.kind:9}  chunks={d.chunk_count:4}  {title}{tag_str}\n    {d.path}"


@library_app.command("list")
def library_list(
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag name."),
    collection: str | None = typer.Option(
        None, "--collection", "-c", help="Filter by collection name."
    ),
) -> None:
    """List documents registered in the SQLite catalog."""
    settings = Settings.from_env()
    conn = connect(settings)
    rows = list_documents(conn, tag=tag, collection=collection)
    for d in rows:
        tags = get_tags_for_doc(conn, d.id)
        colls = get_collections_for_doc(conn, d.id)
        extra = ""
        if tags:
            extra += f"  tags=[{', '.join(tags)}]"
        if colls:
            extra += f"  collections=[{', '.join(colls)}]"
        typer.echo(_format_doc_row(d) + extra)
    conn.close()
    if not rows:
        typer.echo("No documents in the library catalog yet. Use `cluny add`.")


@library_app.command("show")
def library_show(
    identifier: str = typer.Argument(..., help="Document id, id prefix, or catalog path."),
) -> None:
    """Show metadata for one catalog document."""
    settings = Settings.from_env()
    conn = connect(settings)
    doc = resolve_document(conn, identifier)
    if doc is None:
        conn.close()
        typer.echo(f"No document matching: {identifier!r}", err=True)
        raise typer.Exit(code=1)
    tags = get_tags_for_doc(conn, doc.id)
    conn.close()

    typer.echo(f"id:           {doc.id}")
    typer.echo(f"path:         {doc.path}")
    typer.echo(f"kind:         {doc.kind}")
    typer.echo(f"title:        {doc.title or '(none)'}")
    typer.echo(f"content_hash: {doc.content_hash[:16]}…")
    typer.echo(f"size_bytes:   {doc.size_bytes}")
    typer.echo(f"chunk_count:  {doc.chunk_count}")
    typer.echo(f"ingested_at:  {doc.ingested_at}")
    if tags:
        typer.echo(f"tags:         {', '.join(tags)}")


@library_app.command("delete")
def library_delete(
    identifier: str = typer.Argument(..., help="Document id, id prefix, or catalog path."),
    remove_copy: bool = typer.Option(
        False,
        "--remove-copy",
        help="Also delete managed file copy under catalog/files/.",
    ),
) -> None:
    """Remove a document from the catalog and vector index."""
    settings = Settings.from_env()
    collection = get_collection(settings)
    try:
        doc_id = delete_document(
            settings,
            collection,
            identifier,
            remove_managed_copy=remove_copy,
        )
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"Deleted doc_id={doc_id}")


@tag_app.command("add")
def tag_add(
    identifier: str = typer.Argument(..., help="Document id, id prefix, or catalog path."),
    name: str = typer.Argument(..., help="Tag name to attach."),
) -> None:
    """Add a tag to a catalog document."""
    settings = Settings.from_env()
    conn = connect(settings)
    doc = resolve_document(conn, identifier)
    if doc is None:
        conn.close()
        typer.echo(f"No document matching: {identifier!r}", err=True)
        raise typer.Exit(code=1)
    try:
        add_tag_to_doc(conn, doc.id, name)
    except ValueError as e:
        conn.close()
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    conn.close()
    typer.echo(f"Tagged {doc.id[:8]}… with {name!r}")


@tag_app.command("list")
def tag_list() -> None:
    """List all tags in the catalog."""
    settings = Settings.from_env()
    conn = connect(settings)
    tags = list_tags(conn)
    conn.close()
    if not tags:
        typer.echo("No tags yet. Use `cluny tag add`.")
        return
    for t in tags:
        typer.echo(t)


def _format_task(t: TaskRow) -> str:
    due = f"  due={t.due_at}" if t.due_at else ""
    rec = f"  every={t.recurrence}" if t.recurrence else ""
    return f"{t.id[:8]}…  [{t.status:4}]  {t.title}{due}{rec}"


@tasks_app.command("add")
def tasks_add(
    title: str = typer.Argument(..., help="Task title."),
    due: str | None = typer.Option(None, "--due", "-d", help="Due date (tomorrow, +3d, ISO)."),
    notes: str | None = typer.Option(None, "--notes", "-n"),
    project: str | None = typer.Option(None, "--project", "-p"),
    every: str | None = typer.Option(
        None,
        "--every",
        "-e",
        help="Recurrence: daily, weekly, or monthly.",
    ),
) -> None:
    """Add a new open task."""
    if every and every.lower() not in ("daily", "weekly", "monthly"):
        typer.echo("--every must be daily, weekly, or monthly", err=True)
        raise typer.Exit(code=1)
    settings = Settings.load()
    conn = tasks_connect(settings)
    task = db_create_task(
        conn,
        title,
        due_at=due,
        notes=notes,
        project_id=project,
        recurrence=every.lower() if every else None,
    )
    conn.close()
    typer.echo(f"Created task {task.id[:8]}…  {task.title}")


@tasks_app.command("list")
def tasks_list(
    status: str | None = typer.Option(None, "--status", "-s", help="open or done"),
    project: str | None = typer.Option(None, "--project", "-p"),
    due_before: str | None = typer.Option(None, "--due-before", help="Due on or before date."),
    due_week: bool = typer.Option(False, "--due-week", help="Due within the next 7 days."),
) -> None:
    """List tasks."""
    settings = Settings.load()
    conn = tasks_connect(settings)
    rows = db_list_tasks(
        conn,
        status=status,
        project_id=project,
        due_before=due_before,
        due_week=due_week,
    )
    conn.close()
    if not rows:
        typer.echo("No tasks yet. Use `cluny tasks add`.")
        return
    for t in rows:
        typer.echo(_format_task(t))


@tasks_app.command("show")
def tasks_show(identifier: str = typer.Argument(..., help="Task id or prefix.")) -> None:
    """Show one task."""
    settings = Settings.from_env()
    conn = tasks_connect(settings)
    task = resolve_task(conn, identifier)
    conn.close()
    if task is None:
        typer.echo(f"No task matching: {identifier!r}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"id:         {task.id}")
    typer.echo(f"title:      {task.title}")
    typer.echo(f"status:     {task.status}")
    typer.echo(f"due_at:     {task.due_at or '(none)'}")
    typer.echo(f"created_at: {task.created_at}")
    if task.notes:
        typer.echo(f"notes:      {task.notes}")
    if task.project_id:
        typer.echo(f"project_id: {task.project_id}")
    if task.recurrence:
        typer.echo(f"recurrence: {task.recurrence}")


@tasks_app.command("complete")
def tasks_complete(identifier: str = typer.Argument(..., help="Task id or prefix.")) -> None:
    """Mark a task done."""
    settings = Settings.from_env()
    conn = tasks_connect(settings)
    task = resolve_task(conn, identifier)
    if task is None:
        conn.close()
        typer.echo(f"No task matching: {identifier!r}", err=True)
        raise typer.Exit(code=1)
    done = db_complete_task(conn, task.id)
    conn.close()
    assert done is not None
    typer.echo(f"Completed: {done.title}")


@tasks_app.command("update")
def tasks_update(
    identifier: str = typer.Argument(..., help="Task id or prefix."),
    title: str | None = typer.Option(None, "--title", "-t"),
    due: str | None = typer.Option(None, "--due", "-d"),
    notes: str | None = typer.Option(None, "--notes", "-n"),
    status: str | None = typer.Option(None, "--status", "-s"),
) -> None:
    """Update a task."""
    settings = Settings.from_env()
    conn = tasks_connect(settings)
    task = resolve_task(conn, identifier)
    if task is None:
        conn.close()
        typer.echo(f"No task matching: {identifier!r}", err=True)
        raise typer.Exit(code=1)
    updated = db_update_task(
        conn, task.id, title=title, due_at=due, notes=notes, status=status
    )
    conn.close()
    assert updated is not None
    typer.echo(_format_task(updated))


@tasks_app.command("delete")
def tasks_delete(identifier: str = typer.Argument(..., help="Task id or prefix.")) -> None:
    """Delete a task."""
    settings = Settings.from_env()
    conn = tasks_connect(settings)
    task = resolve_task(conn, identifier)
    if task is None:
        conn.close()
        typer.echo(f"No task matching: {identifier!r}", err=True)
        raise typer.Exit(code=1)
    db_delete_task(conn, task.id)
    conn.close()
    typer.echo(f"Deleted task {task.id[:8]}…")


@library_app.command("dedup")
def library_dedup() -> None:
    """Report documents that share the same content hash."""
    settings = Settings.from_env()
    conn = connect(settings)
    groups = duplicate_hash_groups(conn)
    conn.close()
    if not groups:
        typer.echo("No duplicate content hashes in the catalog.")
        return
    for h, docs in groups.items():
        typer.echo(f"\nhash {h[:12]}… ({len(docs)} docs)")
        for d in docs:
            typer.echo(f"  {d.id[:8]}…  {d.title or d.path}")


@collection_app.command("create")
def collection_create(name: str = typer.Argument(...)) -> None:
    """Create a collection."""
    settings = Settings.from_env()
    conn = connect(settings)
    create_collection(conn, name)
    conn.close()
    typer.echo(f"Collection {name!r} ready.")


@collection_app.command("add")
def collection_add(
    identifier: str = typer.Argument(..., help="Document id, prefix, or path."),
    name: str = typer.Argument(..., help="Collection name."),
) -> None:
    """Add a document to a collection."""
    settings = Settings.from_env()
    conn = connect(settings)
    doc = resolve_document(conn, identifier)
    if doc is None:
        conn.close()
        typer.echo(f"No document matching: {identifier!r}", err=True)
        raise typer.Exit(code=1)
    add_doc_to_collection(conn, doc.id, name)
    conn.close()
    typer.echo(f"Added {doc.id[:8]}… to collection {name!r}")


@collection_app.command("list")
def collection_list() -> None:
    """List all collections."""
    settings = Settings.from_env()
    conn = connect(settings)
    names = list_collections(conn)
    conn.close()
    if not names:
        typer.echo("No collections yet. Use `cluny collection create`.")
        return
    for n in names:
        typer.echo(n)


@calendar_app.command("import")
def calendar_import(path: Path = typer.Argument(..., help="ICS file to import.")) -> None:
    """Import calendar events from an ICS file (read-only)."""
    from cluny.calendar_db import import_ics

    settings = Settings.from_env()
    try:
        n = import_ics(path, settings)
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"Imported {n} event(s) from {path}")


@calendar_app.command("list")
def calendar_list() -> None:
    """List imported calendar events."""
    from cluny.calendar_db import connect as cal_connect, list_upcoming

    settings = Settings.from_env()
    conn = cal_connect(settings)
    events = list_upcoming(conn, limit=50)
    conn.close()
    if not events:
        typer.echo("No events. Use `cluny calendar import`.")
        return
    for e in events:
        when = e.start_at or "?"
        typer.echo(f"{when}  {e.summary}")


@app.command()
def serve() -> None:
    """Start the local HTTP API (FastAPI on CLUNY_API_BIND:CLUNY_API_PORT)."""
    try:
        from cluny.api import serve as api_serve
    except ImportError as e:
        typer.echo(
            "FastAPI is required. Install with: pip install -e '.[api]'",
            err=True,
        )
        raise typer.Exit(code=1) from e
    settings = Settings.load()
    typer.echo(f"Serving Cluny API at http://{settings.api_bind_host}:{settings.api_port}")
    api_serve(settings)


def main() -> None:
    load_dotenv_if_present()
    app()


if __name__ == "__main__":
    main()
