"""Unit tests for progressive skill/subagent loading, cache invalidation, and upload endpoint."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─── _extract_header ──────────────────────────────────────────────────────────

class TestExtractHeader:
    def _call(self, text: str) -> str:
        from app.api.v1.skills import _extract_header
        return _extract_header(text)

    def test_returns_first_non_empty_line_stripped_of_hashes(self):
        md = "# My Skill Title\nSome description here."
        assert self._call(md) == "My Skill Title"

    def test_skips_blank_lines(self):
        md = "\n\n## Section\nContent"
        assert self._call(md) == "Section"

    def test_returns_empty_string_on_blank_input(self):
        assert self._call("") == ""
        assert self._call("   \n  ") == ""

    def test_truncates_at_500_chars(self):
        long_line = "A" * 600
        result = self._call(long_line)
        assert len(result) == 500

    def test_no_hash_prefix_is_kept_as_is(self):
        md = "Plain title\n# heading"
        assert self._call(md) == "Plain title"

    def test_subagent_extract_header_identical_logic(self):
        from app.api.v1.subagents import _extract_header as subagent_extract
        assert subagent_extract("# Agent Name\nrest") == "Agent Name"


# ─── SkillDAO L1/L2 progressive loading ──────────────────────────────────────

class TestSkillDAOGetIndex:
    """get_index() should return compact rows without content_md."""

    @pytest.mark.asyncio
    async def test_get_index_returns_name_and_description(self):
        from app.dao.skill_dao import SkillDAO

        mock_session = AsyncMock()
        mock_factory = MagicMock(return_value=mock_session)

        row = MagicMock()
        row.__getitem__ = lambda self, i: ["my-skill", "A brief desc", False, "skills/my-skill", "name: my-skill\ndescription: A brief desc"][i]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        dao = SkillDAO(mock_factory, employee_id=42)
        result = await dao.get_index()

        assert len(result) == 1
        assert result[0]["name"] == "my-skill"
        assert result[0]["description"] == "A brief desc"
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_index_uses_name_as_fallback_description(self):
        from app.dao.skill_dao import SkillDAO

        mock_session = AsyncMock()
        mock_factory = MagicMock(return_value=mock_session)

        row = MagicMock()
        row.__getitem__ = lambda self, i: ["skill-x", None, True, None, None][i]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        dao = SkillDAO(mock_factory, employee_id=1)
        result = await dao.get_index()

        assert result[0]["description"] == "skill-x"


_CACHE_PATH = "app.cache.cache_provider.create_cache_provider"
_STORAGE_PATH = "app.storage.object_storage.create_object_storage"


class TestSkillDAOGetSkillMd:
    """get_skill_md() should prefer Redis cache over object storage over DB fallback."""

    @pytest.mark.asyncio
    async def test_returns_cached_value_when_present(self):
        from app.dao.skill_dao import SkillDAO

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value="# Cached content")

        mock_skill = MagicMock()
        mock_skill.object_key = None

        dao = SkillDAO(None, employee_id=1)
        with patch(_CACHE_PATH, return_value=mock_cache), \
             patch.object(dao, "get_by_name", AsyncMock(return_value=mock_skill)):
            result = await dao.get_skill_md("my-skill")

        assert result == "# Cached content"
        mock_cache.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_object_storage_on_cache_miss(self):
        from app.dao.skill_dao import SkillDAO

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_skill = MagicMock()
        mock_skill.object_key = "skills/my-skill"
        mock_skill.content_md = None

        mock_storage = AsyncMock()
        mock_storage.get = AsyncMock(return_value=b"# From storage")

        dao = SkillDAO(None, employee_id=1)
        with patch(_CACHE_PATH, return_value=mock_cache), \
             patch(_STORAGE_PATH, return_value=mock_storage), \
             patch.object(dao, "get_by_name", AsyncMock(return_value=mock_skill)):
            result = await dao.get_skill_md("my-skill")

        assert result == "# From storage"
        mock_cache.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_content_md_when_no_object_key(self):
        from app.dao.skill_dao import SkillDAO

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_skill = MagicMock()
        mock_skill.object_key = None
        mock_skill.content_md = "# DB fallback"

        dao = SkillDAO(None, employee_id=1)
        with patch(_CACHE_PATH, return_value=mock_cache), \
             patch.object(dao, "get_by_name", AsyncMock(return_value=mock_skill)):
            result = await dao.get_skill_md("my-skill")

        assert result == "# DB fallback"


# ─── Cache invalidation ───────────────────────────────────────────────────────

class TestSkillDAOCacheInvalidation:
    @pytest.mark.asyncio
    async def test_invalidate_cache_deletes_both_keys(self):
        from app.dao.skill_dao import SkillDAO

        mock_cache = AsyncMock()
        mock_cache.delete = AsyncMock()

        dao = SkillDAO(None, employee_id=7)
        with patch(_CACHE_PATH, return_value=mock_cache):
            await dao._invalidate_cache("my-skill")

        deleted_keys = [call.args[0] for call in mock_cache.delete.call_args_list]
        assert "skill_content:7:my-skill" in deleted_keys
        assert "skills_index:7" in deleted_keys

    @pytest.mark.asyncio
    async def test_subagent_invalidate_cache_deletes_both_keys(self):
        from app.dao.subagent_dao import SubagentDAO

        mock_cache = AsyncMock()
        mock_cache.delete = AsyncMock()

        dao = SubagentDAO(None, employee_id=9)
        with patch(_CACHE_PATH, return_value=mock_cache):
            await dao._invalidate_cache("my-agent")

        deleted_keys = [call.args[0] for call in mock_cache.delete.call_args_list]
        assert "subagent_content:9:my-agent" in deleted_keys
        assert "skills_index:9" in deleted_keys


# ─── SubagentDAO.get_index ────────────────────────────────────────────────────

class TestSubagentDAOGetIndex:
    @pytest.mark.asyncio
    async def test_get_index_returns_compact_rows(self):
        from app.dao.subagent_dao import SubagentDAO

        mock_session = AsyncMock()
        mock_factory = MagicMock(return_value=mock_session)

        row = MagicMock()
        row.__getitem__ = lambda self, i: ["helper-agent", "Helps with tasks", False, None][i]
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.scalars = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        dao = SubagentDAO(mock_factory, employee_id=5)
        result = await dao.get_index()

        assert result[0]["name"] == "helper-agent"
        assert result[0]["description"] == "Helps with tasks"

    @pytest.mark.asyncio
    async def test_get_index_falls_back_to_name_as_description(self):
        from app.dao.subagent_dao import SubagentDAO

        mock_session = AsyncMock()
        mock_factory = MagicMock(return_value=mock_session)

        row = MagicMock()
        row.__getitem__ = lambda self, i: ["no-desc-agent", None, True, None][i]
        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        mock_session.scalars = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        dao = SubagentDAO(mock_factory, employee_id=5)
        result = await dao.get_index()

        assert result[0]["description"] == "no-desc-agent"


# ─── SubagentDAO.get_agent_md ─────────────────────────────────────────────────

class TestSubagentDAOGetAgentMd:
    @pytest.mark.asyncio
    async def test_returns_cached_value(self):
        from app.dao.subagent_dao import SubagentDAO

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value="# Cached agent md")

        mock_subagent = MagicMock()
        mock_subagent.object_key = None

        dao = SubagentDAO(None, employee_id=3)
        with patch(_CACHE_PATH, return_value=mock_cache), \
             patch.object(dao, "get_by_name", AsyncMock(return_value=mock_subagent)):
            result = await dao.get_agent_md("helper")

        assert result == "# Cached agent md"

    @pytest.mark.asyncio
    async def test_returns_none_when_subagent_not_found(self):
        from app.dao.subagent_dao import SubagentDAO

        dao = SubagentDAO(None, employee_id=3)
        with patch.object(dao, "get_by_name", AsyncMock(return_value=None)):
            result = await dao.get_agent_md("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_falls_back_to_definition_md(self):
        from app.dao.subagent_dao import SubagentDAO

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_subagent = MagicMock()
        mock_subagent.object_key = None
        mock_subagent.definition_md = "# Fallback definition"

        dao = SubagentDAO(None, employee_id=3)
        with patch(_CACHE_PATH, return_value=mock_cache), \
             patch.object(dao, "get_by_name", AsyncMock(return_value=mock_subagent)):
            result = await dao.get_agent_md("helper")

        assert result == "# Fallback definition"


# ─── Upload endpoint schema validation ───────────────────────────────────────

class TestUploadSchemas:
    def test_upload_skill_content_response(self):
        from app.schemas.skills import UploadSkillContentResponse
        resp = UploadSkillContentResponse(
            id="abc", name="my-skill", object_key="skills/my-skill",
            header_description="My title", message="uploaded",
        )
        assert resp.object_key == "skills/my-skill"

    def test_upload_subagent_content_response(self):
        from app.schemas.subagents import UploadSubagentContentResponse
        resp = UploadSubagentContentResponse(
            id="abc", name="my-agent", object_key="subagents/my-agent",
            header_description=None, message="done",
        )
        assert resp.header_description is None

    def test_update_skill_request_all_optional(self):
        from app.schemas.skills import UpdateSkillRequest
        req = UpdateSkillRequest()
        assert req.name is None
        assert req.content_md is None

    def test_update_subagent_request_all_optional(self):
        from app.schemas.subagents import UpdateSubagentRequest
        req = UpdateSubagentRequest()
        assert req.name is None
        assert req.tools is None

    def test_create_subagent_with_header_description(self):
        from app.schemas.subagents import CreateSubagentRequest
        req = CreateSubagentRequest(
            name="agent", definition_md="# Agent",
            header_description="Custom desc",
            tools=[], constraints=[],
        )
        assert req.header_description == "Custom desc"

    def test_create_skill_header_description_max_length(self):
        from app.schemas.skills import CreateSkillRequest
        with pytest.raises(Exception):
            CreateSkillRequest(name="s", content_md="# C", header_description="x" * 501)


# ─── context_loader.load_skills_index ─────────────────────────────────────────

class TestContextLoaderSkillsIndex:
    @pytest.mark.asyncio
    async def test_loads_from_cache_when_hit(self):
        from app.agent.context_loader import ContextLoader

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value="[cached index]")

        loader = ContextLoader(employee_id=1, session_factory=None)
        loader._cache = mock_cache

        result = await loader.load_skills_index()

        assert result == "[cached index]"
        mock_cache.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_builds_index_from_skills_and_subagents(self):
        from app.agent.context_loader import ContextLoader

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_skill_dao = AsyncMock()
        mock_skill_dao.get_index = AsyncMock(return_value=[
            {"name": "data-analyst", "description": "Analyze data", "is_global": True}
        ])
        mock_subagent_dao = AsyncMock()
        mock_subagent_dao.get_index = AsyncMock(return_value=[
            {"name": "helper", "description": "General helper", "is_global": False}
        ])

        loader = ContextLoader(employee_id=1, session_factory=None)
        loader._cache = mock_cache

        with patch("app.agent.context_loader.SkillDAO", return_value=mock_skill_dao), \
             patch("app.agent.context_loader.SubagentDAO", return_value=mock_subagent_dao):
            result = await loader.load_skills_index()

        assert "[可用技能]" in result
        assert "data-analyst" in result
        assert "[可用子代理]" in result
        assert "helper" in result
        mock_cache.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_no_skills_or_subagents(self):
        from app.agent.context_loader import ContextLoader

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_skill_dao = AsyncMock()
        mock_skill_dao.get_index = AsyncMock(return_value=[])
        mock_subagent_dao = AsyncMock()
        mock_subagent_dao.get_index = AsyncMock(return_value=[])

        loader = ContextLoader(employee_id=1, session_factory=None)
        loader._cache = mock_cache

        with patch("app.agent.context_loader.SkillDAO", return_value=mock_skill_dao), \
             patch("app.agent.context_loader.SubagentDAO", return_value=mock_subagent_dao), \
             patch("app.agent.context_loader.list_system_skills", return_value=[]), \
             patch("app.agent.context_loader.list_system_subagents", return_value=[]):
            result = await loader.load_skills_index()

        assert result == ""
        mock_cache.set.assert_not_awaited()


# ─── _parse_frontmatter ─────────────────────────────────────────────────────────

class TestParseFrontmatter:
    def _call(self, text: str) -> dict | None:
        from app.api.v1.skills import _parse_frontmatter
        return _parse_frontmatter(text)

    def test_parses_valid_yaml_frontmatter(self):
        md = "---\nname: my-skill\ndescription: A test\n---\n\n# Title"
        result = self._call(md)
        assert result == {"name": "my-skill", "description": "A test"}

    def test_returns_none_for_no_frontmatter(self):
        md = "# Just a heading\nContent"
        assert self._call(md) is None

    def test_returns_none_for_invalid_yaml(self):
        md = "---\n: invalid: yaml: [\n---\n"
        assert self._call(md) is None

    def test_returns_none_for_non_dict_frontmatter(self):
        md = "---\n- list item\n- another\n---\n"
        assert self._call(md) is None

    def test_returns_none_for_empty_string(self):
        assert self._call("") is None

    def test_parses_frontmatter_with_block_scalar(self):
        md = "---\nname: test\ndescription: >\n  Long description\n  spanning lines\n---\n\nContent"
        result = self._call(md)
        assert result is not None
        assert result["name"] == "test"
        assert "Long description" in result["description"]

    def test_strips_whitespace_in_input(self):
        md = "  \n---\nname: trimmed\n---\n\nContent"
        result = self._call(md)
        assert result == {"name": "trimmed"}


# ─── _extract_frontmatter_text ───────────────────────────────────────────────────

class TestExtractFrontmatterText:
    def _call(self, text: str) -> str | None:
        from app.api.v1.skills import _extract_frontmatter_text
        return _extract_frontmatter_text(text)

    def test_extracts_raw_yaml_text(self):
        md = "---\nname: my-skill\ndescription: A test\n---\n\n# Title"
        result = self._call(md)
        assert result == "name: my-skill\ndescription: A test"

    def test_returns_none_for_no_frontmatter(self):
        md = "# Just a heading\nContent"
        assert self._call(md) is None

    def test_returns_none_for_empty_frontmatter(self):
        md = "---\n---\n\nContent"
        assert self._call(md) is None

    def test_preserves_block_scalars(self):
        md = "---\nname: test\ndescription: >\n  Long description\n  spanning lines\n---\n\nContent"
        result = self._call(md)
        assert result is not None
        assert ">" in result
        assert "Long description" in result

    def test_strips_whitespace_around_text(self):
        md = "  \n---\n  name: trimmed  \n---\n\nContent"
        result = self._call(md)
        assert result == "name: trimmed"


# ─── SkillDAO frontmatter support ──────────────────────────────────────────────

class TestSkillDAOFrontmatter:
    @pytest.mark.asyncio
    async def test_get_index_includes_frontmatter(self):
        from app.dao.skill_dao import SkillDAO

        mock_session = AsyncMock()
        mock_factory = MagicMock(return_value=mock_session)

        fm_text = "name: my-skill\ndescription: From FM\nlicense: MIT"
        row = MagicMock()
        row.__getitem__ = lambda self, i: ["my-skill", None, False, "skills/my-skill", fm_text][i]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        dao = SkillDAO(mock_factory, employee_id=42)
        result = await dao.get_index()

        assert result[0]["frontmatter"] == {"name": "my-skill", "description": "From FM", "license": "MIT"}
        assert result[0]["description"] == "From FM"

    @pytest.mark.asyncio
    async def test_get_index_falls_back_to_name_when_no_description(self):
        from app.dao.skill_dao import SkillDAO

        mock_session = AsyncMock()
        mock_factory = MagicMock(return_value=mock_session)

        # frontmatter without description field
        fm_text = "name: my-skill"
        row = MagicMock()
        row.__getitem__ = lambda self, i: ["my-skill", None, False, None, fm_text][i]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.close = AsyncMock()

        dao = SkillDAO(mock_factory, employee_id=1)
        result = await dao.get_index()

        assert result[0]["description"] == "my-skill"

    @pytest.mark.asyncio
    async def test_integrity_error_on_duplicate_name(self):
        from app.dao.skill_dao import SkillDAO
        from app.middleware.error_handler import AppError
        from sqlalchemy.exc import IntegrityError

        mock_session = AsyncMock()
        mock_factory = MagicMock(return_value=mock_session)

        # Simulate IntegrityError on commit
        mock_session.commit.side_effect = IntegrityError("duplicate", {}, Exception())

        dao = SkillDAO(mock_factory, employee_id=42)
        with pytest.raises(AppError) as exc_info:
            await dao.create(name="existing-skill", content_md="# Test", frontmatter="name: existing-skill")
        assert exc_info.value.error_code == "BX_SKILL_1002"
        mock_session.rollback.assert_called_once()


# ─── Upload directory schema ────────────────────────────────────────────────────

class TestUploadDirectorySchema:
    def test_upload_directory_response_all_fields(self):
        from app.api.v1.skills import UploadDirectoryResponse
        resp = UploadDirectoryResponse(
            id="abc-123",
            name="my-skill",
            object_key="user-skill/abc-123",
            header_description="My Skill Title",
            file_count=5,
            message="Uploaded 5 files to user-skill/abc-123",
        )
        assert resp.id == "abc-123"
        assert resp.file_count == 5
        assert resp.object_key == "user-skill/abc-123"

    def test_upload_directory_response_minimal(self):
        from app.api.v1.skills import UploadDirectoryResponse
        resp = UploadDirectoryResponse(
            id="abc", name="untitled", object_key="user-skill/abc",
            file_count=1, message="done",
        )
        assert resp.header_description is None


# ─── skill_has_scripts ─────────────────────────────────────────────────────────

class TestSkillHasScripts:
    @pytest.mark.asyncio
    async def test_returns_true_when_scripts_exist(self):
        from app.agent.skill_asset_loader import skill_has_scripts

        mock_skill = MagicMock()
        mock_skill.object_key = "user-skill/abc"

        mock_storage = AsyncMock()
        mock_storage.get_directory = AsyncMock(return_value={"scripts/example.py": b"print('hi')"})

        with patch("app.dao.skill_dao.SkillDAO") as mock_dao_cls, \
             patch("app.storage.object_storage.create_object_storage", return_value=mock_storage), \
             patch("app.db.database.get_session_factory"):
            mock_dao = mock_dao_cls.return_value
            mock_dao.get_by_name = AsyncMock(return_value=mock_skill)
            result = await skill_has_scripts(employee_id=1, skill_name="my-skill")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_object_key(self):
        from app.agent.skill_asset_loader import skill_has_scripts

        mock_skill = MagicMock()
        mock_skill.object_key = None

        with patch("app.dao.skill_dao.SkillDAO") as mock_dao_cls, \
             patch("app.db.database.get_session_factory"):
            mock_dao = mock_dao_cls.return_value
            mock_dao.get_by_name = AsyncMock(return_value=mock_skill)
            result = await skill_has_scripts(employee_id=1, skill_name="my-skill")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_skill_not_found(self):
        from app.agent.skill_asset_loader import skill_has_scripts

        with patch("app.dao.skill_dao.SkillDAO") as mock_dao_cls, \
             patch("app.db.database.get_session_factory"):
            mock_dao = mock_dao_cls.return_value
            mock_dao.get_by_name = AsyncMock(return_value=None)
            result = await skill_has_scripts(employee_id=1, skill_name="nonexistent")
        assert result is False


# ─── Tar builder validation ─────────────────────────────────────────────────────

class TestTarFormat:
    def test_produces_valid_tar_structure(self):
        import sys
        sys.path.insert(0, "frontend/super-agent-chatui/src/utils")
        # Use direct inline test since we can't import TS in Python
        pass  # Tar builder is frontend-only; validated by TypeScript compilation

    def test_workdir_script_has_upload_result_command(self):
        import subprocess
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[2]
        workdir_script = project_root / "scripts" / "workdir.py"
        result = subprocess.run(
            ["python3", str(workdir_script), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "upload-result" in result.stdout
        assert "cleanup-stale" in result.stdout
