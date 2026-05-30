"""Tests for PlanTracker — plan parsing, step progress, and LLM context injection."""

import pytest
from unittest.mock import MagicMock, call

from app.agent.plan_tracker import PlanTracker, _PLAN_HEADER_RE, _STEP_RE, _NUM_STEP_RE, _STEP_DONE_RE, _STEP_FAIL_RE, _PLAN_ADJUST_RE
from app.sse.event_types import SSEEventType


class TestRegexPatterns:
    """Verify regex patterns match expected plan formats."""

    def test_plan_header_chinese(self):
        assert _PLAN_HEADER_RE.search("执行计划：")
        assert _PLAN_HEADER_RE.search("执行计划如下:")
        assert _PLAN_HEADER_RE.search("调整后的执行计划：")
        assert _PLAN_HEADER_RE.search("调整计划：")

    def test_step_format_step_n(self):
        m = _STEP_RE.search("Step 1: 分析需求")
        assert m is not None
        assert m.group(1) == "1"
        assert m.group(3) == "分析需求"

    def test_step_format_chinese(self):
        m = _STEP_RE.search("第 3 步：实现代码")
        assert m is not None
        assert m.group(2) == "3"

    def test_num_step_format(self):
        m = _NUM_STEP_RE.match("1. 分析用户需求")
        assert m is not None
        assert m.group(1) == "1"
        assert m.group(2) == "分析用户需求"

    def test_step_done_regex(self):
        assert _STEP_DONE_RE.search("Step 1 已完成")
        assert _STEP_DONE_RE.search("第2步执行完毕")
        assert _STEP_DONE_RE.search("Step 3也完成")

    def test_step_fail_regex(self):
        assert _STEP_FAIL_RE.search("Step 1 执行失败")
        assert _STEP_FAIL_RE.search("第2步失败")
        assert _STEP_FAIL_RE.search("Step 3遇到问题")

    def test_plan_adjust_regex(self):
        assert _PLAN_ADJUST_RE.search("调整执行计划")
        assert _PLAN_ADJUST_RE.search("更新计划")
        assert _PLAN_ADJUST_RE.search("修改执行计划")


class TestPlanTrackerBasic:
    """Basic PlanTracker lifecycle tests."""

    def _make_tracker(self):
        emit_mock = MagicMock()
        tracker = PlanTracker("test-session", emit_callback=emit_mock)
        return tracker, emit_mock

    def test_init_no_plan(self):
        tracker, _ = self._make_tracker()
        assert not tracker.has_plan
        assert tracker.total_executions == 0
        assert tracker.plan_summary_for_llm() == ""

    def test_increment_executions(self):
        tracker, _ = self._make_tracker()
        tracker.increment_executions()
        assert tracker.total_executions == 1

    def test_parse_empty_thinking(self):
        tracker, _ = self._make_tracker()
        tracker.parse_thinking("")
        tracker.parse_thinking(None)
        assert not tracker.has_plan


class TestPlanDetection:
    """Test plan creation detection from thinking content."""

    def _make_tracker(self):
        emit_mock = MagicMock()
        tracker = PlanTracker("test-session", emit_callback=emit_mock)
        return tracker, emit_mock

    def test_plan_created_step_n_format(self):
        tracker, emit_mock = self._make_tracker()
        thinking = """我需要先制定执行计划：
执行计划：
Step 1: 分析用户需求
Step 2: 设计解决方案
Step 3: 实现代码
"""
        tracker.parse_thinking(thinking)
        assert tracker.has_plan
        assert len(tracker.steps) == 3
        assert tracker.steps[0]["description"] == "分析用户需求"
        # Step 1 gets auto-started when _detect_step_result sees "Step 1: ..." in thinking
        assert tracker.steps[0]["status"] == "in_progress"
        assert tracker.steps[1]["status"] == "pending"
        assert tracker.steps[2]["status"] == "pending"

        # plan_created + plan_step_start (auto-detected Step 1)
        assert emit_mock.call_count == 2
        emit_mock.assert_any_call(
            SSEEventType.plan_created,
            {
                "plan_id": "test-session",
                "goal": "我需要先制定执行计划：",
                "steps": [
                    {"id": tracker.steps[0]["id"], "description": "分析用户需求"},
                    {"id": tracker.steps[1]["id"], "description": "设计解决方案"},
                    {"id": tracker.steps[2]["id"], "description": "实现代码"},
                ],
                "max_steps": 90,
            },
        )
        emit_mock.assert_any_call(
            SSEEventType.plan_step_start,
            {"plan_id": "test-session", "step_index": 0, "description": "分析用户需求"},
        )

    def test_plan_created_chinese_step_format(self):
        tracker, emit_mock = self._make_tracker()
        thinking = """执行计划如下：
第 1 步：搜索相关文档
第 2 步：整理信息
"""
        tracker.parse_thinking(thinking)
        assert tracker.has_plan
        assert len(tracker.steps) == 2

    def test_plan_created_numbered_format(self):
        tracker, emit_mock = self._make_tracker()
        thinking = """执行计划：
1. 分析数据
2. 编写代码
3. 测试验证
"""
        tracker.parse_thinking(thinking)
        assert tracker.has_plan
        assert len(tracker.steps) == 3
        assert tracker.steps[0]["description"] == "分析数据"


