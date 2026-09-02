"""Local HTTP API for Cluny (optional FastAPI dependency)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from cluny.agent import run_agent
from cluny.brain_config import (
    apply_config_update,
    effective_config,
    reset_brain_config,
)
from cluny.capture import capture_note
from cluny.chat_service import SessionNotFoundError, api_chat, api_chat_stream_events
from cluny.config import Settings
from cluny.documents import add_inline_text
from cluny.gui_api import (
    apply_user_config_update,
    create_library_collection,
    create_session_payload,
    delete_library_collection,
    delete_library_doc,
    ingest_uploaded_file,
    library_collections,
    library_document_detail,
    library_documents_payload,
    library_search_payload,
    session_messages_payload,
    sessions_list,
    stats_payload,
    update_library_document,
    user_config_payload,
)
from cluny.kosistenz_context import KosistenzContext
from cluny.library_db import connect, document_count
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.proposals import run_proposals, source_dicts_from_rag_sources
from cluny.query import retrieve
from cluny.store import get_collection
from cluny.task_sync import (
    api_delete_synced_task,
    api_get_synced_task,
    api_list_synced_tasks,
    api_sync_task,
)
from cluny.tasks_db import connect as tasks_connect, list_tasks

try:
    from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel, Field
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "FastAPI is required for the API. Install with: pip install -e '.[api]'"
    ) from e


class SearchRequest(BaseModel):
    query: str
    k: int = Field(default=5, ge=1, le=50)
    collection: str | None = None


class IngestTextRequest(BaseModel):
    text: str
    source: str = "inline"
    catalog: bool = False
    title: str | None = None
    collection: str | None = None


class CaptureRequest(BaseModel):
    text: str
    title: str | None = None
    source: str | None = None
    collection: str | None = None


class AgentRequest(BaseModel):
    question: str
    mode: str = "knowledge"


class ChatRequest(BaseModel):
    question: str
    context: str | None = None
    context_json: KosistenzContext | None = None
    session_id: str | None = None
    collection: str | None = None
    k: int = Field(default=5, ge=1, le=50)


class ProposeRequest(BaseModel):
    question: str
    context: str | None = None
    context_json: KosistenzContext | None = None
    collection: str | None = None
    k: int = Field(default=5, ge=1, le=25)


class TaskSyncRequest(BaseModel):
    external_id: str
    title: str
    status: str = "open"
    due_at: str | None = None
    notes: str | None = None
    project_id: str | None = None
    recurrence: str | None = None


class BrainConfigPutRequest(BaseModel):
    global_persona: str | None = None
    prompts: dict[str, str | None] | None = None
    behavior: dict[str, str | int | None] | None = None


class BrainConfigResetRequest(BaseModel):
    prompt_key: str | None = None
    reset_behavior: bool = False
    reset_persona: bool = False
    reset_all: bool = False


class UserConfigPutRequest(BaseModel):
    chat_model: str | None = None
    embed_model: str | None = None
    retrieval_k: int | None = Field(default=None, ge=1, le=50)
    hybrid_vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    agent_mode: str | None = None
    ask_collection: str | None = None
    standalone_mode: bool | None = None


class SessionCreateRequest(BaseModel):
    title: str | None = None


class LibraryUpdateRequest(BaseModel):
    title: str | None = None
    collections: list[str] | None = None
    tags: list[str] | None = None


class CollectionCreateRequest(BaseModel):
    name: str


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


def _ollama_ok(settings: Settings) -> bool:
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{settings.ollama_base_url}/api/tags")
            return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _brain_status(settings: Settings) -> tuple[bool, str | None]:
    if not _ollama_ok(settings):
        return False, "Ollama is not reachable — start Ollama for Ask and ingest."
    return True, None


def _sse_from_payloads(payloads) -> StreamingResponse:
    def event_gen():
        for payload in payloads:
            if payload == "[DONE]":
                yield "data: [DONE]\n\n"
            else:
                yield f"data: {payload}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cluny API",
        version="0.6.0",
        description=(
            "Brain service for Kosistenz — RAG, Ask/chat/agent, journal index copy. "
            "Kosistenz owns week clock, todos, calendar, and journal files. "
            "See INTEGRATION.md (authoritative: Kosistenz docs/cluny-integration.md)."
        ),
    )

    @app.get("/health")
    def health(settings: Settings = Depends(_settings)) -> dict[str, Any]:
        doc_count = 0
        task_count = 0
        chunk_count = 0
        try:
            conn = connect(settings)
            doc_count = document_count(conn)
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            tconn = tasks_connect(settings)
            task_count = len(list_tasks(tconn))
            tconn.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            chunk_count = get_collection(settings).count()
        except Exception:  # noqa: BLE001
            pass
        ollama_ok = _ollama_ok(settings)
        brain_ready, message = _brain_status(settings)
        extra = stats_payload(settings)
        return {
            "status": "ok",
            "integration": "brain-only",
            "brain_ready": brain_ready,
            "message": message,
            "ollama_ok": ollama_ok,
            "doc_count": doc_count,
            "task_count": task_count,
            "chunk_count": chunk_count,
            "task_count_note": "local CLI/widget tasks.sqlite — not Kosistenz todos",
            **extra,
        }

    @app.get("/stats", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def stats(settings: Settings = Depends(_settings)) -> dict[str, Any]:
        return stats_payload(settings)

    @app.post("/search", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def search(body: SearchRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        try:
            chunks = retrieve(
                body.query,
                k=body.k,
                settings=settings,
                collection_name=body.collection,
            )
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {
            "collection": body.collection,
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

    @app.post("/ask", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def ask(body: ChatRequest, settings: Settings = Depends(_settings)) -> StreamingResponse:
        try:
            payloads = api_chat_stream_events(
                body.question,
                settings=settings,
                context=body.context,
                context_json=body.context_json,
                session_id=body.session_id,
                k=body.k,
                collection=body.collection,
            )
        except SessionNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return _sse_from_payloads(payloads)

    @app.post("/ingest/text", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def ingest_text(body: IngestTextRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
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
                    collection_name=body.collection,
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

    @app.post("/capture", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def capture(body: CaptureRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        """Index a short note from phone/Telegram (catalog + default collection)."""
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="text cannot be empty")
        try:
            result = capture_note(
                body.text,
                settings=settings,
                title=body.title,
                source=body.source,
                collection=body.collection,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return result.to_dict()

    @app.get("/library/collections", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def library_collections_route(settings: Settings = Depends(_settings)) -> dict[str, Any]:
        return library_collections(settings)

    @app.post("/library/collections", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def library_collections_create(
        body: CollectionCreateRequest,
        settings: Settings = Depends(_settings),
    ) -> dict[str, Any]:
        try:
            return create_library_collection(settings, body.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.delete(
        "/library/collections/{name}",
        dependencies=[Depends(_check_auth)],
        tags=["Brain"],
    )
    def library_collections_delete(
        name: str,
        force: bool = False,
        settings: Settings = Depends(_settings),
    ) -> dict[str, Any]:
        try:
            return delete_library_collection(settings, name, force=force)
        except ValueError as e:
            msg = str(e)
            status = 409 if "not empty" in msg else 404
            raise HTTPException(status_code=status, detail=msg) from e

    @app.get("/library/search", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def library_search(
        q: str = "",
        collection: str | None = None,
        source: str | None = None,
        limit: int = 50,
        settings: Settings = Depends(_settings),
    ) -> dict[str, Any]:
        return library_search_payload(
            settings,
            q=q,
            collection=collection,
            source=source,
            limit=limit,
        )

    @app.get("/library", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def library(
        collection: str | None = None,
        source: str | None = None,
        settings: Settings = Depends(_settings),
    ) -> dict[str, Any]:
        return library_documents_payload(settings, collection=collection, source=source)

    @app.get("/library/{doc_id}", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def library_get(doc_id: str, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        try:
            return library_document_detail(settings, doc_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.patch("/library/{doc_id}", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def library_patch(
        doc_id: str,
        body: LibraryUpdateRequest,
        settings: Settings = Depends(_settings),
    ) -> dict[str, Any]:
        data = body.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")
        try:
            return update_library_document(settings, doc_id, data)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.delete("/library/{doc_id}", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def library_delete(doc_id: str, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        try:
            return delete_library_doc(settings, doc_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.post("/ingest/file", dependencies=[Depends(_check_auth)], tags=["Brain"])
    async def ingest_file(
        file: UploadFile = File(...),
        title: str | None = Form(None),
        copy_into_library: bool = Form(False),
        collection: str | None = Form(None),
        settings: Settings = Depends(_settings),
    ) -> dict[str, Any]:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="empty file")
        try:
            return ingest_uploaded_file(
                settings,
                filename=file.filename or "upload.txt",
                content=raw,
                title=title,
                copy_into_library=copy_into_library,
                collection=collection,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/sessions", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def sessions_list_route(
        limit: int = 50, settings: Settings = Depends(_settings)
    ) -> dict[str, Any]:
        return sessions_list(settings, limit=min(max(limit, 1), 100))

    @app.post("/sessions", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def sessions_create(
        body: SessionCreateRequest, settings: Settings = Depends(_settings)
    ) -> dict[str, Any]:
        return create_session_payload(settings, title=body.title)

    @app.get("/sessions/{session_id}/messages", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def sessions_messages(session_id: str, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        try:
            return session_messages_payload(settings, session_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.get("/user/config", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def user_config_get(settings: Settings = Depends(_settings)) -> dict[str, Any]:
        return user_config_payload(settings)

    @app.put("/user/config", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def user_config_put(
        body: UserConfigPutRequest, settings: Settings = Depends(_settings)
    ) -> dict[str, Any]:
        data = body.model_dump(exclude_unset=True)
        return apply_user_config_update(settings, data)

    @app.post("/agent", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def agent(body: AgentRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        if body.mode not in ("knowledge", "tasks", "all", "planner"):
            raise HTTPException(status_code=400, detail="Invalid mode")
        try:
            result = run_agent(body.question, settings=settings, mode=body.mode)  # type: ignore[arg-type]
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"answer": result.answer, "tool_calls": result.tool_calls}

    @app.post("/chat", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def chat(body: ChatRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        try:
            return api_chat(
                body.question,
                settings=settings,
                context=body.context,
                context_json=body.context_json,
                session_id=body.session_id,
                collection=body.collection,
            )
        except SessionNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.post("/chat/stream", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def chat_stream(body: ChatRequest, settings: Settings = Depends(_settings)) -> StreamingResponse:
        try:
            payloads = api_chat_stream_events(
                body.question,
                settings=settings,
                context=body.context,
                context_json=body.context_json,
                session_id=body.session_id,
                k=body.k,
                collection=body.collection,
            )
        except SessionNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return _sse_from_payloads(payloads)

    @app.post("/tasks/sync", dependencies=[Depends(_check_auth)], tags=["Kosistenz mirror"])
    def tasks_sync_upsert(
        body: TaskSyncRequest, settings: Settings = Depends(_settings)
    ) -> dict[str, Any]:
        """Mirror a Kosistenz todo by external_id (not authoritative for scheduling)."""
        if body.status not in ("open", "done"):
            raise HTTPException(status_code=400, detail="status must be open or done")
        try:
            return api_sync_task(
                settings=settings,
                external_id=body.external_id,
                title=body.title,
                status=body.status,
                due_at=body.due_at,
                notes=body.notes,
                project_id=body.project_id,
                recurrence=body.recurrence,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.get("/tasks/sync", dependencies=[Depends(_check_auth)], tags=["Kosistenz mirror"])
    def tasks_sync_list(settings: Settings = Depends(_settings)) -> dict[str, Any]:
        return {"tasks": api_list_synced_tasks(settings)}

    @app.get("/tasks/sync/{external_id}", dependencies=[Depends(_check_auth)], tags=["Kosistenz mirror"])
    def tasks_sync_get(external_id: str, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        task = api_get_synced_task(settings, external_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Synced task not found")
        return task

    @app.delete("/tasks/sync/{external_id}", dependencies=[Depends(_check_auth)], tags=["Kosistenz mirror"])
    def tasks_sync_delete(external_id: str, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        if not api_delete_synced_task(settings, external_id):
            raise HTTPException(status_code=404, detail="Synced task not found")
        return {"deleted": True, "external_id": external_id}

    @app.post("/propose", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def propose(body: ProposeRequest, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        try:
            result = run_proposals(
                body.question,
                context=body.context,
                context_json=body.context_json,
                settings=settings,
                collection=body.collection,
                k=body.k,
            )
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {
            "proposals": [p.to_dict() for p in result.proposals],
            "sources": source_dicts_from_rag_sources(result.sources),
        }

    @app.get("/brain/config", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def brain_config_get(settings: Settings = Depends(_settings)) -> dict[str, Any]:
        return effective_config(settings)

    @app.put("/brain/config", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def brain_config_put(
        body: BrainConfigPutRequest, settings: Settings = Depends(_settings)
    ) -> dict[str, Any]:
        try:
            apply_config_update(
                settings,
                global_persona=body.global_persona if body.global_persona is not None else None,
                prompts=body.prompts,
                behavior=body.behavior,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return effective_config(settings)

    @app.post("/brain/config/reset", dependencies=[Depends(_check_auth)], tags=["Brain"])
    def brain_config_reset(
        body: BrainConfigResetRequest, settings: Settings = Depends(_settings)
    ) -> dict[str, Any]:
        try:
            reset_brain_config(
                settings,
                prompt_key=body.prompt_key,
                reset_behavior=body.reset_behavior,
                reset_persona=body.reset_persona,
                reset_all=body.reset_all,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return effective_config(settings)

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
