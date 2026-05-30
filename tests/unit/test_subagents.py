"""Tests for subagent system — agent_loader, tool_filter, AgentDefinition."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAgentDefinition:
    def test_agent_definition_creation(self):
        from app.subagents.agent_definition import AgentDefinition, AgentSource, PermissionMode

        agent = AgentDefinition(
            agent_type="Explore",
            when_to_use="For exploring codebases",
            source=AgentSource.BUILTIN,
            system_prompt="You are an explorer.",
            tools=["file_read", "Bash"],
            disallowed_tools=["code_execute"],
            max_turns=10,
            model="inherit",
            permission_mode=PermissionMode.DEFAULT,
            color="#6B8E23",
            background=False,
            filename="explore",
        )
        assert agent.agent_type == "Explore"
        assert agent.max_turns == 10
        assert agent.source == AgentSource.BUILTIN
        assert agent.model == "inherit"

    def test_agent_definition_defaults(self):
        from app.subagents.agent_definition import AgentDefinition

        agent = AgentDefinition(
            agent_type="Test",
            when_to_use="For testing",
            system_prompt="system",
        )
        assert agent.source.value == "builtin"
        assert agent.max_turns == 10
        assert agent.tools is None
        assert agent.disallowed_tools is None
        assert agent.model is None
        assert agent.permission_mode is None
        assert agent.background is False

    def test_agent_definition_summary(self):
        from app.subagents.agent_definition import AgentDefinition, AgentDefinitionSummary, AgentSource

        agent = AgentDefinition(
            agent_type="Explore",
            when_to_use="For exploring",
            source=AgentSource.BUILTIN,
            system_prompt="You are an explorer.",
            tools=["file_read"],
            color="#fff",
        )
        summary = AgentDefinitionSummary(
            agent_type=agent.agent_type,
            when_to_use=agent.when_to_use,
            source=agent.source,
            tools=agent.tools,
            color=agent.color,
        )
        assert summary.agent_type == "Explore"
        assert summary.tools == ["file_read"]


class TestToolFilter:
    def test_global_disallowed_tools(self):
        from app.subagents.tool_filter import GLOBAL_DISALLOWED_TOOLS
        assert "spawn_subagent" in GLOBAL_DISALLOWED_TOOLS

    def test_filter_with_allowlist(self):
        from app.subagents.tool_filter import filter_tools_for_agent
        from app.subagents.agent_definition import AgentDefinition

        all_tools = [
            {"function": {"name": "file_read"}},
            {"function": {"name": "file_write"}},
            {"function": {"name": "spawn_subagent"}},
        ]
        agent = AgentDefinition(
            agent_type="Test",
            when_to_use="test",
            system_prompt="test",
            tools=["file_read"],  # allowlist
        )
        result = filter_tools_for_agent(all_tools, agent)
        names = [t["function"]["name"] for t in result]
        assert names == ["file_read"]

    def test_filter_with_star(self):
        from app.subagents.tool_filter import filter_tools_for_agent
        from app.subagents.agent_definition import AgentDefinition

        all_tools = [
            {"function": {"name": "file_read"}},
            {"function": {"name": "file_write"}},
            {"function": {"name": "spawn_subagent"}},
        ]
        agent = AgentDefinition(
            agent_type="Test",
            when_to_use="test",
            system_prompt="test",
            tools=["*"],
        )
        result = filter_tools_for_agent(all_tools, agent)
        names = [t["function"]["name"] for t in result]
        # All except global disallowed
        assert "file_read" in names
        assert "file_write" in names
        assert "spawn_subagent" not in names

    def test_filter_disallowed_tools(self):
        from app.subagents.tool_filter import filter_tools_for_agent
        from app.subagents.agent_definition import AgentDefinition

        all_tools = [
            {"function": {"name": "file_read"}},
            {"function": {"name": "code_execute"}},
            {"function": {"name": "spawn_subagent"}},
        ]
        agent = AgentDefinition(
            agent_type="Test",
            when_to_use="test",
            system_prompt="test",
            tools=["*"],
            disallowed_tools=["code_execute"],
        )
        result = filter_tools_for_agent(all_tools, agent)
        names = [t["function"]["name"] for t in result]
        assert "file_read" in names
        assert "code_execute" not in names
        assert "spawn_subagent" not in names

    def test_filter_no_tools_is_all(self):
        from app.subagents.tool_filter import filter_tools_for_agent
        from app.subagents.agent_definition import AgentDefinition

        all_tools = [
            {"function": {"name": "file_read"}},
            {"function": {"name": "file_write"}},
            {"function": {"name": "spawn_subagent"}},
        ]
        agent = AgentDefinition(
            agent_type="Test",
            when_to_use="test",
            system_prompt="test",
            tools=None,
        )
        result = filter_tools_for_agent(all_tools, agent)
        names = [t["function"]["name"] for t in result]
        assert "file_read" in names
        assert "file_write" in names
        assert "spawn_subagent" not in names


class TestAgentLoaderParsing:
    def test_parse_agent_from_markdown_basic(self):
        from app.subagents.agent_loader import parse_agent_from_markdown

        content = """---
name: TestAgent
description: A test agent for unit testing
tools:
  - file_read
  - Bash
