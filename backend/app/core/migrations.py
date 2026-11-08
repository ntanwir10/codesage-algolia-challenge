"""Programmatic Alembic runner used at application startup."""

from contextlib import contextmanager
from pathlib import Path

import structlog
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from alembic import command
from app.core.database import Base

try:
    import fcntl
except ImportError:  # shortcut: no SQLite migration lock on Windows; run one API process there
    fcntl = None

logger = structlog.get_logger()

_ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"
_BASELINE_TABLES = {"repositories", "code_files", "code_entities"}
_PG_LOCK_KEY = 0x636F646573616765  # "codesage": the advisory lock every CodeSage process migrates under


def _is_memory_sqlite(engine: Engine) -> bool:
    url = engine.url
    return url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:")


def upgrade_database(engine: Engine) -> None:
    """Bring the database behind `engine` to the latest schema revision.

    In-memory SQLite is created directly from the models, since a separate Alembic
    connection would see a different, empty database. Otherwise a pre-Alembic database
    (app tables present, no alembic_version) is stamped at `baseline`, then upgraded.
    """
    if _is_memory_sqlite(engine):
        import app.models  # noqa: F401  registers tables

        Base.metadata.create_all(engine)
        return

    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option(
        "sqlalchemy.url",
        engine.url.render_as_string(hide_password=False).replace("%", "%%"),
    )

    with _migration_lock(engine):
        tables = set(inspect(engine).get_table_names())
        if "alembic_version" not in tables and tables & _BASELINE_TABLES:
            logger.info("Stamping pre-Alembic database at baseline")
            command.stamp(cfg, "baseline")

        command.upgrade(cfg, "head")


@contextmanager
def _migration_lock(engine: Engine):
    """One process migrates at a time; API processes starting together otherwise race on the
    same DDL. The ones that waited then find the schema already at head"""
    if engine.url.get_backend_name() == "postgresql":
        # Autocommit: the lock is the session's, and an open transaction would sit idle meanwhile
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _PG_LOCK_KEY})
            try:
                yield
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _PG_LOCK_KEY})
    elif engine.url.get_backend_name() == "sqlite" and fcntl is not None:
        with open(f"{engine.url.database}-lock", "a") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)  # released when the file closes
            yield
    else:
        yield