class TestStepProgress:
    """Test step start, completion, and failure detection."""

    def _make_tracker_with_plan(self):
        tracker, emit_mock = self._make_tracker()
        thinking = """执行计划：
Step 1: 分析需求
Step 2: 设计方案
Step 3: 实现代码
"""
        tracker.parse_thinking(thinking)
        emit_mock.reset_mock()
        return tracker, emit_mock

    def _make_tracker(self):
        emit_mock = MagicMock()
        tracker = PlanTracker("test-session", emit_callback=emit_mock)
        return tracker, emit_mock

    def test_step_completion(self):
        tracker, emit_mock = self._make_tracker_with_plan()
        tracker.parse_thinking("Step 1 已完成")
        assert tracker.steps[0]["status"] == "completed"
        emit_mock.assert_called_with(
            SSEEventType.plan_step_complete,
            {"plan_id": "test-session", "step_index": 0, "result_summary": "分析需求"},
        )

    def test_step_failure(self):
        tracker, emit_mock = self._make_tracker_with_plan()
        tracker.parse_thinking("Step 2 执行失败")
        assert tracker.steps[1]["status"] == "failed"
        emit_mock.assert_called_with(
            SSEEventType.plan_step_failed,
            {"plan_id": "test-session", "step_index": 1, "error_summary": "设计方案", "will_adjust": True},
        )

    def test_step_start_detection(self):
        tracker, emit_mock = self._make_tracker_with_plan()
        tracker.parse_thinking("我现在执行 Step 1: 分析需求 的过程中")
        assert tracker.steps[0]["status"] == "in_progress"

    def test_multiple_step_results_in_single_block(self):
        tracker, emit_mock = self._make_tracker_with_plan()
        tracker.parse_thinking("Step 1 已完成\nStep 2 也完成")
        assert tracker.steps[0]["status"] == "completed"
        assert tracker.steps[1]["status"] == "completed"

    def test_step_id_stability(self):
        """Same description should produce same ID — preserves status across plan adjustments."""
        tracker, _ = self._make_tracker()
        id1 = tracker._make_step_id("分析需求")
        id2 = tracker._make_step_id("分析需求")
        assert id1 == id2

    def test_step_status_preserved_on_adjustment(self):
        """Completed step status must survive plan re-parse."""
        tracker, emit_mock = self._make_tracker()
        tracker.parse_thinking("""执行计划：
Step 1: 分析需求
Step 2: 设计方案
""")
        tracker.parse_thinking("Step 1 已完成")
        assert tracker.steps[0]["status"] == "completed"

        # Plan adjustment adds new step but keeps completed step
        tracker.parse_thinking("""调整执行计划：
Step 1: 分析需求
Step 2: 设计方案（优化版）
Step 3: 实现代码
""")
        assert tracker.steps[0]["status"] == "completed"
        assert tracker.steps[1]["description"] == "设计方案（优化版）"
        # Step 2 gets auto-started because _detect_step_result sees "Step 2: ..."
        assert tracker.steps[1]["status"] == "in_progress"
        assert len(tracker.steps) == 3


class TestPlanAdjustment:
    """Test plan adjustment detection and emission."""

    def _make_tracker(self):
        emit_mock = MagicMock()
        tracker = PlanTracker("test-session", emit_callback=emit_mock)
        return tracker, emit_mock

    def test_plan_adjusted_event(self):
        tracker, emit_mock = self._make_tracker()
        tracker.parse_thinking("""执行计划：
Step 1: 分析需求
Step 2: 设计方案
""")
        emit_mock.reset_mock()

        tracker.parse_thinking("""调整执行计划：
Step 1: 分析需求
Step 2: 设计方案（优化版）
Step 3: 实现代码
""")
        # Should emit plan_adjusted (among other events like plan_step_start)
        emit_mock.assert_any_call(
            SSEEventType.plan_adjusted,
            {
                "plan_id": "test-session",
                "reason": tracker._extract_adjust_reason("调整执行计划：\nStep 1: 分析需求\nStep 2: 设计方案（优化版）\nStep 3: 实现代码\n"),
                "steps": [
                    {"id": tracker.steps[0]["id"], "description": "分析需求"},
                    {"id": tracker.steps[1]["id"], "description": "设计方案（优化版）"},
                    {"id": tracker.steps[2]["id"], "description": "实现代码"},
                ],
                "max_steps": 90,
            },
        )

    def test_same_steps_no_adjust_event(self):
        """If step IDs are unchanged, no plan_adjusted event fires."""
        tracker, emit_mock = self._make_tracker()
        tracker.parse_thinking("""执行计划：
Step 1: 分析需求
""")
        emit_mock.reset_mock()

        # Re-parse same plan — step IDs identical, no event
        tracker.parse_thinking("""执行计划：
Step 1: 分析需求
""")
        emit_mock.assert_not_called()


