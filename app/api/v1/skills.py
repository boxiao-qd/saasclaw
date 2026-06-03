import hashlib
import io
import tarfile
import yaml
from fastapi import APIRouter, Depends, Query, Request
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
    """Extract description from SKILL.md: frontmatter description field first,
    then fall back to first non-empty body line."""
    stripped = content_md.strip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1])
                if isinstance(fm, dict):
                    desc = fm.get("description")
                    if isinstance(desc, str) and desc.strip():
                        return " ".join(desc.split())[:500]
            except yaml.YAMLError:
                pass
            body = parts[2]
        else:
            body = stripped
    else:
        body = stripped
    for line in body.splitlines():
        line = line.strip().lstrip("#").strip()
        if line and line != "---":
            return line[:500]
    return ""


def _extract_frontmatter_text(content_md: str) -> str | None:
    """Extract raw YAML frontmatter text (between --- delimiters) from SKILL.md."""
    stripped = content_md.strip()
    if not stripped.startswith("---"):
        return None
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return None
    text = parts[1].strip()
    return text if text else None


def _parse_frontmatter(content_md: str) -> dict | None:
    """Parse YAML frontmatter from SKILL.md into a dict (for display/response)."""
    stripped = content_md.strip()
    if not stripped.startswith("---"):
        return None
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
        return fm if isinstance(fm, dict) else None
    except yaml.YAMLError:
        return None


def _parse_frontmatter_text(fm_text: str | None) -> dict | None:
    """Parse a stored frontmatter text string into a dict (for API response)."""
    if not fm_text or not fm_text.strip():
        return None
    try:
        fm = yaml.safe_load(fm_text)
        return fm if isinstance(fm, dict) else None
    except yaml.YAMLError:
        return None


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

    result = []
    for s in db_items:
        parsed_fm = _parse_frontmatter_text(s.frontmatter)
        effective_desc = (
            s.header_description
            or (parsed_fm.get("description") if parsed_fm else None)
            or _extract_header(s.content_md or "")
        )
        result.append(SkillItem(
            id=s.id, name=s.name,
            content_md=s.content_md if include_content else "",
            header_description=effective_desc, object_key=s.object_key,
            is_global=bool(s.is_global), usage_count=s.usage_count, created_at=s.created_at,
            source="user", frontmatter=parsed_fm,
        ))

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
        frontmatter=_parse_frontmatter_text(s.frontmatter),
    )


@router.post("/skills", response_model=CreateSkillResponse)
async def create_skill(
    req: CreateSkillRequest,
    employee_id: int = Depends(get_employee_id),
):
    dao = SkillDAO(get_session_factory(), employee_id)
    frontmatter_text = _extract_frontmatter_text(req.content_md)
    header = req.header_description or _extract_header(req.content_md)
    skill = await dao.create(
        name=req.name, content_md=req.content_md,
        is_global=req.is_global, frontmatter=frontmatter_text,
    )
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
    # Auto-extract frontmatter text from content_md when content is updated
    frontmatter_text: str | None = None
    if req.content_md:
        frontmatter_text = _extract_frontmatter_text(req.content_md)
    s = await dao.update(
        skill_id,
        name=req.name,
        content_md=req.content_md,
        header_description=req.header_description,
        frontmatter=frontmatter_text,
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


class UploadDirectoryResponse(BaseModel):
    id: str
    name: str
    object_key: str
    header_description: str | None = None
    file_count: int
    message: str


@router.post("/skills/upload-directory", response_model=UploadDirectoryResponse)
async def upload_skill_directory(
    request: Request,
    employee_id: int = Depends(get_employee_id),
):
    """Upload a skill directory as tar stream.

    Accepts application/x-tar body containing a complete skill directory
    (SKILL.md + optional scripts/, references/, assets/ subdirectories).
    Unpacks to MinIO under user-skill/{id}/, extracts frontmatter to MySQL.
    """
    from app.storage.object_storage import create_object_storage

    body = await request.body()
    if not body:
        from app.middleware.error_handler import AppError
        raise AppError("BX_SKILL_1004", "Empty request body", 400)

    tar_stream = io.BytesIO(body)
    file_count = 0
    skill_md_content = None
    files_to_upload: list[tuple[str, bytes]] = []

    try:
        with tarfile.open(fileobj=tar_stream, mode="r:") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                # Normalize path: strip leading ./ and any directory traversal
                clean_path = member.name.lstrip("./")
                if ".." in clean_path or clean_path.startswith("/"):
                    continue
                content = tar.extractfile(member)
                if content is None:
                    continue
                data = content.read()
                files_to_upload.append((clean_path, data))
                file_count += 1
                if clean_path == "SKILL.md" or member.name.rstrip("/") == "SKILL.md":
                    skill_md_content = data.decode("utf-8")
    except tarfile.TarError as e:
        from app.middleware.error_handler import AppError
        raise AppError("BX_SKILL_1004", f"Invalid tar archive: {e}", 400)

    if not skill_md_content:
        from app.middleware.error_handler import AppError
        raise AppError("BX_SKILL_1004", "SKILL.md not found in uploaded directory", 400)

    # Extract frontmatter text and name
    frontmatter_text = _extract_frontmatter_text(skill_md_content)
    frontmatter_parsed = _parse_frontmatter(skill_md_content)
    skill_name = (frontmatter_parsed.get("name") if frontmatter_parsed else None) or "untitled"
    header = _extract_header(skill_md_content)

    # Create skill record in MySQL
    dao = SkillDAO(get_session_factory(), employee_id)
    skill = await dao.create(
        name=skill_name,
        content_md=skill_md_content,
        frontmatter=frontmatter_text,
    )
    if header:
        await dao.update(skill.id, header_description=header)

    # Upload all files to MinIO under user-skill/{id}/
    object_key_prefix = f"user-skill/{skill.id}"
    storage = create_object_storage()
    for rel_path, data in files_to_upload:
        key = f"{object_key_prefix}/{rel_path}"
        content_type = "text/markdown" if rel_path.endswith(".md") else "application/octet-stream"
        await storage.put(employee_id, key, data, content_type=content_type)

    content_hash = hashlib.md5(skill_md_content.encode()).hexdigest()
    await dao.update_object_key(skill.id, object_key_prefix, content_hash,
                                header_description=header)

    return UploadDirectoryResponse(
        id=skill.id,
        name=skill_name,
        object_key=object_key_prefix,
        header_description=header,
        file_count=file_count,
        message=f"Uploaded {file_count} files to {object_key_prefix}",
    )


@router.put("/skills/{skill_id}/content", response_model=UploadSkillContentResponse)
async def upload_skill_content(
    skill_id: str,
    req: _UploadContentRequest,
    employee_id: int = Depends(get_employee_id),
):
    """Upload SKILL.md content to object storage and update MySQL metadata.

    Saves to MinIO under user-skill/{id}/SKILL.md.
    Updates content_md, frontmatter and header_description in MySQL.
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
    frontmatter_text = _extract_frontmatter_text(req.skill_md)
    await dao.update(
        skill_id,
        content_md=req.skill_md,
        header_description=header,
        frontmatter=frontmatter_text,
    )
    await dao.update_object_key(skill_id, object_key_prefix, content_hash, header_description=header)

    return UploadSkillContentResponse(
        id=skill.id,
        name=skill.name,
        object_key=object_key_prefix,
        header_description=header,
        message=f"SKILL.md uploaded to {skillmd_key}",
    )
