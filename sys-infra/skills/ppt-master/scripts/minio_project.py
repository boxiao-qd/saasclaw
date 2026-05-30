#!/usr/bin/env python3
"""MinIO-backed project lifecycle manager for ppt-master.

Every file in a ppt-master project lives in MinIO under a prefix:
    user-data/{employee_id}/ppt-projects/{project_dir_name}/

This script is the only entry point for interacting with project files.
During `run`, files are staged in /dev/shm (Linux RAM-backed tmpfs — never touches disk).
On macOS/dev environments, falls back to /tmp. Scratchpad is deleted immediately after the command exits.

Commands
--------
init <name> [--format FORMAT] [--user-id INT]
    Create a new project in MinIO. Outputs JSON:
        {"prefix": "user-data/42/ppt-projects/myslides_ppt169_20250528/", "project_name": "myslides_ppt169_20250528"}
    The caller should capture `prefix` and export it as PROJECT_PREFIX.

run --prefix PREFIX [--read-only] -- <cmd...>
    1. Sync MinIO prefix → /tmp/{uuid}/
    2. Run <cmd>, replacing {PROJECT_DIR} with the temp dir path
    3. Unless --read-only: sync /tmp/{uuid}/ → MinIO prefix (upload new/modified files)
    4. Delete /tmp/{uuid}/
    Exit code mirrors the wrapped command.

write-file --prefix PREFIX <rel_path> [--content TEXT | --file PATH | stdin]
    Upload one file into the MinIO project at prefix/<rel_path>.
    For large SVG files use heredoc / stdin (avoids shell-escaping issues).

read-file --prefix PREFIX <rel_path>
    Print prefix/<rel_path> content to stdout (UTF-8).

list --prefix PREFIX
    Print a line-separated list of relative paths in the project.

import-source --prefix PREFIX <local_path> [--name DEST_NAME]
    Upload a local source file into sources/ within the project, then delete the local copy.

Usage examples
--------------
# Create project
PROJECT_PREFIX=$(python3 minio_project.py init "my-deck" --format ppt169 | python3 -c "import sys,json; print(json.load(sys.stdin)['prefix'])")

# Write spec_lock.md into the project
python3 minio_project.py write-file --prefix "$PROJECT_PREFIX" spec_lock.md --content "..."

# Write SVG via heredoc (recommended for large content)
cat << 'SVG_EOF' | python3 minio_project.py write-file --prefix "$PROJECT_PREFIX" svg_output/slide_01.svg
<svg ...>...</svg>
SVG_EOF

# Read a file
python3 minio_project.py read-file --prefix "$PROJECT_PREFIX" spec_lock.md

# Run a processing script (sync MinIO ↔ /tmp, run, sync back, clean up)
python3 minio_project.py run --prefix "$PROJECT_PREFIX" -- python3 finalize_svg.py {PROJECT_DIR}

# Run a read-only script (no sync back)
python3 minio_project.py run --prefix "$PROJECT_PREFIX" --read-only -- python3 svg_quality_checker.py {PROJECT_DIR}

# List project files
python3 minio_project.py list --prefix "$PROJECT_PREFIX"

Required env vars: OBJECT_STORAGE_ENDPOINT, OBJECT_STORAGE_ACCESS_KEY, OBJECT_STORAGE_SECRET_KEY
Optional env vars: OBJECT_STORAGE_REGION (default: us-east-1), OBJECT_STORAGE_BUCKET (default: sa-artifacts)
                   SA_EMPLOYEE_ID (used by `init` when --user-id is not given)
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def _s3_client():
    import boto3
    endpoint   = os.environ.get("OBJECT_STORAGE_ENDPOINT", "")
    access_key = os.environ.get("OBJECT_STORAGE_ACCESS_KEY", "")
    secret_key = os.environ.get("OBJECT_STORAGE_SECRET_KEY", "")
    region     = os.environ.get("OBJECT_STORAGE_REGION", "us-east-1")
    kw: dict = dict(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    if endpoint:
        kw["endpoint_url"] = endpoint
    return boto3.client("s3", **kw)


def _bucket() -> str:
    return os.environ.get("OBJECT_STORAGE_BUCKET", "sa-artifacts")


def _verify_connection(s3, bucket: str) -> None:
    """Verify MinIO is reachable and credentials are valid. Exits with a user-facing error if not."""
    from botocore.exceptions import ClientError, EndpointResolutionError, NoCredentialsError
    endpoint = os.environ.get("OBJECT_STORAGE_ENDPOINT", "(not set)")
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            return  # bucket doesn't exist yet, _ensure_bucket will create it
        msg = (
            f"MinIO 连接失败（endpoint: {endpoint}, bucket: {bucket}）: {e}\n"
            "请检查 OBJECT_STORAGE_ENDPOINT / ACCESS_KEY / SECRET_KEY 配置是否正确，"
            "以及 MinIO 服务是否正在运行。任务已终止。"
        )
        print(json.dumps({"status": "error", "user_message": msg}), file=sys.stderr)
        print(msg)
        sys.exit(1)
    except (EndpointResolutionError, NoCredentialsError, OSError, Exception) as e:
        msg = (
            f"无法连接到文件存储服务（endpoint: {endpoint}）: {e}\n"
            "请检查网络连接和 MinIO 配置。任务已终止。"
        )
        print(json.dumps({"status": "error", "user_message": msg}), file=sys.stderr)
        print(msg)
        sys.exit(1)


def _ensure_bucket(s3, bucket: str) -> None:
    from botocore.exceptions import ClientError
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            s3.create_bucket(Bucket=bucket)
        else:
            raise


def _sanitize(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value.strip())
    safe = safe.strip("._")
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe[:80] or "project"


# ---------------------------------------------------------------------------
# MinIO sync helpers
# ---------------------------------------------------------------------------

def _sync_down(s3, bucket: str, prefix: str, local_dir: Path) -> int:
    """Download all objects under prefix to local_dir. Returns count."""
    paginator = s3.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(prefix):]
            if not rel:
                continue
            dest = local_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            response = s3.get_object(Bucket=bucket, Key=key)
            dest.write_bytes(response["Body"].read())
            count += 1
    return count


def _sync_up(s3, bucket: str, prefix: str, local_dir: Path) -> int:
    """Upload all files from local_dir to MinIO under prefix. Returns count."""
    count = 0
    for local_file in local_dir.rglob("*"):
        if not local_file.is_file():
            continue
        rel = local_file.relative_to(local_dir).as_posix()
        key = prefix + rel
        content_type, _ = mimetypes.guess_type(local_file.name)
        content_type = content_type or "application/octet-stream"
        with open(local_file, "rb") as f:
            s3.put_object(Bucket=bucket, Key=key, Body=f.read(), ContentType=content_type)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    user_id = args.user_id or os.environ.get("SA_EMPLOYEE_ID", "0")
    fmt = args.format or "ppt169"
    date_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    sanitized = _sanitize(args.name)
    project_dir_name = f"{sanitized}_{fmt}_{date_str}"
    prefix = f"user-data/{user_id}/ppt-projects/{project_dir_name}/"

    s3 = _s3_client()
    bucket = _bucket()
    _verify_connection(s3, bucket)
    _ensure_bucket(s3, bucket)

    # Write project manifest
    manifest = {
        "project_name": project_dir_name,
        "format": fmt,
        "employee_id": str(user_id),
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "prefix": prefix,
    }
    s3.put_object(
        Bucket=bucket,
        Key=prefix + "_project.json",
        Body=json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        ContentType="application/json",
    )

    # Pre-create standard subdirectory markers so listing shows the structure
    for subdir in ("svg_output/", "images/", "sources/", "notes/", "exports/"):
        s3.put_object(Bucket=bucket, Key=prefix + subdir + ".keep", Body=b"", ContentType="text/plain")

    print(json.dumps({
        "prefix": prefix,
        "project_name": project_dir_name,
        "format": fmt,
        "employee_id": str(user_id),
    }, ensure_ascii=False))


def cmd_run(args: argparse.Namespace) -> None:
    if not args.cmd:
        sys.stderr.write("run: no command given after --\n")
        sys.exit(1)

    prefix = _normalize_prefix(args.prefix)
    s3 = _s3_client()
    bucket = _bucket()
    _verify_connection(s3, bucket)

    # Use /dev/shm (Linux RAM-backed tmpfs) so no data ever touches disk.
    # Falls back to /tmp on macOS / systems without /dev/shm (dev environments only).
    _shm = Path("/dev/shm") if Path("/dev/shm").is_dir() else Path("/tmp")
    tmp_dir = _shm / f"pptmaster_{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Sync down
        count_down = _sync_down(s3, bucket, prefix, tmp_dir)
        if count_down == 0:
            sys.stderr.write(f"[warn] No files found in MinIO prefix: {prefix}\n")

        # Interpolate {PROJECT_DIR} in command
        cmd = [c.replace("{PROJECT_DIR}", str(tmp_dir)) for c in args.cmd]

        # Run command
        result = subprocess.run(cmd)

        # Sync back (unless read-only)
        if not args.read_only:
            _sync_up(s3, bucket, prefix, tmp_dir)

        sys.exit(result.returncode)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def cmd_write_file(args: argparse.Namespace) -> None:
    prefix = _normalize_prefix(args.prefix)
    key = prefix + args.rel_path.lstrip("/")
    s3 = _s3_client()
    bucket = _bucket()
    _verify_connection(s3, bucket)

    if args.content is not None:
        data = args.content.encode("utf-8")
    elif args.file:
        data = Path(args.file).read_bytes()
    else:
        data = sys.stdin.buffer.read()

    content_type, _ = mimetypes.guess_type(args.rel_path)
    content_type = content_type or "application/octet-stream"

    _ensure_bucket(s3, bucket)
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    print(json.dumps({"status": "ok", "key": key, "bytes": len(data)}, ensure_ascii=False))


def cmd_read_file(args: argparse.Namespace) -> None:
    prefix = _normalize_prefix(args.prefix)
    key = prefix + args.rel_path.lstrip("/")

    s3 = _s3_client()
    bucket = _bucket()
    _verify_connection(s3, bucket)
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        sys.stdout.buffer.write(response["Body"].read())
    except Exception as e:
        sys.stderr.write(f"Error reading {key}: {e}\n")
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    prefix = _normalize_prefix(args.prefix)
    s3 = _s3_client()
    bucket = _bucket()
    _verify_connection(s3, bucket)
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            rel = obj["Key"][len(prefix):]
            if rel and not rel.endswith("/.keep"):
                print(rel)


def cmd_import_source(args: argparse.Namespace) -> None:
    src = Path(args.local_path)
    if not src.is_file():
        sys.stderr.write(f"File not found: {args.local_path}\n")
        sys.exit(1)
    dest_name = args.name or src.name
    prefix = _normalize_prefix(args.prefix)
    key = prefix + "sources/" + dest_name
    data = src.read_bytes()
    content_type, _ = mimetypes.guess_type(dest_name)
    content_type = content_type or "application/octet-stream"
    s3 = _s3_client()
    bucket = _bucket()
    _verify_connection(s3, bucket)
    _ensure_bucket(s3, bucket)
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    src.unlink()
    print(json.dumps({"status": "ok", "key": key, "bytes": len(data)}, ensure_ascii=False))


def _normalize_prefix(prefix: str) -> str:
    """Ensure prefix ends with /"""
    return prefix if prefix.endswith("/") else prefix + "/"


import time

# ---------------------------------------------------------------------------
# Working directory helpers (tmp-doc/ at project root)
# ---------------------------------------------------------------------------

def _tmp_doc_base() -> Path:
    """Return {project_root}/tmp-doc/. Project root is 4 levels above this script."""
    return Path(__file__).resolve().parents[4] / "tmp-doc"


def cmd_create_workdir(args: argparse.Namespace) -> None:
    """Create or reuse a unique working directory under tmp-doc/{employee_id}_{uuid}/.

    If a directory for this employee already exists and was created within the
    last WORKDIR_REUSE_WINDOW (default 5 minutes), return it instead of creating
    a new one.  This prevents double creation when the AI agent runs
    create-workdir multiple times in separate shell invocations.
    """
    WORKDIR_REUSE_WINDOW = 300  # seconds — when models re-run create-workdir, they do it within seconds

    employee_id = os.environ.get("SA_EMPLOYEE_ID", "0")
    tmp_doc = _tmp_doc_base()
    tmp_doc.mkdir(parents=True, exist_ok=True)

    # Reuse the most recent directory for this employee if within the window.
    now = time.time()
    for entry in sorted(tmp_doc.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        if not entry.name.startswith(f"{employee_id}_"):
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        age = now - mtime
        if age >= WORKDIR_REUSE_WINDOW:
            break  # sorted reverse by name ≈ reverse by time; older entries won't match
        print(json.dumps({"work_dir": str(entry), "reused": True}, ensure_ascii=False))
        return

    work_dir = tmp_doc / f"{employee_id}_{uuid.uuid4().hex}"
    work_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ("svg_output", "images", "sources", "notes", "exports"):
        (work_dir / subdir).mkdir(exist_ok=True)
    print(json.dumps({"work_dir": str(work_dir), "reused": False}, ensure_ascii=False))


def cmd_cleanup(args: argparse.Namespace) -> None:
    """Delete the working directory. Safety-checked: must be under tmp-doc/."""
    work_dir = Path(args.work_dir).resolve()
    tmp_doc = _tmp_doc_base().resolve()
    try:
        work_dir.relative_to(tmp_doc)
    except ValueError:
        msg = f"Safety check failed: {work_dir} is not under {tmp_doc}"
        print(json.dumps({"status": "error", "message": msg}), file=sys.stderr)
        print(msg)
        sys.exit(1)
    shutil.rmtree(work_dir)
    print(json.dumps({"status": "ok", "deleted": str(work_dir)}, ensure_ascii=False))


def cmd_cleanup_stale(args: argparse.Namespace) -> None:
    """Delete working directories older than N hours under tmp-doc/."""
    max_age_hours = int(args.max_age_hours) if args.max_age_hours else 24
    dry_run = args.dry_run
    tmp_doc = _tmp_doc_base().resolve()
    if not tmp_doc.is_dir():
        print(json.dumps({"status": "ok", "deleted": 0, "message": f"tmp-doc/ does not exist"}, ensure_ascii=False))
        return

    now = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted = 0
    errors: list[str] = []

    for entry in sorted(tmp_doc.iterdir()):
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


def _infer_work_dir(local_path: Path) -> "Path | None":
    """Return the work_dir that owns local_path, or None if not under tmp-doc/."""
    try:
        tmp_doc = _tmp_doc_base().resolve()
        resolved = local_path.resolve()
        resolved.relative_to(tmp_doc)              # raises ValueError if not under tmp-doc/
        work_dir_name = resolved.relative_to(tmp_doc).parts[0]
        return tmp_doc / work_dir_name
    except (ValueError, IndexError):
        return None


def cmd_upload_result(args: argparse.Namespace) -> None:
    """Upload a file from the working directory to MinIO user-data/{employee_id}/."""
    local_path = Path(args.local_path)

    # Infer work_dir BEFORE any early exit — cleanup must always run regardless
    # of whether the file exists or the upload succeeds.
    work_dir = _infer_work_dir(local_path)

    def _cleanup() -> None:
        if work_dir and work_dir.is_dir():
            shutil.rmtree(work_dir)

    # Guard: if the file doesn't exist the task is still in progress — clean up
    # and exit. The PPTX may be missing because generation failed, but the work
    # directory must not be left as an orphan.
    if not local_path.is_file():
        _cleanup()
        print(json.dumps({"status": "error", "message": f"File not found: {args.local_path}"}))
        sys.exit(1)

    try:
        user_id = args.user_id or os.environ.get("SA_EMPLOYEE_ID", "0")
        session_id = args.session or os.environ.get("SA_SESSION_ID", "")
        file_name = args.name or local_path.name
        artifact_id = str(uuid.uuid4())
        minio_key = f"user-data/{user_id}/{artifact_id}_{local_path.name}"

        content_type, _ = mimetypes.guess_type(local_path.name)
        content_type = content_type or "application/octet-stream"

        s3 = _s3_client()
        bucket = _bucket()
        _verify_connection(s3, bucket)
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
                            "source_type, source_name, created_at, updated_at) "
                            "VALUES (:id, :eid, :sid, :fname, :mkey, :fsize, 'skill', 'ppt-master', :now, :now)"
                        ),
                        dict(id=artifact_id, eid=int(user_id), sid=session_id or None,
                             fname=file_name, mkey=minio_key, fsize=file_size, now=now),
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
        # Always clean up the work directory — success, failure, or exception.
        _cleanup()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ppt-master project helper — working dir + MinIO upload",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create-workdir
    sub.add_parser("create-workdir", help="Create unique working dir under tmp-doc/; prints {work_dir}")

    # cleanup
    p_cleanup = sub.add_parser("cleanup", help="Delete working directory (safety-checked)")
    p_cleanup.add_argument("--work-dir", required=True, help="Path returned by create-workdir")

    # cleanup-stale
    p_cleanup_stale = sub.add_parser("cleanup-stale", help="Delete stale working dirs older than N hours")
    p_cleanup_stale.add_argument("--max-age-hours", default=None, help="Max age in hours (default: 24)")
    p_cleanup_stale.add_argument("--dry-run", action="store_true", help="List without deleting")

    # upload-result
    p_upload = sub.add_parser("upload-result", help="Upload a file to MinIO user-data/ and record in DB")
    p_upload.add_argument("local_path", help="Local file path to upload")
    p_upload.add_argument("--user-id", default=None, help="Employee ID (default: $SA_EMPLOYEE_ID)")
    p_upload.add_argument("--name", default=None, help="Display filename (default: original name)")
    p_upload.add_argument("--session", default=None, help="Session ID (default: $SA_SESSION_ID)")

    # Legacy MinIO commands (kept for compatibility / direct MinIO access)
    p_init = sub.add_parser("init", help="[legacy] Create project manifest in MinIO")
    p_init.add_argument("name"); p_init.add_argument("--format", default="ppt169"); p_init.add_argument("--user-id", default=None)

    p_run = sub.add_parser("run", help="[legacy] Sync MinIO ↔ /dev/shm, run cmd, sync back")
    p_run.add_argument("--prefix", required=True); p_run.add_argument("--read-only", action="store_true")
    p_run.add_argument("cmd", nargs=argparse.REMAINDER)

    p_write = sub.add_parser("write-file", help="[legacy] Write a file directly to MinIO")
    p_write.add_argument("--prefix", required=True); p_write.add_argument("rel_path")
    p_write.add_argument("--content", default=None); p_write.add_argument("--file", default=None)

    p_read = sub.add_parser("read-file", help="[legacy] Print a MinIO file to stdout")
    p_read.add_argument("--prefix", required=True); p_read.add_argument("rel_path")

    p_list = sub.add_parser("list", help="[legacy] List MinIO project files")
    p_list.add_argument("--prefix", required=True)

    p_import = sub.add_parser("import-source", help="[legacy] Upload local file to MinIO sources/")
    p_import.add_argument("--prefix", required=True); p_import.add_argument("local_path"); p_import.add_argument("--name", default=None)

    args = parser.parse_args()

    if args.command == "run" and args.cmd and args.cmd[0] == "--":
        args.cmd = args.cmd[1:]

    dispatch = {
        "create-workdir": cmd_create_workdir,
        "cleanup":        cmd_cleanup,
        "cleanup-stale":  cmd_cleanup_stale,
        "upload-result":  cmd_upload_result,
        "init":           cmd_init,
        "run":            cmd_run,
        "write-file":     cmd_write_file,
        "read-file":      cmd_read_file,
        "list":           cmd_list,
        "import-source":  cmd_import_source,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