class TestLLMContextInjection:
    """Test plan_summary_for_llm() output format."""

    def _make_tracker(self):
        emit_mock = MagicMock()
        tracker = PlanTracker("test-session", emit_callback=emit_mock)
        return tracker, emit_mock

    def test_summary_empty_when_no_plan(self):
        tracker, _ = self._make_tracker()
        assert tracker.plan_summary_for_llm() == ""

    def test_summary_format_with_progress(self):
        tracker, _ = self._make_tracker()
        tracker.parse_thinking("""执行计划：
Step 1: 分析需求
Step 2: 设计方案
Step 3: 实现代码
""")
        tracker.parse_thinking("Step 1 已完成")
        tracker.parse_thinking("Step 2: 设计方案")

        summary = tracker.plan_summary_for_llm()
        assert "[当前计划进度]" in summary
        assert "● Step 1: 分析需求 (已完成)" in summary
        assert "◉ Step 2: 设计方案 (执行中)" in summary
        assert "○ Step 3: 实现代码 (待执行)" in summary

    def test_summary_with_goal(self):
        tracker, _ = self._make_tracker()
        tracker.parse_thinking("用户要求开发新功能\n执行计划：\nStep 1: 分析\n")
        summary = tracker.plan_summary_for_llm()
        assert "目标:" in summary

    def test_summary_with_failed_step(self):
        tracker, _ = self._make_tracker()
        tracker.parse_thinking("""执行计划：
Step 1: 分析
Step 2: 实现
""")
        tracker.parse_thinking("Step 2 执行失败")

        summary = tracker.plan_summary_for_llm()
        assert "✕ Step 2: 实现 (已失败)" in summary


class TestPlanComplete:
    """Test plan completion lifecycle."""

    def _make_tracker(self):
        emit_mock = MagicMock()
        tracker = PlanTracker("test-session", emit_callback=emit_mock)
        return tracker, emit_mock

    def test_emit_plan_complete(self):
        tracker, emit_mock = self._make_tracker()
        tracker.parse_thinking("""执行计划：
Step 1: 分析需求
""")
        emit_mock.reset_mock()

        tracker.emit_plan_complete("任务完成")
        emit_mock.assert_called_with(
            SSEEventType.plan_complete,
            {"plan_id": "test-session", "summary": "任务完成"},
        )

    def test_emit_plan_complete_default_summary(self):
        tracker, emit_mock = self._make_tracker()
        tracker.parse_thinking("""执行计划：
Step 1: 分析
""")
        emit_mock.reset_mock()

        tracker.emit_plan_complete()
        emit_mock.assert_called_with(
            SSEEventType.plan_complete,
            {"plan_id": "test-session", "summary": "所有步骤已完成"},
        )

    def test_emit_plan_complete_no_plan(self):
        """No event if plan was never created."""
        tracker, emit_mock = self._make_tracker()
        tracker.emit_plan_complete()
        emit_mock.assert_not_called()


class TestGetPlanSummary:
    """Test human-readable plan summary for logging."""

    def _make_tracker(self):
        emit_mock = MagicMock()
        tracker = PlanTracker("test-session", emit_callback=emit_mock)
        return tracker, emit_mock

    def test_no_plan(self):
        tracker, _ = self._make_tracker()
        assert tracker.get_plan_summary() == "无计划"

    def test_with_steps(self):
        tracker, _ = self._make_tracker()
        tracker.parse_thinking("""执行计划：
Step 1: 分析需求
Step 2: 设计方案
""")
        tracker.parse_thinking("Step 1 已完成")
        summary = tracker.get_plan_summary()
        assert "● 分析需求" in summary
        assert "○ 设计方案" in summary


class TestNoRedisDependency:
    """Verify PlanTracker has zero Redis/cache dependencies after refactoring."""

    def test_init_no_cache_param(self):
        tracker = PlanTracker("test-session")
        assert not hasattr(tracker, "_cache")
        assert not hasattr(tracker, "_cache_key")

    def test_no_save_method(self):
        tracker = PlanTracker("test-session")
        assert not hasattr(tracker, "_save")

    def test_no_to_dict_method(self):
        tracker = PlanTracker("test-session")
        assert not hasattr(tracker, "to_dict")

    def test_no_from_dict_method(self):
        assert not hasattr(PlanTracker, "from_dict")

    def test_module_no_redis_imports(self):
        """Module should not import any cache-related modules."""
        import app.agent.plan_tracker as pt_module
        source = open(pt_module.__file__).read()
        assert "cache_provider" not in source
        assert "redis" not in source.lower()
        assert "CacheProvider" not in source