from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer
from datetime import datetime


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(String(36), default=lambda: datetime.utcnow().isoformat())
    updated_at: Mapped[datetime] = mapped_column(String(36), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())


class UserAccountMixin:
    employee_id: Mapped[int] = mapped_column(Integer, nullable=False)


GLOBAL_EMPLOYEE_ID = 0
GLOBAL_SENTINEL = "__global__"  # kept for backward-compat during migration