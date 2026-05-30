from fastapi import APIRouter, Depends
from app.dependencies import get_employee_id
from app.db.database import get_session_factory
from app.dao.profile_dao import ProfileDAO
from app.schemas.settings import SettingsResponse, UpdateSettingsRequest, ModelOption, ToolOption
from app.schemas.common import SuccessResponse
from app.schemas.common import PaginationMeta
from app.config import settings
import json

router = APIRouter()

# Tool catalog — static for now
AVAILABLE_TOOLS = [
    ToolOption(tool_name="web_search", display_name="Web Search", description="Search the web", category="A"),
    ToolOption(tool_name="code_execute", display_name="Code Execute", description="Run code in sandbox", category="B"),
    ToolOption(tool_name="file_read", display_name="File Read", description="Read files", category="C"),
    ToolOption(tool_name="spawn_subagent", display_name="Spawn Sub-agent", description="Delegate to specialized sub-agent", category="D"),
]


def _build_model_options() -> list[ModelOption]:
    """Build model list from config, with friendly display names."""
    display_names = {
        "MiniMax-M2": "MiniMax M2",
        "gpt-4o": "GPT-4o",
        "gpt-4o-mini": "GPT-4o-mini",
        "claude-sonnet-4-20250514": "Claude Sonnet 4",
        "deepseek-chat": "DeepSeek Chat",
        "deepseek-reasoner": "DeepSeek Reasoner",
        "qwen-plus": "Qwen Plus",
        "qwen-turbo": "Qwen Turbo",
    }
    return [
        ModelOption(
            model_id=m,
            name=display_names.get(m, m),
            description=f"Model: {m}",
        )
        for m in settings.available_models
    ]


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    employee_id: int = Depends(get_employee_id),
):
    dao = ProfileDAO(get_session_factory(), employee_id)
    profile = await dao.get_settings()
    current_model = None
    enabled_tools = []
    if profile and profile.settings:
        s = json.loads(profile.settings)
        current_model = s.get("model")
        enabled_tools = s.get("tools", [])
    return SettingsResponse(
        models=_build_model_options(),
        current_model=current_model,
        enabled_tools=enabled_tools,
        available_tools=AVAILABLE_TOOLS,
    )


@router.put("/settings", response_model=SuccessResponse)
async def update_settings(
    req: UpdateSettingsRequest,
    employee_id: int = Depends(get_employee_id),
):
    dao = ProfileDAO(get_session_factory(), employee_id)
    profile = await dao.get_settings()
    current = json.loads(profile.settings) if profile and profile.settings else {}
    if req.model:
        # Validate model is in available list
        if req.model not in settings.available_models:
            from app.middleware.error_handler import AppError
            raise AppError("BX_SETTINGS_5001", f"Model '{req.model}' not available", 400)
        current["model"] = req.model
    if req.tools:
        current["tools"] = req.tools
    await dao.update_settings(json.dumps(current, ensure_ascii=False))
    return SuccessResponse()