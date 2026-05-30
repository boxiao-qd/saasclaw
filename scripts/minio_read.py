#!/usr/bin/env python3
"""Read a file from MinIO.

Usage:
    # Read to stdout (UTF-8 text)
    python3 minio_read.py --key some/path/file.txt

    # Read to local file
    python3 minio_read.py --key some/path/file.txt --out /local/dest.txt

    # Check existence (exit 0 = exists, exit 1 = not found)
    python3 minio_read.py --key some/path/file.txt --exists

Required env vars: same as minio_write.py
"""

from __future__ import annotations

import argparse
import os
import sys


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Read a file from MinIO")
    parser.add_argument("--key", required=True, help="MinIO object key")
    parser.add_argument("--out", default=None, help="Write to local file instead of stdout")
    parser.add_argument("--exists", action="store_true", help="Only check existence; exit 0=found, 1=not found")
    args = parser.parse_args()

    bucket = os.environ.get("OBJECT_STORAGE_BUCKET", "sa-artifacts")
    s3 = _s3_client()

    if args.exists:
        from botocore.exceptions import ClientError
        try:
            s3.head_object(Bucket=bucket, Key=args.key)
            sys.exit(0)
        except ClientError:
            sys.exit(1)

    try:
        response = s3.get_object(Bucket=bucket, Key=args.key)
        data = response["Body"].read()
    except Exception as e:
        sys.stderr.write(f"Error reading {args.key}: {e}\n")
        sys.exit(1)

    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "wb") as f:
            f.write(data)
    else:
        sys.stdout.buffer.write(data)


if __name__ == "__main__":
    main()
