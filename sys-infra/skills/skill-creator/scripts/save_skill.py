#!/usr/bin/env python3
"""Save a skill to MySQL (and optionally MinIO).

Two modes:

  # SKILL.md-only — read content from stdin, no disk write needed
  python3 save_skill.py - [--name DISPLAY_NAME]
  echo "---\nname: foo\n..." | python3 save_skill.py -

  # Full directory — read from workdir, upload extra files (scripts/ etc.) to MinIO
  python3 save_skill.py <workdir_path> [--name DISPLAY_NAME]

In both modes:
  - content_md, frontmatter, header_description → always written to MySQL
  - scripts / references / assets → uploaded to MinIO only when present (directory mode)
  - SKILL.md itself is NEVER uploaded to MinIO (content already in MySQL)

Required environment variables:
    SA_EMPLOYEE_ID
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


async def _save_skill(
    skill_md_content: str,
    workdir: Path | None,
    display_name: str | None = None,
) -> dict:
    import hashlib
    import mimetypes
    import yaml

    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

    from app.dao.skill_dao import SkillDAO
    from app.storage.object_storage import create_object_storage
    from app.db.database import init_db, get_session_factory
    from app.middleware.error_handler import AppError

    await init_db()

    # Parse frontmatter
    frontmatter_text: str | None = None
    frontmatter_parsed: dict | None = None
    stripped = skill_md_content.strip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) >= 3:
            raw_text = parts[1].strip()
            if raw_text:
                frontmatter_text = raw_text
            try:
                fm = yaml.safe_load(parts[1])
                frontmatter_parsed = fm if isinstance(fm, dict) else None
            except yaml.YAMLError as e:
                print(f"[DEBUG] YAML parse error: {e}", file=sys.stderr)

    fallback_name = workdir.name if workdir else "unnamed-skill"
    skill_name = (
        display_name
        or (frontmatter_parsed.get("name") if frontmatter_parsed else None)
        or fallback_name
    )

    employee_id = int(os.environ.get("SA_EMPLOYEE_ID", "0"))
    dao = SkillDAO(get_session_factory(), employee_id)

    try:
        skill = await dao.create(
            name=skill_name,
            content_md=skill_md_content,
            frontmatter=frontmatter_text,
        )
    except AppError as e:
        return {"status": "conflict", "error_code": e.error_code,
                "message": e.message, "conflict_name": skill_name}

    # header_description = description field from frontmatter
    header = ""
    if frontmatter_parsed:
        desc = frontmatter_parsed.get("description")
        if isinstance(desc, str):
            header = " ".join(desc.split())[:500]
    if header:
        await dao.update(skill.id, header_description=header)

    # Extra files (scripts/, references/, assets/) — only in directory mode
    object_key_prefix = None
    file_count = 0
    content_hash = hashlib.md5(skill_md_content.encode()).hexdigest()

    if workdir is not None:
        extra_files = [
            (fpath, fpath.relative_to(workdir).as_posix())
            for fpath in workdir.rglob("*")
            if fpath.is_file() and fpath.relative_to(workdir).as_posix() != "SKILL.md"
        ]
        if extra_files:
            object_key_prefix = f"user-skill/{skill.id}"
            storage = create_object_storage()
            for fpath, rel_path in extra_files:
                data = fpath.read_bytes()
                content_type, _ = mimetypes.guess_type(fpath.name)
                content_type = content_type or "application/octet-stream"
                await storage.put(employee_id, f"{object_key_prefix}/{rel_path}",
                                   data, content_type=content_type)
                file_count += 1

    await dao.update_object_key(skill.id, object_key_prefix, content_hash,
                                header_description=header)

    msg = (
        f"Skill '{skill_name}' saved, {file_count} extra files uploaded to MinIO"
        if file_count else
        f"Skill '{skill_name}' saved (content in MySQL, no MinIO upload)"
    )
    return {
        "status": "ok",
        "id": skill.id,
        "name": skill_name,
        "object_key": object_key_prefix,
        "file_count": file_count,
        "message": msg,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Save a skill to MySQL + MinIO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "source",
        help="Path to skill workdir (directory with SKILL.md + optional subdirs), "
             "or '-' to read SKILL.md content from stdin",
    )
    parser.add_argument("--name", default=None,
                        help="Override skill name (default: from frontmatter)")
    args = parser.parse_args()

    # --- stdin mode ---
    if args.source == "-":
        skill_md_content = sys.stdin.read()
        if not skill_md_content.strip():
            print(json.dumps({"status": "error", "message": "Empty content on stdin"}))
            sys.exit(1)
        result = asyncio.run(_save_skill(skill_md_content, workdir=None,
                                         display_name=args.name))
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if result.get("status") == "ok" else 1)

    # --- directory mode ---
    workdir = Path(args.source).resolve()
    if not workdir.is_dir():
        print(json.dumps({"status": "error",
                          "message": f"Directory not found: {args.source}"}))
        sys.exit(1)

    skill_md_path = workdir / "SKILL.md"
    if not skill_md_path.exists():
        print(json.dumps({"status": "error",
                          "message": "SKILL.md not found in workdir"}))
        sys.exit(1)

    skill_md_content = skill_md_path.read_text(encoding="utf-8")
    result = asyncio.run(_save_skill(skill_md_content, workdir=workdir,
                                     display_name=args.name))
    print(json.dumps(result, ensure_ascii=False))

    # Auto-cleanup workdir after successful save (only if under tmp-doc/)
    if result.get("status") == "ok":
        import shutil
        try:
            project_root = Path(__file__).resolve().parents[4]
            tmp_doc = (project_root / "tmp-doc").resolve()
            if str(workdir).startswith(str(tmp_doc) + "/"):
                shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass

    sys.exit(0 if result.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
