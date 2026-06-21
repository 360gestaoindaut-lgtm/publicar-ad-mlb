from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def worker_session():
    """Sessão sem pool para uso em Celery workers (evita conflito de event loop)."""
    worker_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        Session = async_sessionmaker(bind=worker_engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            yield session
    finally:
        await worker_engine.dispose()
