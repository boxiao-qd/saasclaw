#!/usr/bin/env python3
"""Write content to MinIO.

Usage:
    # stdin → MinIO key
    echo "content" | python3 minio_write.py --key some/path/file.txt

    # local file → MinIO key
    python3 minio_write.py --key some/path/file.txt --file /local/file.txt

    # inline content → MinIO key
    python3 minio_write.py --key some/path/file.txt --content "hello world"

    # heredoc (recommended for SVG / large content)
    cat << 'EOF' | python3 minio_write.py --key some/path/file.txt
    <svg>...</svg>
    EOF

Required env vars:
    OBJECT_STORAGE_ENDPOINT     e.g. http://minio:9000
    OBJECT_STORAGE_ACCESS_KEY
    OBJECT_STORAGE_SECRET_KEY

Optional env vars:
    OBJECT_STORAGE_REGION       default: us-east-1
    OBJECT_STORAGE_BUCKET     default: sa-artifacts

Output (stdout JSON):
    Success: {"status": "ok", "key": "...", "bytes": N}
    Error:   {"status": "error", "message": "..."}
"""

from __future__ import annotations

import argparse
import json
import mimetypes
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


def _ensure_bucket(s3, bucket: str) -> None:
    from botocore.exceptions import ClientError
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            s3.create_bucket(Bucket=bucket)
        else:
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Write content to MinIO")
    parser.add_argument("--key", required=True, help="MinIO object key (path within bucket)")
    parser.add_argument("--file", default=None, help="Local file to upload (default: read stdin)")
    parser.add_argument("--content", default=None, help="Inline content string to upload")
    parser.add_argument("--content-type", default=None, help="MIME type (auto-detected if omitted)")
    args = parser.parse_args()

    # Determine content bytes
    if args.content is not None:
        data = args.content.encode("utf-8")
    elif args.file is not None:
        with open(args.file, "rb") as f:
            data = f.read()
    else:
        data = sys.stdin.buffer.read()

    content_type = args.content_type
    if not content_type:
        guessed, _ = mimetypes.guess_type(args.key)
        content_type = guessed or "application/octet-stream"

    bucket = os.environ.get("OBJECT_STORAGE_BUCKET", "sa-artifacts")

    try:
        s3 = _s3_client()
        _ensure_bucket(s3, bucket)
        s3.put_object(Bucket=bucket, Key=args.key, Body=data, ContentType=content_type)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps({"status": "ok", "key": args.key, "bytes": len(data)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
