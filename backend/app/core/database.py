import structlog
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Create SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    # Sessions cross threads (FastAPI's threadpool, background jobs); SQLite needs this to allow it
    connect_args=(
        {"check_same_thread": False}
        if settings.database_url.startswith("sqlite")
        else {}
    ),
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.sql_echo,
)

if settings.database_url.startswith("sqlite") and ":memory:" not in settings.database_url:

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    except HTTPException:
        # A deliberate 4xx from the endpoint, not a database problem
        db.rollback()
        raise
    except Exception as e:
        logger.error("Database session error", error=str(e))
        db.rollback()
        raise
    finally:
        db.close()
