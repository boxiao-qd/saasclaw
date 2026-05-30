#!/usr/bin/env python3
"""Upload a result file to MinIO user-data/ and clean up the work directory.

Single atomic command — does upload + work-dir cleanup together so callers
don't need to chain two separate commands.

Usage:
    python3 save_result.py \\
        --file   /path/to/tmp-doc/42_abc/report.md \\
        --work-dir /path/to/tmp-doc/42_abc \\
        [--name  "My Report.md"] \\
        [--source "skill-name"]

Environment variables (injected by agent framework):
    SA_EMPLOYEE_ID              Employee / user ID
    OBJECT_STORAGE_ENDPOINT     MinIO endpoint
    OBJECT_STORAGE_ACCESS_KEY
    OBJECT_STORAGE_SECRET_KEY
    OBJECT_STORAGE_BUCKET
    DB_URL                      (optional) record upload in artifact_files table

Output (stdout JSON):
    Success: {"status": "ok", "file_name": "...", "minio_key": "...", "message": "..."}
    Error:   {"status": "error", "message": "..."}
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _s3_client():
    import boto3
    kw = dict(
        aws_access_key_id=os.environ.get("OBJECT_STORAGE_ACCESS_KEY", ""),
        aws_secret_access_key=os.environ.get("OBJECT_STORAGE_SECRET_KEY", ""),
        region_name=os.environ.get("OBJECT_STORAGE_REGION", "us-east-1"),
    )
    endpoint = os.environ.get("OBJECT_STORAGE_ENDPOINT", "")
    if endpoint:
        kw["endpoint_url"] = endpoint
    return boto3.client("s3", **kw)


def _ensure_bucket(s3, bucket: str) -> None:
    from botocore.exceptions import ClientError
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            s3.create_bucket(Bucket=bucket)
        else:
            raise


def _record_db(artifact_id: str, employee_id: int, file_name: str,
               minio_key: str, file_size: int, source: str) -> None:
    db_url = os.environ.get("DB_URL", "")
    if not db_url:
        return
    sync_url = (db_url
                .replace("+aiosqlite", "")
                .replace("+asyncpg", "")
                .replace("+aiomysql", "+pymysql"))
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(sync_url)
        now = datetime.now(tz=timezone.utc).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO artifact_files "
                    "(id, employee_id, session_id, file_name, minio_key, file_size, "
                    "source_type, source_name, created_at, updated_at) "
                    "VALUES (:id,:eid,NULL,:fname,:mkey,:fsize,'skill',:src,:now,:now)"
                ),
                dict(id=artifact_id, eid=employee_id, fname=file_name,
                     mkey=minio_key, fsize=file_size, src=source, now=now),
            )
    except Exception as e:
        sys.stderr.write(f"[warn] DB record skipped: {e}\n")


def _cleanup_work_dir(work_dir: Path) -> None:
    """Delete work_dir with a safety check — must be under tmp-doc/."""
    project_root_env = os.environ.get("SA_PROJECT_ROOT")
    if project_root_env:
        tmp_doc = Path(project_root_env).resolve() / "tmp-doc"
    else:
        tmp_doc = Path(__file__).resolve().parents[4] / "tmp-doc"

    try:
        work_dir.relative_to(tmp_doc.resolve())
    except ValueError:
        sys.stderr.write(f"[warn] work-dir '{work_dir}' is not under tmp-doc/ — skipped cleanup\n")
        return

    if not work_dir.is_dir():
        return

    shutil.rmtree(work_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload result file to MinIO and clean up work dir")
    parser.add_argument("--file",     required=True, help="Absolute path of the file to upload")
    parser.add_argument("--work-dir", required=True, dest="work_dir",
                        help="Work directory to delete after successful upload")
    parser.add_argument("--name",     default="",    help="Display filename (default: original name)")
    parser.add_argument("--source",   default="skill", help="Skill or subagent name")
    args = parser.parse_args()

    local_path = Path(args.file).resolve()
    work_dir = Path(args.work_dir).resolve()

    employee_id = int(os.environ.get("SA_EMPLOYEE_ID", "0"))
    file_name   = args.name or local_path.name
    artifact_id = str(uuid.uuid4())
    minio_key   = f"user-data/{employee_id}/{artifact_id}_{local_path.name}"
    content_type, _ = mimetypes.guess_type(local_path.name)
    content_type = content_type or "text/plain"

    bucket = os.environ.get("OBJECT_STORAGE_BUCKET", "sa-artifacts")

    # Guard: file must exist and be non-empty. Clean up work dir before failing
    # — a missing/empty file means the task didn't complete, but the work
    # directory must not be left as an orphan.
    if not local_path.is_file():
        _cleanup_work_dir(work_dir)
        _fail(f"File not found: {args.file}")

    if local_path.stat().st_size == 0:
        _cleanup_work_dir(work_dir)
        _fail(f"File is empty: {args.file} — write the report content before uploading.")

    # Upload
    try:
        s3 = _s3_client()
        _ensure_bucket(s3, bucket)
        file_size = local_path.stat().st_size
        s3.put_object(Bucket=bucket, Key=minio_key,
                      Body=local_path.read_bytes(), ContentType=content_type)
    except Exception as e:
        # Upload failed — keep work dir for retry
        _fail(f"MinIO upload failed: {e}")
        return  # unreachable, but satisfies type checker

    # Record in DB (best-effort)
    _record_db(artifact_id, employee_id, file_name, minio_key, file_size, args.source)

    # Clean up work directory on success
    _cleanup_work_dir(work_dir)

    print(json.dumps({
        "status":    "ok",
        "file_name": file_name,
        "minio_key": minio_key,
        "message":   f"✓ 文件「{file_name}」已上传到文件存储，可在「我的文件」中查看和下载。",
    }, ensure_ascii=False))


def _fail(msg: str) -> None:
    print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
    sys.exit(1)


if __name__ == "__main__":
    main()
