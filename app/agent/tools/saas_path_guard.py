"""SaaS path whitelist validator — restrict file operations to system-config/ and user-config/."""

import os
from pathlib import Path

from app.config import settings


def _is_under_dir(real_path: str, dir_path: str) -> bool:
    """Check if real_path is exactly dir_path or a subdirectory/file under dir_path.
    Uses path separator boundary to prevent prefix collision (e.g. /data/uc matching /data/uc-data)."""
    if real_path == dir_path:
        return True
    if real_path.startswith(dir_path + os.sep):
        return True
    return False


def _saas_read_allowed(path: str) -> bool:
    """In SaaS mode, only allow reads from system-config/ and user-config/."""
    if not settings.saas_mode:
        return True
    real = os.path.realpath(path)
    system_dir = os.path.realpath(settings.saas_system_config_dir)
    user_dir = os.path.realpath(settings.saas_user_config_dir)
    return _is_under_dir(real, system_dir) or _is_under_dir(real, user_dir)


def _saas_write_allowed(path: str) -> bool:
    """In SaaS mode, only allow writes to user-config/."""
    if not settings.saas_mode:
        return True
    real = os.path.realpath(path)
    user_dir = os.path.realpath(settings.saas_user_config_dir)
    return _is_under_dir(real, user_dir)


def _saas_search_allowed(path: str) -> bool:
    """In SaaS mode, only allow searches within system-config/ and user-config/."""
    if not settings.saas_mode:
        return True
    real = os.path.realpath(path) if path else os.path.realpath(os.getcwd())
    system_dir = os.path.realpath(settings.saas_system_config_dir)
    user_dir = os.path.realpath(settings.saas_user_config_dir)
    return _is_under_dir(real, system_dir) or _is_under_dir(real, user_dir)


SAAS_READ_DENIED_MSG = (
    "SaaS mode: path not in allowed read whitelist. "
    "Only system-config/ (pre-built skills/hooks/tools, read-only) "
    "and user-config/ (user skills/subagents, read-write) are accessible."
)

SAAS_WRITE_DENIED_MSG = (
    "SaaS mode: path not in allowed write whitelist. "
    "Only user-config/ (user skills/subagents) is writable."
)

SAAS_SEARCH_DENIED_MSG = (
    "SaaS mode: search path not in allowed whitelist. "
    "Only system-config/ and user-config/ directories are searchable."
)