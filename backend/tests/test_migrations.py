import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.migrations import _ALEMBIC_DIR, upgrade_database

HEAD = "commit_sha"
DROPPED = {
    "repositories": {"repo_metadata", "security_score", "vulnerability_count"},
    "code_files": {"file_name", "is_analyzed", "size_bytes"},
    "code_entities": {
        "full_name", "start_column", "end_column", "complexity_score", "is_public", "is_async",
    },
}
NEW_TABLES = {"repositories", "code_files", "code_entities", "alembic_version"}


_engines = []


def _engine(path: Path):
    engine = create_engine(f"sqlite:///{path}")
    _engines.append(engine)
    return engine


@pytest.fixture(autouse=True)
def _dispose_engines():
    """Close each test's pooled connections; left open, they surface as ResourceWarnings later"""
    yield
    while _engines:
        _engines.pop().dispose()


def _cfg(path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def _build_legacy(path: Path) -> None:
    """A pre-Alembic database: baseline schema via migration SQL, then alembic_version dropped."""
    command.upgrade(_cfg(path), "baseline")
    with closing(sqlite3.connect(path)) as conn, conn:  # closing: the with alone only commits
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
    with closing(sqlite3.connect(path)) as conn, conn:  # closing: the with alone only commits
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
    for table, dropped in DROPPED.items():
        assert not dropped & {c["name"] for c in insp.get_columns(table)}
    assert "entity_metadata" in {c["name"] for c in insp.get_columns("code_entities")}
    assert "commit_sha" in {c["name"] for c in insp.get_columns("repositories")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD


def test_legacy_database_is_stamped_and_cleaned(tmp_path):
    db = tmp_path / "legacy.db"
    _build_legacy(db)
    engine = _engine(db)
    upgrade_database(engine)

    assert set(inspect(engine).get_table_names()) == NEW_TABLES
    with closing(sqlite3.connect(db)) as conn, conn:  # closing: the with alone only commits
        repos = conn.execute("SELECT id, name, url FROM repositories ORDER BY id").fetchall()
        assert repos == [(2, "repo2", "https://x/dup"), (3, "repo3", "https://x/solo")]
        files = conn.execute("SELECT id, repository_id FROM code_files ORDER BY id").fetchall()
        assert files == [(2, 2), (3, 3)]
        ents = conn.execute("SELECT id, file_id FROM code_entities ORDER BY id").fetchall()
        assert ents == [(2, 2), (3, 3)]
        assert conn.execute("SELECT content FROM code_files WHERE id=2").fetchone() == ("x=1",)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO repositories (name, url) VALUES ('n', 'https://x/solo')")


def test_legacy_database_without_legacy_tables_upgrades(tmp_path):
    # Older create_all() runs could leave out sessions and search_indexes
    db = tmp_path / "legacy-minimal.db"
    _build_legacy(db)
    with closing(sqlite3.connect(db)) as conn, conn:  # closing: the with alone only commits
        conn.execute("DROP TABLE sessions")
        conn.execute("DROP TABLE search_indexes")
    engine = _engine(db)
    upgrade_database(engine)

    assert set(inspect(engine).get_table_names()) == NEW_TABLES
    assert _counts(db) == {"repositories": 2, "code_files": 2, "code_entities": 2}


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


def test_upgrade_from_cleanup_keeps_rows(tmp_path):
    db = tmp_path / "keep.db"
    command.upgrade(_cfg(db), "cleanup")
    with closing(sqlite3.connect(db)) as conn, conn:  # closing: the with alone only commits
        conn.execute(
            "INSERT INTO repositories (id, name, url, status, security_score, repo_metadata) "
            "VALUES (1, 'r', 'https://x/r', 'completed', 90, '{}')"
        )
        conn.execute(
            "INSERT INTO code_files (id, repository_id, file_path, file_name, content, "
            "language, size_bytes, line_count, is_analyzed) "
            "VALUES (1, 1, 'a.py', 'a.py', 'x=1', 'python', 3, 1, 1)"
        )
        conn.execute(
            "INSERT INTO code_entities (id, file_id, repository_id, entity_type, entity_name, "
            "full_name, start_line, signature, entity_metadata, is_public) "
            "VALUES (1, 1, 1, 'function', 'f', 'm.f', 1, 'f()', '{\"k\": 1}', 1)"
        )

    command.upgrade(_cfg(db), "head")

    engine = _engine(db)
    insp = inspect(engine)
    for table, dropped in DROPPED.items():
        assert not dropped & {c["name"] for c in insp.get_columns(table)}
    index_names = {i["name"] for t in DROPPED for i in insp.get_indexes(t)}
    assert not {"ix_code_entities_full_name", "ix_code_files_file_name"} & index_names
    with closing(sqlite3.connect(db)) as conn, conn:  # closing: the with alone only commits
        assert conn.execute("SELECT id, name, url, status FROM repositories").fetchall() == [
            (1, "r", "https://x/r", "completed")
        ]
        assert conn.execute(
            "SELECT id, repository_id, file_path, content, language, line_count FROM code_files"
        ).fetchall() == [(1, 1, "a.py", "x=1", "python", 1)]
        assert conn.execute(
            "SELECT id, file_id, entity_name, start_line, signature, entity_metadata "
            "FROM code_entities"
        ).fetchall() == [(1, 1, "f", 1, "f()", '{"k": 1}')]


def test_downgrade_from_head_restores_nullable_columns(tmp_path):
    db = tmp_path / "head_down.db"
    engine = _engine(db)
    upgrade_database(engine)
    with closing(sqlite3.connect(db)) as conn, conn:  # closing: the with alone only commits
        conn.execute("INSERT INTO repositories (id, name, url) VALUES (1, 'r', 'https://x/r')")
        conn.execute(
            "INSERT INTO code_files (id, repository_id, file_path, content) "
            "VALUES (1, 1, 'a.py', 'x=1')"
        )
    command.downgrade(_cfg(db), "cleanup")

    insp = inspect(engine)
    for table, restored in DROPPED.items():
        columns = {c["name"]: c for c in insp.get_columns(table)}
        assert restored <= set(columns)
        assert all(columns[name]["nullable"] for name in restored)
    assert "ix_code_files_file_name" in {i["name"] for i in insp.get_indexes("code_files")}
    assert "ix_code_entities_full_name" in {
        i["name"] for i in insp.get_indexes("code_entities")
    }
    with closing(sqlite3.connect(db)) as conn, conn:  # closing: the with alone only commits
        assert conn.execute("SELECT COUNT(*) FROM code_files").fetchone() == (1,)
    # and forward again
    upgrade_database(engine)
    assert not DROPPED["code_files"] & {c["name"] for c in inspect(engine).get_columns("code_files")}


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
    _engines.append(engine)  # disposed after the test like the file-backed ones
    upgrade_database(engine)
    assert set(inspect(engine).get_table_names()) == NEW_TABLES - {"alembic_version"}
