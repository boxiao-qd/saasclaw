#!/usr/bin/env python3
"""General-purpose working directory manager for skills and subagents.

Every skill or subagent that generates files should:
1. Call `create` to get a unique work dir at task start
2. Write ALL intermediate and output files inside that dir
3. Upload the final deliverable via $SA_UPLOAD_SCRIPT
4. Call `cleanup` to delete the work dir after upload

Directory layout:
    {project_root}/tmp-doc/{employee_id}_{uuid}/

- Unique per (user, task) — no concurrent conflicts
- Local disk only during the task — deleted after upload
- Final results in MinIO under user-data/{employee_id}/

Usage:
    # Create work dir (prints JSON with work_dir path)
    python3 workdir.py create [--employee-id 42]

    # Delete work dir after task completes
    python3 workdir.py cleanup --path /path/to/tmp-doc/42_abc123ef/

Environment variables used:
    SA_EMPLOYEE_ID   — employee / user ID (fallback when --employee-id not given)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path


# Project root is two levels above this script: {project_root}/scripts/workdir.py
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TMP_DOC_BASE = _PROJECT_ROOT / "tmp-doc"


def cmd_create(args: argparse.Namespace) -> None:
    employee_id = args.employee_id or os.environ.get("SA_EMPLOYEE_ID", "0")
    work_dir = _TMP_DOC_BASE / f"{employee_id}_{uuid.uuid4().hex}"
    work_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"work_dir": str(work_dir)}, ensure_ascii=False))


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

    args = parser.parse_args()
    {"create": cmd_create, "cleanup": cmd_cleanup}[args.command](args)


if __name__ == "__main__":
    main()
