import uuid
from sqlalchemy import select, update
from app.dao.base import BaseDAO
from app.models.models import Subagent as SubagentModel
from app.models.base import GLOBAL_EMPLOYEE_ID
from app.middleware.error_handler import AppError


class SubagentDAO(BaseDAO):
    async def list_subagents(self) -> list[SubagentModel]:
        session = self._session()
        result = await session.scalars(
            select(SubagentModel).where(
                self._filter_user_or_global(SubagentModel), SubagentModel.is_deleted == 0
            )
        )
        items = result.all()
        await session.close()
        return items

    async def create(self, name: str, definition_md: str, tools: list[str], constraints: list[str], is_global: bool = False) -> SubagentModel:
        session = self._session()
        import json
        eid = GLOBAL_EMPLOYEE_ID if is_global else self._employee_id
        obj = SubagentModel(
            id=str(uuid.uuid4()),
            employee_id=eid,
            name=name,
            definition_md=definition_md,
            tools=json.dumps(tools),
            constraints=json.dumps(constraints),
            is_global=int(is_global),
        )
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        await session.close()
        return obj

    async def get_by_name(self, name: str) -> SubagentModel | None:
        session = self._session()
        obj = await session.scalar(
            select(SubagentModel).where(
                SubagentModel.name == name,
                self._filter_user_or_global(SubagentModel),
                SubagentModel.is_deleted == 0,
            )
        )
        await session.close()
        return obj

    async def get_by_id(self, subagent_id: str) -> SubagentModel:
        session = self._session()
        obj = await session.scalar(
            select(SubagentModel).where(
                SubagentModel.id == subagent_id,
                self._filter_user_or_global(SubagentModel),
                SubagentModel.is_deleted == 0,
            )
        )
        await session.close()
        if not obj:
            raise AppError("BX_SUBAGENT_1001", "Subagent not found", 404)
        return obj

    async def get_index(self) -> list[dict]:
        """Return compact subagent index (name + header_description) for system prompt.
        Progressive loading L1: only header info, no full definition_md."""
        session = self._session()
        result = await session.scalars(
            select(SubagentModel.name, SubagentModel.header_description,
                   SubagentModel.is_global, SubagentModel.object_key)
            .where(self._filter_user_or_global(SubagentModel), SubagentModel.is_deleted == 0)
            .order_by(SubagentModel.is_global.desc(), SubagentModel.name.asc())
        )
        items = [
            {"name": r[0], "description": r[1] or r[0], "is_global": r[2], "object_key": r[3]}
            for r in result.all()
        ]
        await session.close()
        return items

    async def get_agent_md(self, name: str) -> str | None:
        """Get AGENT.md content for a subagent. L2 lazy load.
        Priority: cache → object storage → definition_md fallback."""
        from app.cache.cache_provider import create_cache_provider
        from app.storage.object_storage import create_object_storage

        subagent = await self.get_by_name(name)
        if not subagent:
            return None

        cache = create_cache_provider(self._session_factory, self._employee_id)
        cached = await cache.get(f"subagent_content:{self._employee_id}:{name}")
        if cached:
            return cached

        if subagent.object_key:
            obj_storage = create_object_storage()
            content = await obj_storage.get(self._employee_id, f"{subagent.object_key}/AGENT.md")
            if content:
                text = content.decode("utf-8") if isinstance(content, bytes) else content
                await cache.set(f"subagent_content:{self._employee_id}:{name}", text, ttl=300)
                return text

        if subagent.definition_md:
            await cache.set(f"subagent_content:{self._employee_id}:{name}", subagent.definition_md, ttl=300)
            return subagent.definition_md

        return None

    async def update(self, subagent_id: str, **kwargs) -> SubagentModel:
        import json as _json
        session = self._session()
        obj = await session.scalar(
            select(SubagentModel).where(SubagentModel.id == subagent_id)
        )
        if not obj:
            raise AppError("BX_SUBAGENT_1001", "Subagent not found", 404)
        if obj.employee_id == GLOBAL_EMPLOYEE_ID:
            raise AppError("BX_SUBAGENT_1003", "Cannot modify global subagents", 403)
        for key, val in kwargs.items():
            if key == "tools":
                setattr(obj, "tools", _json.dumps(val))
            elif key == "constraints":
                setattr(obj, "constraints", _json.dumps(val))
            elif val is not None:
                setattr(obj, key, val)
        await session.commit()
        await session.refresh(obj)
        updated_name = obj.name
        await session.close()
        await self._invalidate_cache(updated_name)
        return obj

    async def soft_delete(self, subagent_id: str) -> None:
        obj = await self.get_by_id(subagent_id)
        subagent_name = obj.name
        session = self._session()
        await session.execute(
            update(SubagentModel).where(SubagentModel.id == subagent_id).values(is_deleted=1)
        )
        await session.commit()
        await session.close()
        await self._invalidate_cache(subagent_name)

    async def update_object_key(self, subagent_id: str, object_key: str,
                                 header_description: str | None = None) -> None:
        session = self._session()
        values: dict = {"object_key": object_key}
        if header_description is not None:
            values["header_description"] = header_description
        await session.execute(
            update(SubagentModel).where(SubagentModel.id == subagent_id).values(**values)
        )
        await session.commit()
        await session.close()
        obj = await self.get_by_id(subagent_id)
        await self._invalidate_cache(obj.name)

    async def _invalidate_cache(self, subagent_name: str) -> None:
        from app.cache.cache_provider import create_cache_provider
        cache = create_cache_provider(self._session_factory, self._employee_id)
        await cache.delete(f"subagent_content:{self._employee_id}:{subagent_name}")
        await cache.delete(f"skills_index:{self._employee_id}")