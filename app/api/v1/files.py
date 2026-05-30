"""User files API — list / download / delete files stored in MinIO under user-data/{employee_id}/."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.config import settings
from app.dao.artifact_file_dao import ArtifactFileDAO
from app.db.database import get_session_factory
from app.dependencies import get_employee_id

router = APIRouter(prefix="/files", tags=["files"])
log = logging.getLogger(__name__)


def _s3_client():
    import boto3

    kw = dict(
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
        region_name=settings.object_storage_region or "us-east-1",
    )
    if settings.object_storage_endpoint:
        kw["endpoint_url"] = settings.object_storage_endpoint
    return boto3.client("s3", **kw)


@router.get("")
async def list_files(
    limit: int = 50,
    offset: int = 0,
    employee_id: int = Depends(get_employee_id),
):
    dao = ArtifactFileDAO(get_session_factory(), employee_id)
    files = await dao.list_files(limit=limit, offset=offset)
    total = await dao.count()
    return {
        "files": [
            {
                "id": f.id,
                "file_name": f.file_name,
                "file_size": f.file_size,
                "source_type": f.source_type,
                "source_name": f.source_name,
                "session_id": f.session_id,
                "minio_key": f.minio_key,
                "created_at": f.created_at,
            }
            for f in files
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    employee_id: int = Depends(get_employee_id),
):
    dao = ArtifactFileDAO(get_session_factory(), employee_id)
    f = await dao.get_by_id(file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")

    bucket = settings.object_storage_bucket

    try:
        s3 = _s3_client()
        resp = s3.get_object(Bucket=bucket, Key=f.minio_key)
        data = resp["Body"].read()
        content_type = resp.get("ContentType", "application/octet-stream")
    except Exception as e:
        log.error("MinIO download failed for key %s: %s", f.minio_key, e)
        raise HTTPException(status_code=502, detail="Failed to retrieve file from storage")

    safe_name = f.file_name.replace('"', "'")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    employee_id: int = Depends(get_employee_id),
):
    dao = ArtifactFileDAO(get_session_factory(), employee_id)
    f = await dao.get_by_id(file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")

    # Delete from MinIO
    bucket = settings.object_storage_bucket
    try:
        s3 = _s3_client()
        s3.delete_object(Bucket=bucket, Key=f.minio_key)
    except Exception as e:
        log.warning("MinIO delete failed for key %s: %s", f.minio_key, e)
        # Continue to delete DB record even if MinIO object is missing

    # Delete DB record
    await dao.delete_by_id(file_id)
    return {"status": "deleted", "id": file_id}
