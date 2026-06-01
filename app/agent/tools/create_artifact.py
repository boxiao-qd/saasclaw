"""create_artifact tool — save generated content as a persistent file artifact in MinIO.

Used by agents during cron job execution to create deliverable files (PPT, MD, PDF, etc.)
that should be persisted and made available for download by the user.
"""

import json
import mimetypes
import re
import uuid
from datetime import datetime

from app.config import settings

_MAX_FILENAME_LENGTH = 200


def _sanitize_filename(name: str) -> str:
    """Strip path separators and control characters from user-supplied filename."""
    name = name.replace("\\", "/")
    name = name.split("/")[-1]  # keep only basename
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)  # strip control chars
    name = name.strip(". ")  # strip leading/trailing dots and spaces
    if not name:
        name = "artifact.bin"
    if len(name) > _MAX_FILENAME_LENGTH:
        base, _, ext = name.rpartition(".")
        name = base[:_MAX_FILENAME_LENGTH - len(ext) - 1] + "." + ext
    return name


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "create_artifact",
        "description": (
            "Create a persistent file artifact from generated content. "
            "Use this tool when the user (or cron task) needs a deliverable file "
            "such as a report, presentation, spreadsheet, or document. "
            "The content will be stored permanently and a download link will be "
            "included in the notification. "
            "Supported formats: .md, .pptx, .pdf, .xlsx, .docx, .csv, .json, .txt, .html, .png, .jpg, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "File name with extension (e.g. 'report.md', 'slides.pptx', 'data.csv')",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write into the file",
                },
            },
            "required": ["filename", "content"],
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    """Fallback executor — returns an error directing to the session-aware path."""
    return json.dumps({
        "error": "create_artifact requires session context — use execute_with_session",
        "tool_name": "create_artifact",
    }, ensure_ascii=False)


async def execute_with_session(args_str: str, employee_id: int, session_id: str) -> str:
    """Create a persistent file artifact: upload to MinIO + create DB record."""
    args = json.loads(args_str)
    filename = _sanitize_filename(args.get("filename", "artifact.bin"))
    content = args.get("content", "")

    content_bytes = content.encode("utf-8")
    file_size = len(content_bytes)

    artifact_id = str(uuid.uuid4())
    minio_key = f"user-data/{employee_id}/{artifact_id}_{filename}"
    content_type, _ = mimetypes.guess_type(filename)
    content_type = content_type or "application/octet-stream"

    # ── Upload to object storage ──────────────────────────────────────────
    backend = settings.object_storage_backend
    if backend in ("s3", "minio"):
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.object_storage_access_key,
                aws_secret_access_key=settings.object_storage_secret_key,
                region_name=settings.object_storage_region or "us-east-1",
                endpoint_url=settings.object_storage_endpoint or None,
            )
            bucket = settings.object_storage_bucket
            s3.put_object(Bucket=bucket, Key=minio_key, Body=content_bytes, ContentType=content_type)
        except Exception as e:
            return json.dumps({
                "error": f"MinIO upload failed: {e}",
                "tool_name": "create_artifact",
            }, ensure_ascii=False)
    else:
        # Local file storage fallback
        from pathlib import Path
        base_dir = Path(settings.saas_user_config_dir)
        local_path = base_dir / minio_key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content_bytes)
        import logging
        logging.getLogger(__name__).info("create_artifact local: %s (%d bytes)", local_path, file_size)

    # ── Create DB record ──────────────────────────────────────────────────
    try:
        from app.db.database import get_session_factory
        sf = get_session_factory()
        now = datetime.utcnow().isoformat()
        async with sf() as session:
            from sqlalchemy import text
            await session.execute(
                text(
                    "INSERT INTO artifact_files "
                    "(id, employee_id, session_id, file_name, minio_key, file_size, "
                    " source_type, source_name, created_at, updated_at) "
                    "VALUES (:id, :eid, :sid, :fname, :mkey, :fsize, :stype, :sname, :now, :now)"
                ),
                {
                    "id": artifact_id,
                    "eid": employee_id,
                    "sid": session_id,
                    "fname": filename,
                    "mkey": minio_key,
                    "fsize": file_size,
                    "stype": "cron_job",
                    "sname": "create_artifact",
                    "now": now,
                },
            )
            await session.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("DB record failed for artifact %s: %s", artifact_id, e)
        return json.dumps({
            "error": f"Database record failed: {e}",
            "tool_name": "create_artifact",
            "minio_key": minio_key,
        }, ensure_ascii=False)

    return json.dumps({
        "status": "created",
        "file_id": artifact_id,
        "file_name": filename,
        "file_size": file_size,
        "download_url": f"/bx/api/v1/files/{artifact_id}/download",
    }, ensure_ascii=False)
