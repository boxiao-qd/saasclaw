from sqlalchemy import select, delete

from app.dao.base import BaseDAO
from app.models.models import ArtifactFile


class ArtifactFileDAO(BaseDAO):
    async def list_files(self, limit: int = 50, offset: int = 0) -> list[ArtifactFile]:
        async with self._session_factory() as session:
            stmt = (
                select(ArtifactFile)
                .where(self._filter_by_user(ArtifactFile))
                .order_by(ArtifactFile.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.scalars(stmt)
            return list(result.all())

    async def count(self) -> int:
        from sqlalchemy import func
        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(ArtifactFile).where(
                self._filter_by_user(ArtifactFile)
            )
            result = await session.scalar(stmt)
            return result or 0

    async def get_by_id(self, file_id: str) -> ArtifactFile | None:
        async with self._session_factory() as session:
            stmt = select(ArtifactFile).where(
                self._filter_by_user(ArtifactFile),
                ArtifactFile.id == file_id,
            )
            result = await session.scalars(stmt)
            return result.first()

    async def delete_by_id(self, file_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = (
                delete(ArtifactFile)
                .where(
                    self._filter_by_user(ArtifactFile),
                    ArtifactFile.id == file_id,
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
