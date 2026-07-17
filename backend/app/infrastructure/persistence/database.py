"""Database connection setup — skeleton only.

In Phase 1 this is a no-op. Real connection will use SQLAlchemy async.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config.settings import settings


class DatabaseManager:
    """Manages the async SQLAlchemy engine and session factory.

    Phase 1: engine is None; no real DB calls.
    Phase 2: initialized on app startup.
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None

    @property
    def engine(self) -> AsyncEngine | None:
        return self._engine

    async def initialize(self) -> None:
        """Create the async engine.

        Called during FastAPI lifespan startup.
        """
        if settings.database_url.startswith("sqlite"):
            self._engine = create_async_engine(
                settings.database_url,
                echo=settings.database_echo,
            )
        else:
            self._engine = create_async_engine(
                settings.database_url,
                echo=settings.database_echo,
                pool_size=10,
                max_overflow=20,
            )

    async def dispose(self) -> None:
        if self._engine:
            await self._engine.dispose()

    def get_session(self) -> AsyncSession:
        if not self._engine:
            raise RuntimeError("Database not initialized")
        return AsyncSession(self._engine)


db_manager = DatabaseManager()
