import hashlib
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from app.dependencies import get_employee_id
from app.db.database import get_session_factory
from app.dao.skill_dao import SkillDAO
from app.schemas.skills import (
    SkillListResponse, SkillItem,
    CreateSkillRequest, CreateSkillResponse,
    UpdateSkillRequest, UpdateSkillResponse,
    UploadSkillContentResponse,
)
from app.schemas.common import SuccessResponse

router = APIRouter()


def _extract_header(content_md: str) -> str:
    """Extract first non-empty line from SKILL.md as header_description."""
    for line in content_md.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:500]
    return ""


@router.get("/skills", response_model=SkillListResponse)
async def list_skills(
    scope: str = Query("all", pattern="^(all|global|personal)$"),
    include_content: bool = Query(False),
    employee_id: int = Depends(get_employee_id),
):
    from app.storage.sys_infra import list_sys_infra_skill_items

    dao = SkillDAO(get_session_factory(), employee_id)
    db_items = await dao.list_skills()
    if scope == "global":
        db_items = [s for s in db_items if s.employee_id == 0]
    elif scope == "personal":
        db_items = [s for s in db_items if s.employee_id != 0]

    result = [
        SkillItem(
            id=s.id, name=s.name,
            content_md=s.content_md if include_content else "",
            header_description=s.header_description, object_key=s.object_key,
            is_global=bool(s.is_global), usage_count=s.usage_count, created_at=s.created_at,
            source="user",
        )
        for s in db_items
    ]

    if scope in ("all", "global"):
        sys_items = await list_sys_infra_skill_items(include_content=include_content)
        result.extend(SkillItem(**item) for item in sys_items)

    return SkillListResponse(skills=result)


@router.get("/skills/{skill_id}", response_model=SkillItem)
async def get_skill(
    skill_id: str,
    employee_id: int = Depends(get_employee_id),
):
    dao = SkillDAO(get_session_factory(), employee_id)
    s = await dao.get_by_id(skill_id)
    return SkillItem(
        id=s.id, name=s.name, content_md=s.content_md,
        header_description=s.header_description, object_key=s.object_key,
        is_global=bool(s.is_global), usage_count=s.usage_count, created_at=s.created_at,
    )


@router.post("/skills", response_model=CreateSkillResponse)
async def create_skill(
    req: CreateSkillRequest,
    employee_id: int = Depends(get_employee_id),
):
    dao = SkillDAO(get_session_factory(), employee_id)
    header = req.header_description or _extract_header(req.content_md)
    skill = await dao.create(name=req.name, content_md=req.content_md, is_global=req.is_global)
    if header:
        await dao.update(skill.id, header_description=header)
    return CreateSkillResponse(id=skill.id, name=skill.name, created_at=skill.created_at)


@router.put("/skills/{skill_id}", response_model=UpdateSkillResponse)
async def update_skill(
    skill_id: str,
    req: UpdateSkillRequest,
    employee_id: int = Depends(get_employee_id),
):
    dao = SkillDAO(get_session_factory(), employee_id)
    s = await dao.update(
        skill_id,
        name=req.name,
        content_md=req.content_md,
        header_description=req.header_description,
    )
    return UpdateSkillResponse(
        id=s.id, name=s.name, content_md=s.content_md,
        header_description=s.header_description, object_key=s.object_key,
        is_global=bool(s.is_global), usage_count=s.usage_count, updated_at=s.updated_at,
    )


@router.delete("/skills/{skill_id}", response_model=SuccessResponse)
async def delete_skill(
    skill_id: str,
    employee_id: int = Depends(get_employee_id),
):
    dao = SkillDAO(get_session_factory(), employee_id)
    await dao.soft_delete(skill_id)
    return SuccessResponse()


class _UploadContentRequest(BaseModel):
    skill_md: str = Field(..., min_length=1)


@router.put("/skills/{skill_id}/content", response_model=UploadSkillContentResponse)
async def upload_skill_content(
    skill_id: str,
    req: _UploadContentRequest,
    employee_id: int = Depends(get_employee_id),
):
    """Upload SKILL.md content to object storage and update object_key.

    Saves to user-config/{user_id}/skills/{slug}/SKILL.md.
    Updates header_description from the first meaningful line.
    """
    from app.storage.object_storage import create_object_storage

    dao = SkillDAO(get_session_factory(), employee_id)
    skill = await dao.get_by_id(skill_id)

    # Use skill UUID as the unique directory name under user-skill/ (flat layout, no per-user nesting).
    object_key_prefix = f"user-skill/{skill.id}"
    skillmd_key = f"{object_key_prefix}/SKILL.md"

    storage = create_object_storage()
    await storage.put(employee_id, skillmd_key, req.skill_md, content_type="text/markdown")

    content_hash = hashlib.md5(req.skill_md.encode()).hexdigest()
    header = _extract_header(req.skill_md)
    await dao.update_object_key(skill_id, object_key_prefix, content_hash, header_description=header)

    return UploadSkillContentResponse(
        id=skill.id,
        name=skill.name,
        object_key=object_key_prefix,
        header_description=header,
        message=f"SKILL.md uploaded to {skillmd_key}",
    )
