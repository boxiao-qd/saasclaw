from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event, text
from app.config import settings

_engine = None
_session_factory = None


async def init_db():
    global _engine, _session_factory

    is_sqlite = settings.db_url.startswith("sqlite")
    is_mysql = "mysql" in settings.db_url

    engine_kwargs = {"echo": settings.debug}
    if is_mysql:
        # Recycle connections every hour to avoid "server has gone away" errors;
        # pre-ping validates the connection before each use.
        # pool_pre_ping=False: aiomysql's async ping() requires a 'reconnect' arg
        # that SQLAlchemy's dialect doesn't pass — causes TypeError on first use.
        # pool_recycle handles stale connections instead.
        engine_kwargs.update({
            "pool_recycle": 3600,
            "pool_pre_ping": False,
            "pool_size": 10,
            "max_overflow": 20,
        })

    _engine = create_async_engine(settings.db_url, **engine_kwargs)

    if is_sqlite:
        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # Auto-create tables on startup
    from app.models.base import Base
    from app.models.models import (  # noqa: F401 — all must be imported so create_all sees them
        Session, Message, Memory, UserProfile, Skill, Subagent,
        CronJob, CronRun, Notification, Todo, ArtifactFile,
    )
    from app.models.user import User  # noqa: F401
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Column-level migrations for tables that already existed before new columns were added.
    await _run_column_migrations()


async def _run_column_migrations():
    """Add columns that were introduced after the initial table creation.

    Uses IF NOT EXISTS / information_schema checks so this is safe to run on
    every startup against both SQLite and MySQL.
    """
    sf = get_session_factory()
    async with sf() as session:
        is_mysql = "mysql" in settings.db_url
        is_sqlite = settings.db_url.startswith("sqlite")

        if is_mysql:
            # Add file_id to notifications if missing
            result = await session.execute(text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "  AND TABLE_NAME = 'notifications' "
                "  AND COLUMN_NAME = 'file_id'"
            ))
            if result.scalar() == 0:
                await session.execute(text(
                    "ALTER TABLE notifications "
                    "ADD COLUMN file_id VARCHAR(36) NULL, "
                    "ADD CONSTRAINT fk_notif_file "
                    "  FOREIGN KEY (file_id) REFERENCES artifact_files(id) ON DELETE SET NULL"
                ))
                await session.commit()

            # Add is_running and consecutive_errors to cron_jobs if missing
            result = await session.execute(text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "  AND TABLE_NAME = 'cron_jobs' "
                "  AND COLUMN_NAME = 'is_running'"
            ))
            if result.scalar() == 0:
                await session.execute(text(
                    "ALTER TABLE cron_jobs "
                    "ADD COLUMN is_running SMALLINT DEFAULT 0, "
                    "ADD COLUMN consecutive_errors INT DEFAULT 0"
                ))
                await session.commit()

        elif is_sqlite:
            result = await session.execute(text("PRAGMA table_info(notifications)"))
            cols = {row[1] for row in result.fetchall()}
            if "file_id" not in cols:
                await session.execute(text(
                    "ALTER TABLE notifications ADD COLUMN file_id VARCHAR(36) NULL "
                    "REFERENCES artifact_files(id) ON DELETE SET NULL"
                ))
                await session.commit()

            result = await session.execute(text("PRAGMA table_info(cron_jobs)"))
            cols = {row[1] for row in result.fetchall()}
            if "is_running" not in cols:
                await session.execute(text(
                    "ALTER TABLE cron_jobs ADD COLUMN is_running SMALLINT DEFAULT 0"
                ))
                await session.commit()
            if "consecutive_errors" not in cols:
                await session.execute(text(
                    "ALTER TABLE cron_jobs ADD COLUMN consecutive_errors INT DEFAULT 0"
                ))
                await session.commit()


async def close_db():
    global _engine
    if _engine:
        await _engine.dispose()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory
