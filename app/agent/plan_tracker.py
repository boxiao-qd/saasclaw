"""Plan parser — detect plan structure and step progress from LLM thinking content.

The LLM is instructed to output plans in thinking tags with a specific format:
    「执行计划：
    Step 1: [description]
    Step 2: [description]
    ...」

This module extracts that structure and emits SSE events for plan lifecycle.
Plan state is kept purely in-memory (a variable on the PlanTracker instance).
The active plan is injected into the LLM context each iteration via
plan_summary_for_llm() so the model always sees current step statuses.
"""

from __future__ import annotations

import hashlib
import logging
import re

from app.sse.event_types import SSEEventType
from app.config import settings

log = logging.getLogger(__name__)

# Match plan header: 「执行计划：」 / 「调整后的执行计划：」 / 「调整计划：」 etc.
_PLAN_HEADER_RE = re.compile(r"(?:执行|调整(?:后的)?)(?:执行)?计划(?:如下)?[：:]")
# Match a step line: Step N: ... or Step N：... or 第N步：... or N. ...
_STEP_RE = re.compile(r"(?:Step\s*(\d+)|第\s*(\d+)\s*步)\s*[：:]\s*(.+)")
# Match numbered step: 1. description
_NUM_STEP_RE = re.compile(r"^\s*(\d+)[\.\、\)]\s+(.+)")
# Match step completion — covers Chinese (了/执行/已经) and English (done/completed/finished)
_STEP_DONE_RE = re.compile(
    r"(?:Step\s*(\d+)|第\s*(\d+)\s*步)"
    r"\s*(?:[：:]\s*)?"
    r"\s*(?:已经?|也|执行)?\s*"
    r"(?:完成了?|成功了?|执行完毕了?|执行成功|done|completed?|finished?|succeed(?:ed)?|✓|√)",
    re.IGNORECASE,
)
# Match step failure — covers Chinese and English
_STEP_FAIL_RE = re.compile(
    r"(?:Step\s*(\d+)|第\s*(\d+)\s*步)"
    r"\s*(?:[：:]\s*)?"
    r"\s*(?:已经?|也|执行)?\s*"
    r"(?:失败了?|执行失败了?|出错了?|报错了?|未成功|遇到(?:了)?问题|failed?|errored?|unsuccessful|❌)",
    re.IGNORECASE,
)
# Match plan adjustment
_PLAN_ADJUST_RE = re.compile(r"(?:调整|更新|修改|修订)(?:执行)?计划")


def _emit(session_id: str, event_type: SSEEventType, data: dict) -> None:
    """Default emit function using SSE push_event."""
    from app.api.v1.stream import push_event
    push_event(session_id, event_type, data)


