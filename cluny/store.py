"""Chroma-backed persistent vector store for the second brain."""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from cluny.config import Settings

COLLECTION_NAME = "second_brain"


def get_collection(settings: Settings) -> Collection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    chroma_path = settings.data_dir / "chroma"
    client = chromadb.PersistentClient(path=str(chroma_path))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Cluny second brain chunks"},
    )


def query_raw(
    collection: Collection,
    query_embedding: list[float],
    n_results: int,
) -> dict[str, Any]:
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
