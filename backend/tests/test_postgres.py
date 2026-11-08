"""Postgres, against a real server: set TEST_POSTGRES_URL (CI does). Skipped otherwise.

Covers what SQLite would hide: the migrations on Postgres (and their advisory lock), column
types (bytea vectors, booleans, timestamps with time zone), the job claim that workers race for
and the one-job-per-repository index that API processes race for.
"""

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.migrations import upgrade_database
from app.models import CodeEntity, CodeFile, Job, Repository
from app.services import repository_service

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set TEST_POSTGRES_URL to run against Postgres")


@pytest.fixture
def empty_pg():
    engine = create_engine(Settings(database_url=URL).database_url)
    with engine.begin() as conn:  # a clean database for each test
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    yield engine
    engine.dispose()


@pytest.fixture
def pg(empty_pg, monkeypatch):
    upgrade_database(empty_pg)
    factory = sessionmaker(bind=empty_pg)
    monkeypatch.setattr(repository_service, "SessionLocal", factory)
    return factory


def test_a_plain_postgresql_url_uses_psycopg():
    assert Settings(database_url="postgresql://u:p@h/db").database_url == "postgresql+psycopg://u:p@h/db"
    assert Settings(database_url="postgres://u:p@h/db").database_url == "postgresql+psycopg://u:p@h/db"


def test_migrations_build_the_schema(pg):
    tables = set(inspect(pg.kw["bind"]).get_table_names())
    assert {"repositories", "code_files", "code_entities", "jobs", "alembic_version"} <= tables


def test_processes_starting_together_migrate_one_at_a_time(empty_pg, migrate_together):
    migrate_together(URL)

    with empty_pg.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "unique_jobs"


def test_rows_round_trip_including_vectors(pg):
    with pg() as db:
        repo = Repository(name="o/r", url="https://github.com/o/r", status="completed", commit_sha="a" * 40)
        db.add(repo)
        db.flush()
        file = CodeFile(repository_id=repo.id, file_path="a.py", content="def f(): pass\n", language="python")
        db.add(file)
        db.flush()
        db.add(CodeEntity(file_id=file.id, repository_id=repo.id, entity_type="function", entity_name="f",
                          start_line=1, end_line=1, embedding=b"\x00\x00\x80?", embedding_model="m"))
        db.commit()
        entity = db.query(CodeEntity).one()
        assert (entity.embedding, entity.embedding_model) == (b"\x00\x00\x80?", "m")


def test_one_worker_wins_a_job(pg, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "index_workers", "external")
    with pg() as db:
        repo = Repository(name="o/r", url="https://github.com/o/r", status="completed")
        db.add(repo)
        db.commit()
        repository_id = repo.id

    repository_service.start_processing(repository_id, force_reprocess=True)
    first, second = repository_service.claim_job("a:1"), repository_service.claim_job("b:2")

    assert first.claimed_by == "a:1" and second is None
    with pg() as db:
        assert db.query(Job).count() == 1


def test_a_job_another_api_process_queued_first_counts_as_busy(pg, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "index_workers", "external")
    with pg() as db:
        repo = Repository(name="o/r", url="https://github.com/o/r", status="completed")
        db.add(repo)
        db.commit()
        repository_id = repo.id
    repository_service.start_processing(repository_id)
    monkeypatch.setattr(repository_service, "is_processing", lambda _id: False)  # both checked first

    with pytest.raises(repository_service.RepositoryBusyError):
        repository_service.start_processing(repository_id)
    with pg() as db:
        assert db.query(Job).count() == 1
