from __future__ import annotations

import logging
from elasticsearch import AsyncElasticsearch, NotFoundError
from app.config import settings

log = logging.getLogger(__name__)

_es_client: AsyncElasticsearch | None = None

# Single shared memory index; user isolation via employee_id field filter
MEMORY_INDEX = "bx-memory"


async def init_es():
    global _es_client
    _es_client = AsyncElasticsearch(hosts=settings.es_hosts)
    await _ensure_memory_index()


async def close_es():
    global _es_client
    if _es_client:
        await _es_client.close()
        _es_client = None


def get_es_client() -> AsyncElasticsearch:
    if _es_client is None:
        raise RuntimeError("Elasticsearch not initialized. Call init_es() first.")
    return _es_client


async def _ensure_memory_index() -> None:
    """Create the bx-memory index with dense_vector mapping if it doesn't exist.

    When the index already exists, validates that the embedding dimension matches
    settings.embedding_dim and logs a WARNING if they diverge (does not auto-delete
    to avoid data loss).
    """
    es = get_es_client()
    try:
        exists = await es.indices.exists(index=MEMORY_INDEX)
    except Exception:
        return  # ES unavailable — skip index creation

    if exists:
        try:
            mapping = await es.indices.get_mapping(index=MEMORY_INDEX)
            props = mapping[MEMORY_INDEX]["mappings"].get("properties", {})
            embedding_props = props.get("embedding", {})
            existing_dims = embedding_props.get("dims")
            if existing_dims is not None and existing_dims != settings.embedding_dim:
                log.warning(
                    "ES index '%s' has embedding.dims=%d but settings.embedding_dim=%d — "
                    "embeddings will be rejected. Re-create the index or fix EMBEDDING_DIM.",
                    MEMORY_INDEX, existing_dims, settings.embedding_dim,
                )
            else:
                log.info("ES memory index '%s' validated (dims=%s)", MEMORY_INDEX, existing_dims or "unknown")
        except Exception as e:
            log.warning("Could not validate ES index mapping for '%s': %s", MEMORY_INDEX, e)
        return

    mapping = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "properties": {
                "id":           {"type": "keyword"},
                "employee_id":  {"type": "integer"},
                "key":          {"type": "keyword"},
                "value":        {"type": "text"},
                "category":     {"type": "keyword"},
                "memory_type":  {"type": "keyword"},
                "importance":   {"type": "float"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": settings.embedding_dim,
                    "index": True,
                    "similarity": "cosine",
                },
                "is_deleted":   {"type": "boolean"},
                "created_at":   {"type": "date"},
            }
        },
    }
    try:
        await es.indices.create(index=MEMORY_INDEX, body=mapping)
        log.info("Created ES memory index: %s (dim=%d)", MEMORY_INDEX, settings.embedding_dim)
    except Exception as e:
        log.warning("Failed to create ES memory index: %s", e)


async def index_memory_doc(
    employee_id: int,
    doc_id: str,
    key: str,
    value: str,
    category: str,
    memory_type: str,
    importance: float,
    is_deleted: bool,
    embedding: list[float] | None,
    created_at: str | None = None,
) -> None:
    """Upsert a single memory document into the ES index.
    Called asynchronously after DB writes; failures are non-fatal."""
    es = get_es_client()
    doc = {
        "id": doc_id,
        "employee_id": employee_id,
        "key": key,
        "value": value,
        "category": category,
        "memory_type": memory_type,
        "importance": importance,
        "is_deleted": is_deleted,
    }
    if created_at:
        doc["created_at"] = created_at
    if embedding:
        doc["embedding"] = embedding

    try:
        await es.index(index=MEMORY_INDEX, id=doc_id, document=doc)
    except Exception as e:
        log.warning("ES index_memory_doc failed for %s: %s", doc_id, e)


async def hybrid_search_memories(
    employee_id: int,
    query_embedding: list[float],
    query_text: str,
    top_k: int = 10,
    memory_type: str = "long_term",
    date_from: str | None = None,
) -> list[dict]:
    """Hybrid search: kNN (cosine) + BM25 with manual RRF merge in Python.

    Avoids the ES native RRF feature which requires a paid license.
    Both searches run in parallel; results are merged using the standard
    RRF formula: score += 1 / (rank_constant + rank).

    Args:
        date_from: ISO 8601 date string (e.g. "2026-05-23") to filter by created_at.
                   Used for STM retrieval to limit to recent N days.

    Returns hit source dicts ordered by merged RRF score (top_k items).
    Falls back gracefully on any ES error.
    """
    import asyncio as _asyncio

    es = get_es_client()
    pool_size = top_k * 3
    rank_constant = 60

    base_filter: list[dict] = [
        {"term": {"employee_id": employee_id}},
        {"term": {"is_deleted": False}},
        {"term": {"memory_type": memory_type}},
    ]
    if date_from:
        base_filter.append({"range": {"created_at": {"gte": date_from}}})

    knn_body = {
        "size": pool_size,
        "knn": {
            "field": "embedding",
            "query_vector": query_embedding,
            "k": pool_size,
            "num_candidates": max(pool_size * 2, 50),
            "filter": base_filter,
        },
        "_source": True,
    }

    bm25_body = {
        "size": pool_size,
        "query": {
            "bool": {
                "must": {"match": {"value": query_text}},
                "filter": base_filter,
            }
        },
        "_source": True,
    }

    async def _search(body):
        resp = await es.search(index=MEMORY_INDEX, body=body)
        return resp["hits"]["hits"]

    knn_hits, bm25_hits = await _asyncio.gather(
        _search(knn_body),
        _search(bm25_body),
        return_exceptions=True,
    )

    rrf: dict[str, dict] = {}

    if not isinstance(knn_hits, Exception):
        for rank, hit in enumerate(knn_hits):
            doc_id = hit["_id"]
            if doc_id not in rrf:
                rrf[doc_id] = {"source": hit["_source"], "score": 0.0}
            rrf[doc_id]["score"] += 1.0 / (rank_constant + rank + 1)
    else:
        log.warning("ES kNN search failed: %s", knn_hits)

    if not isinstance(bm25_hits, Exception):
        for rank, hit in enumerate(bm25_hits):
            doc_id = hit["_id"]
            if doc_id not in rrf:
                rrf[doc_id] = {"source": hit["_source"], "score": 0.0}
            rrf[doc_id]["score"] += 1.0 / (rank_constant + rank + 1)
    else:
        log.warning("ES BM25 search failed: %s", bm25_hits)

    if not rrf:
        return []

    sorted_hits = sorted(rrf.values(), key=lambda x: x["score"], reverse=True)
    results = [item["source"] for item in sorted_hits[:top_k]]
    # Attach merged RRF score for downstream scoring (e.g. dual-track LTM)
    for item, src in zip(sorted_hits[:top_k], results):
        src["_score"] = item["score"]
    return results
