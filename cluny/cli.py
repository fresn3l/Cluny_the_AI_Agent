"""CLI for ingesting notes and asking questions (local Ollama only)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import typer

from cluny.agent import run_agent
from cluny.backup import export_data, restore_data
from cluny.config import Settings, load_dotenv_if_present
from cluny.documents import add_file, add_url, delete_document
from cluny.eval import default_golden_path, default_report_path, load_cases, run_eval, write_report
from cluny.extract import ExtractionError, list_ingestable_files
from cluny.ingest import ingest_string
from cluny.library_db import (
    DocumentRow,
    add_tag_to_doc,
    connect,
    document_count,
    get_tags_for_doc,
    list_documents,
    list_tags,
    resolve_document,
)
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.query import rag_answer, rag_answer_stream, retrieve
from cluny.store import get_collection
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
app.add_typer(library_app, name="library")
app.add_typer(tag_app, name="tag")
app.add_typer(tasks_app, name="tasks")


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

    if isinstance(n, tuple):
        n = n[0]
    typer.echo(f"Indexed {n} chunk(s) under source={source!r}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Retrieval query (no LLM)."),
    k: int = typer.Option(5, help="Number of chunks to retrieve."),
) -> None:
    """Hybrid search over indexed chunks (debug / retrieval-only)."""
    try:
        chunks = retrieve(query, k=k)
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
) -> None:
    """Ask using retrieved context (RAG)."""
    try:
        if no_stream:
            result = rag_answer(question, k=k)
            if result.empty_index:
                typer.echo(result.answer, err=True)
                raise typer.Exit(code=1)
            typer.echo(result.answer)
            return

        stream, sources, empty = rag_answer_stream(question, k=k)
        if empty:
            msg = "".join(stream)
            typer.echo(msg, err=True)
            raise typer.Exit(code=1)
        for token in stream:
            typer.echo(token, nl=False)
        typer.echo()
        if sources:
            typer.echo("\nSources:")
            for s in sources:
                typer.echo(f"  • {s.label}")
    except OllamaError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e


@app.command()
def agent(
    question: str = typer.Argument(..., help="Question for the tool-calling agent."),
    mode: str = typer.Option(
        "knowledge",
        "--mode",
        "-m",
        help="Tool namespace: knowledge | tasks | all",
    ),
) -> None:
    """Ask using the agent loop (search_brain / add_note / task tools)."""
    if mode not in ("knowledge", "tasks", "all"):
        typer.echo("mode must be knowledge, tasks, or all", err=True)
        raise typer.Exit(code=1)
    try:
        result = run_agent(question, mode=mode)  # type: ignore[arg-type]
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
) -> None:
    """Export catalog, vectors, and optional managed copies to a zip archive."""
    settings = Settings.from_env()
    try:
        path = export_data(out, settings, include_files=not no_files)
    except OSError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"Exported to {path}")


@app.command()
def import_data(
    archive: Path = typer.Argument(..., help="Cluny export .zip to restore."),
    merge: bool = typer.Option(
        False,
        "--merge",
        help="Merge into existing data dir instead of replacing chroma/sqlite.",
    ),
) -> None:
    """Restore catalog and vector index from a Cluny export archive."""
    settings = Settings.from_env()
    try:
        restore_data(archive, settings, merge=merge)
    except (FileNotFoundError, OSError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"Restored from {archive} into {settings.data_dir}")


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
) -> None:
    """List documents registered in the SQLite catalog."""
    settings = Settings.from_env()
    conn = connect(settings)
    rows = list_documents(conn, tag=tag)
    for d in rows:
        tags = get_tags_for_doc(conn, d.id)
        typer.echo(_format_doc_row(d, tags))
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
    return f"{t.id[:8]}…  [{t.status:4}]  {t.title}{due}"


@tasks_app.command("add")
def tasks_add(
    title: str = typer.Argument(..., help="Task title."),
    due: str | None = typer.Option(None, "--due", "-d", help="Due date (free text or ISO)."),
    notes: str | None = typer.Option(None, "--notes", "-n"),
    project: str | None = typer.Option(None, "--project", "-p"),
) -> None:
    """Add a new open task."""
    settings = Settings.from_env()
    conn = tasks_connect(settings)
    task = db_create_task(conn, title, due_at=due, notes=notes, project_id=project)
    conn.close()
    typer.echo(f"Created task {task.id[:8]}…  {task.title}")


@tasks_app.command("list")
def tasks_list(
    status: str | None = typer.Option(None, "--status", "-s", help="open or done"),
) -> None:
    """List tasks."""
    settings = Settings.from_env()
    conn = tasks_connect(settings)
    rows = db_list_tasks(conn, status=status)
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


def main() -> None:
    load_dotenv_if_present()
    app()


if __name__ == "__main__":
    main()
