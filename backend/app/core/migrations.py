"""Programmatic Alembic runner used at application startup."""

from pathlib import Path

import structlog
from alembic.config import Config
from sqlalchemy import Engine, inspect

from alembic import command
from app.core.database import Base

logger = structlog.get_logger()

_ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"
_BASELINE_TABLES = {"repositories", "code_files", "code_entities"}


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

    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and tables & _BASELINE_TABLES:
        logger.info("Stamping pre-Alembic database at baseline")
        command.stamp(cfg, "baseline")

    command.upgrade(cfg, "head")