maxTurns: 5
model: inherit
---
You are a test agent. Use your tools wisely."""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            agent = parse_agent_from_markdown(Path(tmp_path), "test-agent")
            assert agent is not None
            assert agent.agent_type == "TestAgent"
            assert agent.when_to_use == "A test agent for unit testing"
            assert agent.tools == ["file_read", "Bash"]
            assert agent.max_turns == 5
            assert agent.model == "inherit"
            assert agent.system_prompt == "You are a test agent. Use your tools wisely."
            assert agent.filename == "test-agent"
            assert agent.resource_dir == str(Path(tmp_path).parent.resolve())
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_parse_agent_dir_template_substitution(self):
        from app.subagents.agent_loader import parse_agent_from_markdown

        content = """---
name: Reviewer
description: A code reviewer
---
You are a reviewer. Read the checklist at ${AGENT_DIR}/data/checklist.json."""

        # Use a temp directory to test path resolution
        with tempfile.TemporaryDirectory() as tmp_dir:
            agent_md = Path(tmp_dir) / "AGENT.md"
            agent_md.write_text(content, encoding="utf-8")
            agent = parse_agent_from_markdown(agent_md, "reviewer")

            assert agent is not None
            assert "${AGENT_DIR}" not in agent.system_prompt
            assert agent.resource_dir == str(Path(tmp_dir).resolve())
            assert f"{Path(tmp_dir).resolve()}/data/checklist.json" in agent.system_prompt

    def test_parse_agent_from_markdown_star_tools(self):
        from app.subagents.agent_loader import parse_agent_from_markdown

        content = """---
name: GpAgent
description: A general purpose agent
tools:
  - "*"
---
Do whatever is needed."""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            agent = parse_agent_from_markdown(Path(tmp_path), "gp")
            assert agent is not None
            assert agent.tools == ["*"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_parse_agent_missing_name(self):
        from app.subagents.agent_loader import parse_agent_from_markdown

        content = """---
description: No name here
---
Body."""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            agent = parse_agent_from_markdown(Path(tmp_path))
            assert agent is None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_parse_agent_no_frontmatter(self):
        from app.subagents.agent_loader import parse_agent_from_markdown

        content = "Just a plain markdown file without frontmatter."

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            agent = parse_agent_from_markdown(Path(tmp_path))
            assert agent is None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_parse_agent_string_list_comma(self):
        from app.subagents.agent_loader import parse_agent_from_markdown

        content = """---
name: CommaAgent
description: Comma-separated tools
tools: file_read, Bash, web_search
---
Body."""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            agent = parse_agent_from_markdown(Path(tmp_path))
            assert agent is not None
            assert agent.tools == ["file_read", "Bash", "web_search"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_parse_agent_disallowed_tools(self):
        from app.subagents.agent_loader import parse_agent_from_markdown

        content = """---
name: RestrictedAgent
description: Has disallowed tools
disallowedTools:
  - code_execute
  - file_write
---
Body."""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            agent = parse_agent_from_markdown(Path(tmp_path))
            assert agent is not None
            assert agent.disallowed_tools == ["code_execute", "file_write"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_parse_real_ag_md_files(self):
        from app.subagents.agent_loader import parse_agent_from_markdown

        project_root = Path(__file__).parent.parent.parent
        for name, expected_type in [
            ("explore", "Explore"),
            ("plan", "Plan"),
            ("general-purpose", "general-purpose"),
        ]:
            path = project_root / "sys-infra" / "subagents" / name / "AGENT.md"
            agent = parse_agent_from_markdown(path, name)
            assert agent is not None, f"{name}/AGENT.md should parse"
            assert agent.agent_type == expected_type, f"{name} should have type {expected_type}"
            assert agent.system_prompt, f"{name} should have a body"


class TestSubagentLoader:
    @pytest.mark.asyncio
    async def test_loader_initializes_and_lists_builtins(self):
        from app.subagents.agent_loader import SubagentLoader

        loader = SubagentLoader()
        loader._loaded = False
        loader._registry = {}
        agents = await loader.list_agents()
        names = {a.agent_type for a in agents}
        assert "Explore" in names
        assert "Plan" in names
        assert "general-purpose" in names

    @pytest.mark.asyncio
    async def test_loader_get_agent(self):
        from app.subagents.agent_loader import SubagentLoader

        loader = SubagentLoader()
        loader._loaded = False
        loader._registry = {}
        explore = await loader.get_agent("Explore")
        assert explore is not None
        assert explore.agent_type == "Explore"
        assert explore.max_turns == 10
        assert explore.tools == ["file_read", "file_search", "Bash", "web_search", "web_fetch"]

    @pytest.mark.asyncio
    async def test_loader_get_nonexistent(self):
        from app.subagents.agent_loader import SubagentLoader

        loader = SubagentLoader()
        loader._loaded = False
        loader._registry = {}
        agent = await loader.get_agent("NonExistent")
        assert agent is None

    @pytest.mark.asyncio
    async def test_loader_builtin_priority_over_db(self):
        from app.subagents.agent_loader import SubagentLoader

        loader = SubagentLoader()
        loader._loaded = False
        loader._registry = {}
        explore = await loader.get_agent("Explore")
        assert explore is not None
        assert explore.source.value == "builtin"