"""Tool: update_user_profile — update display_name or profile_data preferences."""

import json
import logging
import re

log = logging.getLogger(__name__)

# Allowed chars: Unicode letters/digits, CJK, common punctuation, space, dash, dot, apostrophe
_DISPLAY_NAME_RE = re.compile(r"^[\w一-鿿　-〿\s\-·.']{1,64}$")
_PREF_MAX_KEYS = 20
_PREF_MAX_KEY_LEN = 64
_PREF_MAX_VAL_LEN = 200
_PREF_MAX_BYTES = 4096

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "update_user_profile",
        "description": (
            "更新当前用户的身份信息或偏好设置。"
            "当用户主动告知姓名、偏好、习惯、语言风格等个人信息时调用。"
            "field='display_name' 更新姓名；field='preference' + value 更新偏好字段（JSON {key: value}）。"
            "只在用户主动要求时才调用，不要自动猜测并更新。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": ["display_name", "preference"],
                    "description": "要更新的字段类型",
                },
                "value": {
                    "type": "string",
                    "description": "display_name 时为新名字字符串；preference 时为 JSON 对象字符串，如 {\"language\": \"中文\"}",
                },
            },
            "required": ["field", "value"],
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    from sqlalchemy import update as sa_update
    from app.db.database import get_session_factory
    from app.dao.profile_dao import ProfileDAO
    from app.models.models import UserProfile

    try:
        args = json.loads(args_str)
    except Exception:
        return json.dumps({"error": "Invalid JSON arguments"}, ensure_ascii=False)

    field = args.get("field", "")
    value = args.get("value", "")

    if not field or value is None:
        return json.dumps({"error": "field and value are required"}, ensure_ascii=False)

    sf = get_session_factory()
    dao = ProfileDAO(sf, employee_id)

    try:
        from app.models.models import UserProfile
        profile = await dao.get_settings()
        if not profile:
            # Auto-create profile row on first use
            async with sf() as session:
                session.add(UserProfile(employee_id=employee_id))
                await session.commit()
            profile = await dao.get_settings()

        if field == "display_name":
            name = str(value).strip()
            if not _DISPLAY_NAME_RE.match(name):
                return json.dumps(
                    {"error": "display_name contains invalid characters or exceeds 64 chars"},
                    ensure_ascii=False,
                )
            async with sf() as session:
                await session.execute(
                    sa_update(UserProfile)
                    .where(UserProfile.employee_id == employee_id)
                    .values(display_name=name)
                )
                await session.commit()
            return json.dumps(
                {"success": True, "field": "display_name", "value": name},
                ensure_ascii=False,
            )

        elif field == "preference":
            try:
                new_pref = json.loads(value)
                if not isinstance(new_pref, dict):
                    return json.dumps(
                        {"error": "preference value must be a JSON object"},
                        ensure_ascii=False,
                    )
            except Exception:
                return json.dumps(
                    {"error": "preference value must be valid JSON, e.g. {\"key\": \"value\"}"},
                    ensure_ascii=False,
                )

            # Validate keys and values
            for k, v in new_pref.items():
                if len(str(k)) > _PREF_MAX_KEY_LEN:
                    return json.dumps(
                        {"error": f"preference key '{str(k)[:20]}...' exceeds {_PREF_MAX_KEY_LEN} chars"},
                        ensure_ascii=False,
                    )
                if len(str(v)) > _PREF_MAX_VAL_LEN:
                    return json.dumps(
                        {"error": f"preference value for key '{str(k)[:20]}' exceeds {_PREF_MAX_VAL_LEN} chars"},
                        ensure_ascii=False,
                    )

            existing: dict = {}
            if profile.profile_data:
                try:
                    parsed = json.loads(profile.profile_data)
                    if isinstance(parsed, dict):
                        existing = parsed
                except Exception:
                    pass

            # Enforce key count limit across merged result
            merged = {**existing, **new_pref}
            if len(merged) > _PREF_MAX_KEYS:
                return json.dumps(
                    {"error": f"preference exceeds maximum of {_PREF_MAX_KEYS} keys"},
                    ensure_ascii=False,
                )

            merged_json = json.dumps(merged, ensure_ascii=False)
            if len(merged_json.encode()) > _PREF_MAX_BYTES:
                return json.dumps(
                    {"error": f"preference data exceeds {_PREF_MAX_BYTES} bytes"},
                    ensure_ascii=False,
                )

            async with sf() as session:
                await session.execute(
                    sa_update(UserProfile)
                    .where(UserProfile.employee_id == employee_id)
                    .values(profile_data=merged_json)
                )
                await session.commit()

            return json.dumps(
                {"success": True, "field": "preference", "updated_keys": list(new_pref.keys())},
                ensure_ascii=False,
            )

        else:
            return json.dumps({"error": "Unknown field"}, ensure_ascii=False)

    except Exception as e:
        log.error("update_user_profile failed: %s", e)
        return json.dumps({"error": "internal_error"}, ensure_ascii=False)
