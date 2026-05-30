"""Generate system-config/ directory by copying pre-built skills/hooks/tools/subagents/plugins."""

import os
import shutil
from pathlib import Path

from app.config import settings


def generate_system_config():
    """Copy pre-built directories to system-config/ for SaaS runtime."""
    project_root = Path(settings.saas_system_config_dir).parent
    system_dir = Path(settings.saas_system_config_dir)

    # Clean and recreate
    if system_dir.exists():
        shutil.rmtree(system_dir)
    system_dir.mkdir(parents=True, exist_ok=True)

    # Pre-built source directories to copy
    source_dirs = [
        "app/agent/skills",
        "app/agent/hooks",
        "app/agent/tools",
        "app/agent/subagents",
        "app/agent/plugins",
    ]

    for src in source_dirs:
        src_path = project_root / src
        if not src_path.exists():
            continue
        dest_name = Path(src).name  # e.g. "skills", "hooks", "tools"
        dest_path = system_dir / dest_name
        shutil.copytree(src_path, dest_path)

    print(f"system-config/ generated at {system_dir}")


if __name__ == "__main__":
    generate_system_config()