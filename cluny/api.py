"""Local HTTP API for Cluny (optional FastAPI dependency)."""

from __future__ import annotations

import json
from typing import Any

from cluny.agent import run_agent
from cluny.config import Settings
from cluny.documents import add_inline_text
from cluny.library_db import connect, list_documents
from cluny.ollama_client import OllamaError
from cluny.query import retrieve
from cluny.query import rag_answer_stream
from cluny.store import get_collection
from cluny.supervisor import run_chat
from cluny.tasks_db import connect as tasks_connect, create_task as db_create_task

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel, Field
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "FastAPI is required for the API. Install with: pip install -e '.[api]'"
    ) from e


class SearchRequest(BaseModel):
    query: str
    k: int = Field(default=5, ge=1, le=50)


class AskRequest(BaseModel):
    question: str
    k: int = Field(default=5, ge=1, le=50)


class IngestTextRequest(BaseModel):
    text: str
    source: str = "inline"
    catalog: bool = False
    title: str | None = None


class TaskCreateRequest(BaseModel):
    title: str
    due_at: str | None = None
    notes: str | None = None
    project_id: str | None = None
    recurrence: str | None = None


class AgentRequest(BaseModel):
    question: str
    mode: str = "knowledge"


class ChatRequest(BaseModel):
    question: str


def _settings() -> Settings:
    return Settings.load()


_LOCALHOST_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def _check_auth(
    request: Request,
    settings: Settings = Depends(_settings),
    authorization: str | None = Header(default=None),
    x_cluny_token: str | None = Header(default=None, alias="X-Cluny-Token"),
) -> None:
    token = settings.api_token
    if not token:
        client_host = request.client.host if request.client else ""
        if client_host not in _LOCALHOST_HOSTS:
            raise HTTPException(status_code=403, detail="Non-localhost access requires CLUNY_API_TOKEN")
        return

    presented = ""
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    elif x_cluny_token:
        presented = x_cluny_token.strip()
    if presented != token:
        raise HTTPException(status_code=401, detail="Invalid API token")


def create_app() -> FastAPI:
    app = FastAPI(title="Cluny API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/search", dependencies=[Depends(_check_auth)])
    def search(body: SearchRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        try:
            chunks = retrieve(body.query, k=body.k, settings=settings)
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {
            "chunks": [
                {
                    "text": ch.text,
                    "label": ch.label,
                    "score": ch.score,
                    "doc_path": ch.doc_path,
                    "chunk_index": ch.chunk_index,
                }
                for ch in chunks
            ]
        }

    @app.post("/ask", dependencies=[Depends(_check_auth)])
    def ask(body: AskRequest, settings: Settings = Depends(_settings)) -> StreamingResponse:
        try:
            stream, sources, empty = rag_answer_stream(body.question, k=body.k, settings=settings)
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        def event_gen():
            if empty:
                yield f"data: {json.dumps({'token': ''.join(stream)})}\n\n"
                yield "data: [DONE]\n\n"
                return
            yield f"data: {json.dumps({'sources': [s.label for s in sources]})}\n\n"
            for token in stream:
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @app.post("/ingest/text", dependencies=[Depends(_check_auth)])
    def ingest_text(body: IngestTextRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        from cluny.ollama_client import OllamaClient

        collection = get_collection(settings)
        ollama = OllamaClient(settings)
        try:
            if body.catalog:
                result = add_inline_text(
                    settings,
                    collection,
                    ollama,
                    body.text,
                    source_label=body.source,
                    title=body.title,
                )
                return {
                    "doc_id": result.doc_id,
                    "chunk_count": result.chunk_count,
                    "catalog": True,
                }
            from cluny.ingest import ingest_string

            n = ingest_string(
                collection,
                ollama,
                body.text,
                source_label=body.source,
                settings=settings,
            )
            if isinstance(n, tuple):
                n = n[0]
            return {"chunk_count": n, "catalog": False}
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/library", dependencies=[Depends(_check_auth)])
    def library(settings: Settings = Depends(_settings)) -> dict[str, Any]:
        conn = connect(settings)
        docs = list_documents(conn)
        conn.close()
        return {
            "documents": [
                {
                    "id": d.id,
                    "path": d.path,
                    "kind": d.kind,
                    "title": d.title,
                    "chunk_count": d.chunk_count,
                }
                for d in docs
            ]
        }

    @app.post("/tasks", dependencies=[Depends(_check_auth)])
    def create_task(body: TaskCreateRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        conn = tasks_connect(settings)
        task = db_create_task(
            conn,
            body.title,
            due_at=body.due_at,
            notes=body.notes,
            project_id=body.project_id,
            recurrence=body.recurrence,
        )
        conn.close()
        return {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "due_at": task.due_at,
            "recurrence": task.recurrence,
        }

    @app.post("/agent", dependencies=[Depends(_check_auth)])
    def agent(body: AgentRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        if body.mode not in ("knowledge", "tasks", "all", "planner"):
            raise HTTPException(status_code=400, detail="Invalid mode")
        try:
            result = run_agent(body.question, settings=settings, mode=body.mode)  # type: ignore[arg-type]
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"answer": result.answer, "tool_calls": result.tool_calls}

    @app.post("/chat", dependencies=[Depends(_check_auth)])
    def chat(body: ChatRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        try:
            result = run_chat(body.question, settings=settings)
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"route": result.route, "answer": result.answer, "tool_calls": result.tool_calls}

    return app


def serve(settings: Settings | None = None) -> None:
    import uvicorn

    settings = settings or Settings.load()
    uvicorn.run(
        create_app(),
        host=settings.api_bind_host,
        port=settings.api_port,
        log_level="info",
    )
