import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.migrations import _ALEMBIC_DIR, upgrade_database

NEW_TABLES = {"repositories", "code_files", "code_entities", "alembic_version"}


def _engine(path: Path):
    return create_engine(f"sqlite:///{path}")


def _cfg(path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def _build_legacy(path: Path) -> None:
    """A pre-Alembic database: baseline schema via migration SQL, then alembic_version dropped."""
    command.upgrade(_cfg(path), "baseline")
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE alembic_version")
        for rid, url in ((1, "https://x/dup"), (2, "https://x/dup"), (3, "https://x/solo")):
            conn.execute(
                "INSERT INTO repositories (id, name, url, status) VALUES (?, ?, ?, 'completed')",
                (rid, f"repo{rid}", url),
            )
            conn.execute(
                "INSERT INTO code_files (id, repository_id, file_path, file_name, content) "
                "VALUES (?, ?, 'a.py', 'a.py', 'x=1')",
                (rid, rid),
            )
            conn.execute(
                "INSERT INTO code_entities (id, file_id, repository_id, entity_type, entity_name) "
                "VALUES (?, ?, ?, 'function', 'f')",
                (rid, rid, rid),
            )
        conn.execute(
            "INSERT INTO sessions (session_id) VALUES ('s1')",
        )
        conn.execute(
            "INSERT INTO search_indexes (repository_id, algolia_object_id, entity_type, "
            "entity_name, file_path, content) VALUES (2, 'o1', 'function', 'f', 'a.py', 'c')"
        )


def _counts(path: Path) -> dict:
    with sqlite3.connect(path) as conn:
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("repositories", "code_files", "code_entities")
        }


def test_fresh_database_has_expected_schema(tmp_path):
    db = tmp_path / "fresh.db"
    engine = _engine(db)
    upgrade_database(engine)

    insp = inspect(engine)
    assert set(insp.get_table_names()) == NEW_TABLES
    unique_cols = [c["column_names"] for c in insp.get_unique_constraints("repositories")]
    assert ["url"] in unique_cols
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "cleanup"


def test_legacy_database_is_stamped_and_cleaned(tmp_path):
    db = tmp_path / "legacy.db"
    _build_legacy(db)
    engine = _engine(db)
    upgrade_database(engine)

    assert set(inspect(engine).get_table_names()) == NEW_TABLES
    with sqlite3.connect(db) as conn:
        repos = conn.execute("SELECT id, name, url FROM repositories ORDER BY id").fetchall()
        assert repos == [(2, "repo2", "https://x/dup"), (3, "repo3", "https://x/solo")]
        files = conn.execute("SELECT id, repository_id FROM code_files ORDER BY id").fetchall()
        assert files == [(2, 2), (3, 3)]
        ents = conn.execute("SELECT id, file_id FROM code_entities ORDER BY id").fetchall()
        assert ents == [(2, 2), (3, 3)]
        assert conn.execute("SELECT content FROM code_files WHERE id=2").fetchone() == ("x=1",)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO repositories (name, url) VALUES ('n', 'https://x/solo')")


def test_upgrade_twice_is_noop(tmp_path):
    db = tmp_path / "twice.db"
    _build_legacy(db)
    engine = _engine(db)
    upgrade_database(engine)
    before = _counts(db)
    upgrade_database(engine)
    assert _counts(db) == before
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar() == 1


def test_downgrade_to_baseline(tmp_path):
    db = tmp_path / "down.db"
    engine = _engine(db)
    upgrade_database(engine)
    command.downgrade(_cfg(db), "baseline")

    insp = inspect(engine)
    assert set(insp.get_table_names()) == NEW_TABLES | {"sessions", "search_indexes"}
    assert not insp.get_unique_constraints("repositories")
    # and back up again
    upgrade_database(engine)
    assert set(inspect(engine).get_table_names()) == NEW_TABLES


def test_memory_database_uses_create_all():
    engine = create_engine("sqlite://")
    upgrade_database(engine)
    assert set(inspect(engine).get_table_names()) == NEW_TABLES - {"alembic_version"}
