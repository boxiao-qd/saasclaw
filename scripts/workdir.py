#!/usr/bin/env python3
"""General-purpose working directory manager for skills and subagents.

Every skill or subagent that generates files should:
1. Call `create` to get a unique work dir at task start
2. Write ALL intermediate and output files inside that dir
3. Call `upload-result` to upload the final deliverable to MinIO and cleanup
   (or use `upload_artifact.py` + `cleanup` separately for fine-grained control)

Directory layout:
    {project_root}/tmp-doc/{employee_id}_{uuid}/

- Unique per (user, task) — no concurrent conflicts
- Local disk only during the task — deleted after upload
- Final results in MinIO under user-data/{employee_id}/

Usage:
    # Create work dir (prints JSON with work_dir path)
    python3 workdir.py create [--employee-id 42]

    # Upload a file from workdir to MinIO, then cleanup workdir
    python3 workdir.py upload-result /path/to/tmp-doc/42_abc/output.pptx \
        --user-id 42 --source "ppt-master" [--name "Report.pptx"] [--session sess-id]

    # Delete work dir without uploading
    python3 workdir.py cleanup --path /path/to/tmp-doc/42_abc123ef/

    # Delete stale workdirs older than N hours
    python3 workdir.py cleanup-stale [--max-age-hours 24] [--dry-run]

Environment variables used:
    SA_EMPLOYEE_ID            — employee / user ID (fallback when --employee-id not given)
    SA_SESSION_ID             — session ID for DB record
    OBJECT_STORAGE_ENDPOINT   — MinIO endpoint
    OBJECT_STORAGE_ACCESS_KEY
    OBJECT_STORAGE_SECRET_KEY
    OBJECT_STORAGE_BUCKET     — target bucket
    OBJECT_STORAGE_REGION     — (default: us-east-1)
    DB_URL                    — SQLAlchemy DB URL (optional, DB record skipped if not set)
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


# Project root is two levels above this script: {project_root}/scripts/workdir.py
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TMP_DOC_BASE = _PROJECT_ROOT / "tmp-doc"


# ---------------------------------------------------------------------------
# MinIO helpers
# ---------------------------------------------------------------------------

def _s3_client():
    import boto3
    endpoint   = os.environ.get("OBJECT_STORAGE_ENDPOINT", "")
    access_key = os.environ.get("OBJECT_STORAGE_ACCESS_KEY", "")
    secret_key = os.environ.get("OBJECT_STORAGE_SECRET_KEY", "")
    region     = os.environ.get("OBJECT_STORAGE_REGION", "us-east-1")
    kw = dict(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    if endpoint:
        kw["endpoint_url"] = endpoint
    return boto3.client("s3", **kw)


def _bucket() -> str:
    return os.environ.get("OBJECT_STORAGE_BUCKET", "sa-artifacts")


def _ensure_bucket(s3, bucket: str) -> None:
    from botocore.exceptions import ClientError
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            s3.create_bucket(Bucket=bucket)
        else:
            raise


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def cmd_create(args: argparse.Namespace) -> None:
    employee_id = args.employee_id or os.environ.get("SA_EMPLOYEE_ID", "0")
    work_dir = _TMP_DOC_BASE / f"{employee_id}_{uuid.uuid4().hex}"
    work_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"work_dir": str(work_dir)}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def cmd_cleanup(args: argparse.Namespace) -> None:
    work_dir = Path(args.path).resolve()
    tmp_doc = _TMP_DOC_BASE.resolve()

    # Safety: only delete directories that live under tmp-doc/
    try:
        work_dir.relative_to(tmp_doc)
    except ValueError:
        msg = f"Safety check failed: '{work_dir}' is not under '{tmp_doc}'. Not deleted."
        print(json.dumps({"status": "error", "message": msg}), file=sys.stderr)
        sys.exit(1)

    if not work_dir.exists():
        print(json.dumps({"status": "ok", "message": "Already gone", "path": str(work_dir)}))
        return

    shutil.rmtree(work_dir, ignore_errors=True)
    print(json.dumps({"status": "ok", "deleted": str(work_dir)}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# cleanup-stale
# ---------------------------------------------------------------------------

def cmd_cleanup_stale(args: argparse.Namespace) -> None:
    max_age_hours = int(args.max_age_hours) if args.max_age_hours else 24
    dry_run = args.dry_run
    if not _TMP_DOC_BASE.is_dir():
        print(json.dumps({"status": "ok", "deleted": 0, "message": "tmp-doc/ does not exist"}, ensure_ascii=False))
        return

    now = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted = 0
    errors: list[str] = []

    for entry in sorted(_TMP_DOC_BASE.iterdir()):
        if not entry.is_dir():
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        age = now - mtime
        if age < max_age_seconds:
            continue
        if dry_run:
            age_h = age / 3600
            print(f"[dry-run] would delete: {entry} (age: {age_h:.1f}h)")
            deleted += 1
        else:
            try:
                shutil.rmtree(entry)
                age_h = age / 3600
                print(f"[cleanup] deleted: {entry} (age: {age_h:.1f}h)")
                deleted += 1
            except OSError as e:
                errors.append(f"{entry}: {e}")

    result = {"status": "ok", "deleted": deleted, "dry_run": dry_run}
    if errors:
        result["errors"] = errors
    print(json.dumps(result, ensure_ascii=False))


# ---------------------------------------------------------------------------
# upload-result
# ---------------------------------------------------------------------------

def _infer_work_dir(local_path: Path) -> Path | None:
    """Return the work_dir that owns local_path, or None if not under tmp-doc/."""
    try:
        tmp_doc = _TMP_DOC_BASE.resolve()
        resolved = local_path.resolve()
        resolved.relative_to(tmp_doc)
        work_dir_name = resolved.relative_to(tmp_doc).parts[0]
        return tmp_doc / work_dir_name
    except (ValueError, IndexError):
        return None


def cmd_upload_result(args: argparse.Namespace) -> None:
    """Upload a file from the working directory to MinIO, record in DB, and cleanup."""
    local_path = Path(args.local_path)

    # Infer work_dir from the file path — cleanup must run regardless of outcome
    work_dir = _infer_work_dir(local_path)

    def _cleanup() -> None:
        if work_dir and work_dir.is_dir():
            shutil.rmtree(work_dir, ignore_errors=True)

    if not local_path.is_file():
        _cleanup()
        print(json.dumps({"status": "error", "message": f"File not found: {args.local_path}"}))
        sys.exit(1)

    try:
        user_id = args.user_id or os.environ.get("SA_EMPLOYEE_ID", "0")
        session_id = args.session or os.environ.get("SA_SESSION_ID", "")
        source_name = args.source or "skill"
        file_name = args.name or local_path.name
        artifact_id = str(uuid.uuid4())
        minio_key = f"user-data/{user_id}/{artifact_id}_{local_path.name}"

        content_type, _ = mimetypes.guess_type(local_path.name)
        content_type = content_type or "application/octet-stream"

        s3 = _s3_client()
        bucket = _bucket()
        _ensure_bucket(s3, bucket)

        file_size = local_path.stat().st_size
        with open(local_path, "rb") as f:
            s3.put_object(Bucket=bucket, Key=minio_key, Body=f.read(), ContentType=content_type)

        # Record in DB (best-effort)
        db_url = os.environ.get("DB_URL", "")
        if db_url:
            try:
                sync_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "").replace("+aiomysql", "+pymysql")
                from sqlalchemy import create_engine, text
                engine = create_engine(sync_url)
                now = datetime.now(tz=timezone.utc).isoformat()
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO artifact_files "
                            "(id, employee_id, session_id, file_name, minio_key, file_size, "
                            " source_type, source_name, created_at, updated_at) "
                            "VALUES (:id, :eid, :sid, :fname, :mkey, :fsize, 'skill', :sname, :now, :now)"
                        ),
                        dict(id=artifact_id, eid=int(user_id), sid=session_id or None,
                             fname=file_name, mkey=minio_key, fsize=file_size, sname=source_name, now=now),
                    )
            except Exception as e:
                sys.stderr.write(f"[warn] DB record skipped: {e}\n")

        print(json.dumps({
            "status": "ok",
            "artifact_id": artifact_id,
            "file_name": file_name,
            "minio_key": minio_key,
            "message": f"✓ 文件「{file_name}」已上传到文件存储，可在「我的文件」中查看和下载。",
        }, ensure_ascii=False))

    finally:
        _cleanup()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Working directory manager for skills/subagents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create unique work dir under tmp-doc/")
    p_create.add_argument("--employee-id", default=None,
                          help="Employee ID (default: $SA_EMPLOYEE_ID)")

    p_cleanup = sub.add_parser("cleanup", help="Delete work dir (safety-checked)")
    p_cleanup.add_argument("--path", required=True,
                           help="Path returned by 'create'")

    p_cleanup_stale = sub.add_parser("cleanup-stale", help="Delete stale workdirs older than N hours")
    p_cleanup_stale.add_argument("--max-age-hours", default=None, help="Max age in hours (default: 24)")
    p_cleanup_stale.add_argument("--dry-run", action="store_true", help="List without deleting")

    p_upload = sub.add_parser("upload-result", help="Upload file to MinIO and cleanup workdir")
    p_upload.add_argument("local_path", help="Local file path to upload (must be under tmp-doc/)")
    p_upload.add_argument("--user-id", default=None, help="Employee ID (default: $SA_EMPLOYEE_ID)")
    p_upload.add_argument("--name", default=None, help="Display filename (default: original name)")
    p_upload.add_argument("--source", default="skill", help="Skill/subagent name that generated this file")
    p_upload.add_argument("--session", default=None, help="Session ID (default: $SA_SESSION_ID)")

    args = parser.parse_args()

    dispatch = {
        "create":         cmd_create,
        "cleanup":        cmd_cleanup,
        "cleanup-stale":  cmd_cleanup_stale,
        "upload-result":  cmd_upload_result,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()