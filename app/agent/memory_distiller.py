"""Memory distiller -- three-layer distillation for SaaS stateful memory.

Layer 1: Per-turn distillation → short_term memory (cross-session, from conversation extraction)
Layer 2: Periodic consolidation → long_term memory (from short_term promotion, importance >= 0.7)
Layer 3: System prompt injection → long_term summary ≤ 500 chars

Triggers:
- Per-turn: after each assistant response, extract key facts → short_term
- Session end: consolidate short_term → long_term (promote high-importance, discard low-importance)
- Pre-compress: distill un-distilled messages → short_term before compressing context
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from app.dao.memory_dao import MemoryDAO
from app.dao.message_dao import MessageDAO
from app.agent.llm_router import LLMRouter
from app.agent.context_loader import ContextLoader
from app.config import settings

log = logging.getLogger(__name__)

DISTILL_PROMPT = """你是一个记忆蒸馏器。从以下对话片段中提取需要长期记住的关键信息。

提取规则：
1. 只提取有长期价值的信息，忽略临时闲聊和中间步骤
2. 每条事实归类为：preference（偏好）、decision（决策）、fact（事实）、constraint（约束）、goal（目标）
3. 为每条事实打分 importance：0.0-1.0，越高越重要
4. key 使用英文 snake_case 唯一标识，如 "preferred_programming_language"
5. value 用中文简洁描述事实内容

=== 对话片段开始 ===
{messages_text}
=== 对话片段结束 ===

请输出 JSON 数组，格式如下：
[
  {{"category": "preference", "key": "xxx", "value": "xxx", "importance": 0.9}},
  {{"category": "fact", "key": "xxx", "value": "xxx", "importance": 0.7}}
]

如果没有值得长期记住的信息，输出空数组 []。"""


@dataclass
class DistillationResult:
    session_id: str
    facts: list[dict]
    total_messages_processed: int
    distilled_count: int
    skipped_count: int


class MemoryDistillerProtocol(Protocol):
    async def distill(self, employee_id: int, session_id: str,
                      messages: list[dict]) -> DistillationResult: ...
    async def pre_compress_distill(self, employee_id: int,
                                   session_id: str) -> DistillationResult: ...


class MemoryDistiller:
    def __init__(self, employee_id: int, session_factory):
        self._employee_id = employee_id
        self._session_factory = session_factory
        self._llm_router = LLMRouter()
        self._context_loader = ContextLoader(employee_id, session_factory)

    async def distill(
        self,
        employee_id: int,
        session_id: str,
        messages: list[dict],
        memory_type: str = "short_term",
    ) -> DistillationResult:
        """Distill key facts from conversation messages into memory.
        memory_type: "short_term" for per-turn extraction, "long_term" for session-end consolidation."""
        if not settings.memory_distill_enabled:
            return DistillationResult(session_id=session_id, facts=[], total_messages_processed=0,
                                      distilled_count=0, skipped_count=0)

        if len(messages) < settings.memory_distill_min_messages:
            log.debug(f"跳过蒸馏：仅有 {len(messages)} 条消息（最少需要 {settings.memory_distill_min_messages} 条）")
            return DistillationResult(session_id=session_id, facts=[], total_messages_processed=len(messages),
                                      distilled_count=0, skipped_count=0)

        # build distillation input
        messages_text = self._format_messages(messages)
        if len(messages_text) > settings.memory_distill_max_input_chars:
            messages_text = messages_text[:settings.memory_distill_max_input_chars]

        prompt = DISTILL_PROMPT.format(messages_text=messages_text)

        # call LLM
        try:
            response = await self._llm_router.chat(
                model=settings.compress_model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            raw = response.choices[0].message.content.strip()
        except Exception as e:
            log.warning(f"记忆蒸馏LLM调用失败: {e}")
            return DistillationResult(session_id=session_id, facts=[], total_messages_processed=len(messages),
                                      distilled_count=0, skipped_count=0)

        # parse response
        facts = self._parse_facts(raw)

        # filter low importance
        filtered = [f for f in facts if f.get("importance", 0) >= 0.5]
        skipped = len(facts) - len(filtered)

        if not filtered:
            return DistillationResult(session_id=session_id, facts=filtered,
                                      total_messages_processed=len(messages),
                                      distilled_count=0, skipped_count=skipped)

        # upsert into memory with specified type
        dao = MemoryDAO(self._session_factory, self._employee_id)
        inserted, updated = await dao.upsert_from_distillation(filtered, session_id, memory_type=memory_type)

        # clear memory cache so next session sees updated facts
        await self._context_loader.clear_memory_cache()

        log.info(f"Session {session_id[:8]} 蒸馏完成: 新增 {inserted} 条，更新 {updated} 条，跳过 {skipped} 条")

        return DistillationResult(
            session_id=session_id,
            facts=filtered,
            total_messages_processed=len(messages),
            distilled_count=inserted + updated,
            skipped_count=skipped,
        )

    async def pre_compress_distill(
        self,
        employee_id: int,
        session_id: str,
    ) -> DistillationResult:
        """Distill only un-distilled messages before context compression."""
        msg_dao = MessageDAO(self._session_factory, self._employee_id)
        history, _ = await msg_dao.get_history(session_id, limit=10000)

        # filter to only un-distilled user/assistant messages
        un_distilled = [
            {"role": m.role, "content": m.content or ""}
            for m in history
            if m.role in ("user", "assistant") and m.is_distilled == 0 and m.is_compressed == 0
        ]

        if not un_distilled:
            return DistillationResult(session_id=session_id, facts=[], total_messages_processed=0,
                                      distilled_count=0, skipped_count=0)

        result = await self.distill(employee_id, session_id, un_distilled)

        # mark messages as distilled
        distilled_ids = [m.id for m in history
                         if m.role in ("user", "assistant") and m.is_distilled == 0 and m.is_compressed == 0]
        for mid in distilled_ids:
            await msg_dao.update(mid, is_distilled=1)

        return result

    def _format_messages(self, messages: list[dict]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if content:
                lines.append(f"[{role}]: {content[:300]}")
        return "\n".join(lines)

    def _parse_facts(self, raw: str) -> list[dict]:
        """Parse LLM response into fact dicts."""
        import re as _re
        raw = raw.strip()
        # strip <think>...</think> blocks (chain-of-thought from reasoning models)
        raw = _re.sub(r'<think(?:ing)?>.*?</think(?:ing)?>', '', raw, flags=_re.DOTALL | _re.IGNORECASE).strip()
        # strip markdown code blocks if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            facts = json.loads(raw)
            if not isinstance(facts, list):
                return []
            valid = []
            for f in facts:
                if isinstance(f, dict) and "key" in f and "value" in f:
                    f.setdefault("category", "fact")
                    f.setdefault("importance", 0.5)
                    f["importance"] = max(0.0, min(1.0, float(f.get("importance", 0.5))))
                    valid.append(f)
            return valid
        except json.JSONDecodeError:
            log.warning(f"蒸馏响应解析失败: {raw[:200]}")
            return []

    async def consolidate(self, employee_id: int) -> tuple[int, int]:
        """Consolidate short_term memories into long_term.
        Promotes importance >= 0.7 to long_term, soft-deletes importance < 0.5."""
        dao = MemoryDAO(self._session_factory, self._employee_id)
        promoted, discarded = await dao.consolidate_to_long_term()

        # clear memory cache so next session sees updated facts
        await self._context_loader.clear_memory_cache()

        log.info(f"记忆整合: {promoted} 条晋升为长期记忆，{discarded} 条已丢弃")
        return promoted, discarded