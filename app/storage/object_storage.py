"""Object storage provider -- abstract layer for S3/MinIO/OSS.

Supports:
- Single file operations (put/get/delete)
- Directory tree operations (list_directory, get_directory) for skill/subagent progressive loading
- Progressive loading flow: header_index(DB) → SKILL.md → script/ → references/ → assets/
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from app.config import settings

log = logging.getLogger(__name__)


class ObjectStorageError(Exception):
    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


class ObjectStorageProviderProtocol(Protocol):
    async def put(self, employee_id: int, object_key: str, data: bytes | str,
                  content_type: str = "text/markdown") -> str: ...
    async def get(self, employee_id: int, object_key: str) -> bytes | None: ...
    async def delete(self, employee_id: int, object_key: str) -> bool: ...
    async def list_objects(self, employee_id: int, prefix: str = "") -> list[str]: ...
    async def list_directory(self, employee_id: int, dir_key: str) -> list[str]: ...
    async def get_directory(self, employee_id: int, dir_key: str) -> dict[str, bytes]: ...


class LocalFileStorage:
    """Dev-mode fallback: store skill/subagent files in local directory."""

    def __init__(self, base_dir: str = ""):
        self._base = Path(base_dir or settings.saas_user_config_dir)

    def _resolve_path(self, employee_id: int, object_key: str) -> Path:
        # object_key is the full path (e.g. user-skill/{id}/SKILL.md); employee_id unused here.
        resolved = self._base / object_key
        try:
            resolved.resolve().relative_to(self._base.resolve())
        except ValueError:
            raise ObjectStorageError(f"Path traversal rejected: {object_key}")
        return resolved

    async def put(self, employee_id: int, object_key: str, data: bytes | str,
                  content_type: str = "text/markdown") -> str:
        path = self._resolve_path(employee_id, object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            data = data.encode("utf-8")
        path.write_bytes(data)
        return f"local:{path}"

    async def get(self, employee_id: int, object_key: str) -> bytes | None:
        path = self._resolve_path(employee_id, object_key)
        if path.exists():
            return path.read_bytes()
        return None

    async def delete(self, employee_id: int, object_key: str) -> bool:
        path = self._resolve_path(employee_id, object_key)
        if path.exists():
            path.unlink()
            return True
        return True  # non-existent is OK

    async def list_objects(self, employee_id: int, prefix: str = "") -> list[str]:
        base = self._resolve_path(employee_id, prefix)
        if not base.exists():
            return []
        # return paths relative to the prefix directory
        return [str(p.relative_to(base)) for p in base.rglob("*") if p.is_file()]

    async def list_directory(self, employee_id: int, dir_key: str) -> list[str]:
        """List files in a skill/subagent directory tree."""
        dir_path = self._resolve_path(employee_id, dir_key)
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        return [str(p.relative_to(dir_path)) for p in dir_path.rglob("*") if p.is_file()]

    async def get_directory(self, employee_id: int, dir_key: str) -> dict[str, bytes]:
        """Fetch all files in a directory tree. Returns {relative_path: content}."""
        dir_path = self._resolve_path(employee_id, dir_key)
        if not dir_path.exists() or not dir_path.is_dir():
            return {}
        result = {}
        for p in dir_path.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(dir_path))
                result[rel] = p.read_bytes()
        return result


class S3ObjectStorage:
    """S3/MinIO implementation using aioboto3."""

    def __init__(self, session=None, endpoint_url: str = "", bucket: str = "",
                 prefix: str = "bx-sa", region: str = ""):
        self._session = session
        self._endpoint_url = endpoint_url
        self._bucket = bucket
        self._prefix = prefix
        self._region = region

    def _full_key(self, employee_id: int, object_key: str) -> str:
        # object_key is already the full MinIO path (e.g. user-skill/{id}/SKILL.md).
        # employee_id is kept in the signature for interface compatibility but unused.
        return object_key

    async def put(self, employee_id: int, object_key: str, data: bytes | str,
                  content_type: str = "text/markdown") -> str:
        if isinstance(data, str):
            data = data.encode("utf-8")
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
        ) as s3:
            resp = await s3.put_object(
                Bucket=self._bucket,
                Key=self._full_key(employee_id, object_key),
                Body=data,
                ContentType=content_type,
            )
            return resp.get("ETag", "")

    async def get(self, employee_id: int, object_key: str) -> bytes | None:
        try:
            async with self._session.client(
                "s3",
                endpoint_url=self._endpoint_url,
                region_name=self._region,
            ) as s3:
                resp = await s3.get_object(
                    Bucket=self._bucket,
                    Key=self._full_key(employee_id, object_key),
                )
                body = await resp["Body"].read()
                return body
        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                return None
            raise ObjectStorageError(f"Failed to get {object_key}", cause=e)

    async def delete(self, employee_id: int, object_key: str) -> bool:
        try:
            async with self._session.client(
                "s3",
                endpoint_url=self._endpoint_url,
                region_name=self._region,
            ) as s3:
                await s3.delete_object(
                    Bucket=self._bucket,
                    Key=self._full_key(employee_id, object_key),
                )
            return True
        except Exception as e:
            raise ObjectStorageError(f"Failed to delete {object_key}", cause=e)

    async def list_objects(self, employee_id: int, prefix: str = "") -> list[str]:
        try:
            async with self._session.client(
                "s3",
                endpoint_url=self._endpoint_url,
                region_name=self._region,
            ) as s3:
                full_prefix = self._full_key(employee_id, prefix)
                resp = await s3.list_objects_v2(
                    Bucket=self._bucket,
                    Prefix=full_prefix,
                )
                keys = [obj["Key"] for obj in resp.get("Contents", [])]
                # strip the list prefix to return relative keys
                base = full_prefix if full_prefix.endswith("/") else full_prefix + "/"
                return [k.removeprefix(base) for k in keys]
        except Exception as e:
            raise ObjectStorageError(f"Failed to list {prefix}", cause=e)

    async def list_directory(self, employee_id: int, dir_key: str) -> list[str]:
        """List files under a skill/subagent directory in object storage."""
        return await self.list_objects(employee_id, f"{dir_key}/")

    async def get_directory(self, employee_id: int, dir_key: str) -> dict[str, bytes]:
        """Fetch all files in a skill/subagent directory from object storage.
        Returns {relative_path: content} for progressive loading."""
        file_keys = await self.list_directory(employee_id, dir_key)
        result = {}
        dir_prefix = dir_key.rstrip("/") + "/"
        for rel_key in file_keys:
            # list_directory returns paths relative to dir_key; reconstruct full key for get()
            content = await self.get(employee_id, dir_prefix + rel_key)
            if content is not None:
                result[rel_key] = content
        return result


def create_object_storage() -> ObjectStorageProviderProtocol:
    backend = settings.object_storage_backend

    if not backend:
        return LocalFileStorage(base_dir=settings.saas_user_config_dir)

    if backend in ("s3", "minio"):
        try:
            import aioboto3
            session = aioboto3.Session(
                aws_access_key_id=settings.object_storage_access_key,
                aws_secret_access_key=settings.object_storage_secret_key,
            )
            return S3ObjectStorage(
                session=session,
                endpoint_url=settings.object_storage_endpoint,
                bucket=settings.object_storage_bucket,
                prefix=settings.object_storage_prefix,
                region=settings.object_storage_region,
            )
        except ImportError:
            log.warning("aioboto3 not installed, falling back to LocalFileStorage")
            return LocalFileStorage()

    log.warning(f"Unsupported object storage backend: {backend}, using LocalFileStorage")
    return LocalFileStorage()