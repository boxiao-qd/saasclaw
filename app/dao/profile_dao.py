from sqlalchemy import select, update
from app.dao.base import BaseDAO
from app.models.models import UserProfile as UserProfileModel
from app.middleware.error_handler import AppError


class ProfileDAO(BaseDAO):
    async def get_settings(self) -> UserProfileModel | None:
        session = self._session()
        obj = await session.scalar(
            select(UserProfileModel).where(UserProfileModel.employee_id == self._employee_id)
        )
        await session.close()
        return obj

    async def update_settings(self, settings_json: str) -> UserProfileModel:
        session = self._session()
        obj = await session.scalar(
            select(UserProfileModel).where(UserProfileModel.employee_id == self._employee_id)
        )
        if not obj:
            raise AppError("BX_1003", "Profile not found", 404)
        await session.execute(
            update(UserProfileModel)
            .where(UserProfileModel.employee_id == self._employee_id)
            .values(settings=settings_json)
        )
        await session.commit()
        await session.close()
        return obj