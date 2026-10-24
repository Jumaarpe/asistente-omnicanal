import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
from app.core.logger import logger
from app.database.base import Base

# Garantizar que el directorio padre de la base de datos exista
if settings.DATABASE_URL.startswith("sqlite"):
    db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

# Motor asíncrono
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Configurar SQLite para alta concurrencia (WAL mode, busy timeout) si el backend es SQLite
if "sqlite" in settings.DATABASE_URL:
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

# Fábrica de sesiones asíncronas
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def init_db() -> None:
    """
    Inicializa las tablas de la base de datos de manera asíncrona.
    Se ejecuta durante el arranque (startup) de FastAPI.
    """
    # Importar todos los modelos para que Base.metadata los registre
    import app.models  # noqa: F401

    logger.info("🔧 Inicializando esquema de base de datos relacional...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Tablas de base de datos verificadas y sincronizadas exitosamente.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependencia de FastAPI para inyectar una sesión de base de datos asíncrona.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