class PlanTracker:
    """Tracks plan state across agent loop iterations and emits SSE events.

    Plan state is a pure in-memory variable. Each agent loop creates its own
    PlanTracker instance. The active plan is injected into the LLM context
    each iteration via plan_summary_for_llm().
    """

    def __init__(self, session_id: str, emit_callback=None):
        self._session_id = session_id
        self._plan_id: str = ""
        self._goal: str = ""
        self._steps: list[dict] = []  # [{id, description, status}]
        self._current_step_index: int = -1
        self._plan_emitted: bool = False
        self._total_executions: int = 0
        self._emit = emit_callback if emit_callback else lambda et, d: _emit(session_id, et, d)

    @property
    def total_executions(self) -> int:
        return self._total_executions

    @property
    def has_plan(self) -> bool:
        return self._plan_emitted

    def increment_executions(self):
        self._total_executions += 1

    def parse_thinking(self, reasoning_content: str) -> None:
        """Parse thinking content to detect plan/step changes and emit SSE events."""
        if not reasoning_content:
            return

        self._detect_plan(reasoning_content)
        self._detect_step_result(reasoning_content)

        if self._plan_emitted and _PLAN_ADJUST_RE.search(reasoning_content):
            self._detect_plan(reasoning_content)

    def _detect_plan(self, text: str) -> None:
        """Detect plan structure in thinking content."""
        if not _PLAN_HEADER_RE.search(text):
            return

        steps: list[dict] = []
        lines = text.split("\n")
        in_plan = False

        for line in lines:
            stripped = line.strip()
            if _PLAN_HEADER_RE.search(stripped):
                in_plan = True
                continue
            if not in_plan:
                continue

            m = _STEP_RE.search(stripped)
            if m:
                desc = (m.group(3) or "").strip()
                steps.append({
                    "id": self._make_step_id(desc),
                    "description": desc,
                    "status": self._get_existing_step_status(desc),
                })
                continue

            m = _NUM_STEP_RE.match(stripped)
            if m:
                desc = m.group(2).strip()
                steps.append({
                    "id": self._make_step_id(desc),
                    "description": desc,
                    "status": self._get_existing_step_status(desc),
                })
                continue

            if steps and stripped and not stripped.startswith(("Step", "第", *"0123456789")):
                break

        if not steps:
            return

        new_step_ids = [s["id"] for s in steps]
        old_step_ids = [s["id"] for s in self._steps]

        if not self._plan_emitted:
            self._steps = steps
            self._goal = self._extract_goal(text)
            self._plan_emitted = True
            self._emit(SSEEventType.plan_created, {
                "plan_id": self._plan_id or self._session_id,
                "goal": self._goal,
                "steps": [{"id": s["id"], "description": s["description"]} for s in steps],
                "max_steps": settings.max_plan_steps,
            })
            log.info("[%s] Plan created: %d steps", self._session_id[:8], len(steps))
        elif new_step_ids != old_step_ids:
            self._steps = steps
            reason = self._extract_adjust_reason(text)
            self._emit(SSEEventType.plan_adjusted, {
                "plan_id": self._plan_id or self._session_id,
                "reason": reason,
                "steps": [{"id": s["id"], "description": s["description"]} for s in steps],
                "max_steps": settings.max_plan_steps,
            })

    def _detect_step_result(self, text: str) -> None:
        """Detect step completion or failure in thinking content.

        Processes ALL matches — if the LLM mentions multiple step results
        in a single thinking block, all are captured.
        """
        for m in _STEP_DONE_RE.finditer(text):
            step_num = int(m.group(1) or m.group(2))
            self._mark_step_by_num(step_num, "completed")

        for m in _STEP_FAIL_RE.finditer(text):
            step_num = int(m.group(1) or m.group(2))
            self._mark_step_by_num(step_num, "failed")

        for m in _STEP_RE.finditer(text):
            step_num = int(m.group(1) or m.group(2))
            if self._current_step_index < step_num - 1:
                self._start_step(step_num)
                return

    def _start_step(self, step_num: int) -> None:
        if step_num < 1 or step_num > len(self._steps):
            return
        idx = step_num - 1
        step = self._steps[idx]
        if step["status"] in ("completed", "in_progress"):
            return
        # Implicit completion: when Step N starts, complete the preceding in_progress Step N-1.
        # The LLM advancing to the next step is reliable evidence the previous one finished.
        if idx > 0 and self._steps[idx - 1]["status"] == "in_progress":
            self._mark_step_by_num(idx, "completed")  # step_num=idx marks index idx-1
        step["status"] = "in_progress"
        self._current_step_index = idx
        self._emit(SSEEventType.plan_step_start, {
            "plan_id": self._plan_id or self._session_id,
            "step_index": idx,
            "description": step["description"],
        })

    def _mark_step_by_num(self, step_num: int, status: str) -> None:
        if step_num < 1 or step_num > len(self._steps):
            return False
        idx = step_num - 1
        step = self._steps[idx]
        if step["status"] == status:
            return False
        step["status"] = status
        self._current_step_index = idx if status == "in_progress" else self._current_step_index

        if status == "completed":
            self._emit(SSEEventType.plan_step_complete, {
                "plan_id": self._plan_id or self._session_id,
                "step_index": idx,
                "result_summary": step["description"],
            })
        elif status == "failed":
            self._emit(SSEEventType.plan_step_failed, {
                "plan_id": self._plan_id or self._session_id,
                "step_index": idx,
                "error_summary": step["description"],
                "will_adjust": True,
            })

    # ── LLM context injection ────────────────────────────────────────

    def plan_summary_for_llm(self) -> str:
        """Return a compact plan progress summary for the LLM system message.

        Lets the model see which steps are done, in-progress, pending, or failed.
        Format:
            [当前计划进度]
            ● 分析用户需求 (已完成)
            ◉ 设计解决方案 (执行中)
            ○ 实现代码 (待执行)
            ✕ 部署上线 (已失败)
        """
        if not self._steps:
            return ""

        status_labels = {
            "pending": "待执行",
            "in_progress": "执行中",
            "completed": "已完成",
            "failed": "已失败",
        }
        status_icons = {
            "pending": "○",
            "in_progress": "◉",
            "completed": "●",
            "failed": "✕",
        }

        lines = ["[当前计划进度]"]
        if self._goal:
            lines.append(f"目标: {self._goal}")
        for i, s in enumerate(self._steps, 1):
            icon = status_icons.get(s["status"], "?")
            label = status_labels.get(s["status"], s["status"])
            lines.append(f"  {icon} Step {i}: {s['description']} ({label})")

        return "\n".join(lines)

    # ── Lifecycle ────────────────────────────────────────────────────

    def emit_plan_complete(self, summary: str = "") -> None:
        """Emit plan_complete SSE event."""
        if self._plan_emitted:
            self._emit(SSEEventType.plan_complete, {
                "plan_id": self._plan_id or self._session_id,
                "summary": summary or "所有步骤已完成",
            })

    def get_plan_summary(self) -> str:
        """Return a human-readable plan summary for logging."""
        if not self._steps:
            return "无计划"
        statuses = {"pending": "○", "in_progress": "◉", "completed": "●", "failed": "✕"}
        lines = []
        for s in self._steps:
            icon = statuses.get(s["status"], "?")
            lines.append(f"  {icon} {s['description']}")
        return "\n".join(lines)

    @staticmethod
    def _make_step_id(description: str) -> str:
        return hashlib.md5(description.encode()).hexdigest()[:10]

    def _get_existing_step_status(self, description: str) -> str:
        target_id = self._make_step_id(description)
        for s in self._steps:
            if s["id"] == target_id and s["status"] in ("completed", "failed"):
                return s["status"]
        return "pending"

    def _extract_goal(self, text: str) -> str:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if _PLAN_HEADER_RE.search(line) and i > 0:
                return lines[i - 1].strip()[:200]
        return ""

    def _extract_adjust_reason(self, text: str) -> str:
        m = _PLAN_ADJUST_RE.search(text)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 80)
            return text[start:end].replace("\n", " ").strip()
        return "计划已调整"

    @property
    def steps(self):
        return list(self._steps)