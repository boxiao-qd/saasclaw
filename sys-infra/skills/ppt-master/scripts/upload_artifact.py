#!/usr/bin/env python3
"""upload_artifact — upload a file to MinIO artifact storage.

Usage:
    python upload_artifact.py <local_path> --user-id <employee_id> [options]

Options:
    --user-id INT      User ID (required)
    --name TEXT        Display filename shown to user (default: original filename)
    --source TEXT      Skill/subagent name that generated this file (default: "skill")
    --session TEXT     Session ID to associate this file with (optional)

Examples:
    # Basic upload
    python upload_artifact.py report.pptx --user-id 42

    # With display name and source
    python upload_artifact.py /tmp/output.docx --user-id 42 --name "Q2 Report.docx" --source "report-writer"

    # From within a skill running in code_execute (env vars already set)
    python upload_artifact.py report.pptx --user-id $SA_EMPLOYEE_ID --source "ppt-master"

Required environment variables:
    OBJECT_STORAGE_ENDPOINT    MinIO endpoint, e.g. http://minio:9000
    OBJECT_STORAGE_ACCESS_KEY
    OBJECT_STORAGE_SECRET_KEY
    ARTIFACT_STORAGE_BUCKET    Target bucket (default: sa-artifacts)

Optional environment variables:
    OBJECT_STORAGE_REGION      (default: us-east-1)
    DB_URL                     SQLAlchemy DB URL to record the upload (skipped if not set)

Output (JSON to stdout):
    Success: {"status": "ok", "artifact_id": "...", "file_name": "...", "minio_key": "...", "message": "..."}
    Error:   {"status": "error", "message": "..."}
"""

import argparse
import json
import mimetypes
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# MinIO upload
# ---------------------------------------------------------------------------

def _upload(local_path: Path, minio_key: str, content_type: str) -> int:
    """Upload file to MinIO; return file size in bytes."""
    import boto3
    from botocore.exceptions import ClientError

    endpoint   = os.environ.get("OBJECT_STORAGE_ENDPOINT", "")
    access_key = os.environ.get("OBJECT_STORAGE_ACCESS_KEY", "")
    secret_key = os.environ.get("OBJECT_STORAGE_SECRET_KEY", "")
    region     = os.environ.get("OBJECT_STORAGE_REGION", "us-east-1")
    bucket     = os.environ.get("OBJECT_STORAGE_BUCKET", "sa-artifacts")

    client_kw = dict(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    if endpoint:
        client_kw["endpoint_url"] = endpoint

    s3 = boto3.client("s3", **client_kw)

    # ensure bucket exists
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            s3.create_bucket(Bucket=bucket)
        else:
            raise

    file_size = local_path.stat().st_size
    with open(local_path, "rb") as f:
        s3.put_object(Bucket=bucket, Key=minio_key, Body=f, ContentType=content_type)

    return file_size


# ---------------------------------------------------------------------------
# DB record (optional — skipped when DB_URL is not set)
# ---------------------------------------------------------------------------

def _record(artifact_id: str, employee_id: int, session_id: str,
            file_name: str, minio_key: str, file_size: int, source_name: str) -> None:
    db_url = os.environ.get("DB_URL", "")
    if not db_url:
        return  # DB recording is optional

    # strip async driver prefix so sync SQLAlchemy can use the URL
    sync_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "").replace("+aiomysql", "+pymysql")

    from sqlalchemy import create_engine, text
    engine = create_engine(sync_url)
    now = datetime.utcnow().isoformat()

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO artifact_files "
                "(id, employee_id, session_id, file_name, minio_key, file_size, "
                " source_type, source_name, created_at, updated_at) "
                "VALUES (:id, :eid, :sid, :fname, :mkey, :fsize, 'skill', :sname, :now, :now)"
            ),
            dict(id=artifact_id, eid=employee_id, sid=session_id or None,
                 fname=file_name, mkey=minio_key, fsize=file_size, sname=source_name, now=now),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload a generated file to MinIO artifact storage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("local_path", help="Path to the file to upload")
    parser.add_argument("--user-id",  required=True, type=int, dest="user_id",
                        help="Employee / user ID")
    parser.add_argument("--name",     default="",    help="Display filename (default: original name)")
    parser.add_argument("--source",   default="skill", help="Skill or subagent name")
    parser.add_argument("--session",  default="",    help="Session ID to link this file to")
    args = parser.parse_args()

    local_path = Path(args.local_path).resolve()
    if not local_path.is_file():
        _fail(f"File not found: {args.local_path}")

    file_name    = args.name or local_path.name
    artifact_id  = str(uuid.uuid4())
    minio_key    = f"user-data/{args.user_id}/{artifact_id}_{local_path.name}"
    content_type, _ = mimetypes.guess_type(local_path.name)
    content_type = content_type or "application/octet-stream"

    # upload
    try:
        file_size = _upload(local_path, minio_key, content_type)
    except Exception as e:
        _fail(f"MinIO upload failed: {e}")

    # record in DB (best-effort)
    try:
        _record(artifact_id, args.user_id, args.session,
                file_name, minio_key, file_size, args.source)
    except Exception as e:
        # Don't fail the whole operation just because DB is unavailable
        sys.stderr.write(f"[warn] DB record skipped: {e}\n")

    # clean up local file after successful upload
    try:
        local_path.unlink()
    except Exception:
        pass

    print(json.dumps({
        "status":      "ok",
        "artifact_id": artifact_id,
        "file_name":   file_name,
        "minio_key":   minio_key,
        "file_size":   file_size,
        "message":     f"✓ 文件「{file_name}」已上传到文件存储，可在「我的文件」中查看和下载。",
    }, ensure_ascii=False))


def _fail(msg: str) -> None:
    print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False))
    sys.exit(1)


if __name__ == "__main__":
    main()
