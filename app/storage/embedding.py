"""Async embedding generation via OpenAI-compatible /v1/embeddings endpoint."""

from __future__ import annotations

import logging
from openai import AsyncOpenAI
from app.config import settings

log = logging.getLogger(__name__)


def _get_client() -> AsyncOpenAI:
    api_base = settings.embedding_api_base or settings.openai_api_base
    api_key = settings.embedding_api_key or (settings.openai_api_keys[0] if settings.openai_api_keys else "none")
    return AsyncOpenAI(api_key=api_key, base_url=api_base)


async def get_embedding(text: str) -> list[float] | None:
    """Generate a dense vector embedding for text.

    Returns the embedding list on success, None on any failure.
    Callers should treat None as unavailable and fall back to non-vector retrieval.
    """
    if not settings.embedding_model or not text.strip():
        return None

    # Truncate to avoid exceeding model token limits (most models ~8192 tokens)
    text = text[:4000]

    try:
        client = _get_client()
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=text,
        )
        return resp.data[0].embedding
    except Exception as e:
        log.warning("Embedding generation failed: %s", e)
        return None
