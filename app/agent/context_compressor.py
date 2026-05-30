"""Context compressor -- summarizes middle messages when token count exceeds session limit.

Enhanced: triggers pre-compress distillation before compressing, so key facts
are preserved in long-term memory even when conversation context is compressed.
"""

from app.dao.message_dao import MessageDAO
from app.dao.session_dao import SessionDAO
from app.db.database import get_session_factory
from app.agent.llm_router import LLMRouter
from app.agent.memory_distiller import MemoryDistiller
from app.config import settings
import logging

log = logging.getLogger(__name__)


async def compress_if_needed(employee_id: int, session_id: str, force: bool = False) -> bool:
    """Check if session token count exceeds max_tokens, compress middle messages if so.

    When force=True, bypass the threshold check and compress unconditionally.
    Used by the pre-flight guard to rescue an in-progress task instead of aborting it.
    """
    session_dao = SessionDAO(get_session_factory(), employee_id)
    msg_dao = MessageDAO(get_session_factory(), employee_id)

    session = await session_dao.get_by_id(session_id)
    if not force:
        if session.max_tokens <= 0:
            return False
        if session.token_count / session.max_tokens < settings.context_compression_threshold:
            return False
    tokens_before = session.token_count

    # Pre-compress hook: distill un-distilled messages first
    if settings.memory_distill_enabled:
        try:
            distiller = MemoryDistiller(employee_id, get_session_factory())
            result = await distiller.pre_compress_distill(employee_id, session_id)
            log.info(f"Pre-compress distillation: {result.distilled_count} facts extracted")
        except Exception as e:
            log.warning(f"Pre-compress distillation failed: {e}")

    # Load all messages for the session
    history, _ = await msg_dao.get_history(session_id, limit=10000)

    if len(history) < 5:
        return False

    # Keep first 2 and last 2 messages, compress the middle
    to_compress = history[2:-2]
    if not to_compress:
        return False

    # Build summary of middle messages
    middle_text = "\n".join([f"[{m.role}]: {(m.content or '')[:500]}" for m in to_compress])
    summary_prompt = [
        {"role": "system", "content": "Summarize the following conversation segment concisely, preserving key decisions, facts, and action items."},
        {"role": "user", "content": middle_text},
    ]

    router = LLMRouter()
    try:
        response = await router.chat(model=settings.compress_model, messages=summary_prompt, stream=False)
        summary = response.choices[0].message.content
    except Exception as exc:
        log.warning(f"Context compression failed: {exc}")
        return False

    # Mark compressed messages as is_compressed=1 and zero their token count
    for msg in to_compress:
        await msg_dao.update(msg.id, token_count=0, is_compressed=1)

    # Insert compressed summary as a system message
    summary_tokens = len(summary) // 4
    await msg_dao.create(
        session_id=session_id, role="system",
        content=f"[Compressed context]: {summary}",
        token_count=summary_tokens,
    )

    # Reset session token_count to reflect only surviving messages
    kept = [m for m in history if m not in to_compress]
    kept_tokens = sum(m.token_count or 0 for m in kept) + summary_tokens
    await session_dao.set_token_count(session_id, kept_tokens)

    try:
        from app.api.v1.stream import push_event
        from app.sse.event_types import SSEEventType
        push_event(session_id, SSEEventType.context_compression, {
            "tokens_before": tokens_before,
            "tokens_after": kept_tokens,
            "compressed_count": len(to_compress),
            "summary_preview": summary[:100],
        })
    except Exception as e:
        log.warning(f"Failed to push context_compression SSE event: {e}")

    return True