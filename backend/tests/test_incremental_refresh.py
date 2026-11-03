"""Incremental runs reuse unchanged files; the scheduled refresh starts them for moved branches"""

import asyncio

import pytest

from app.models.code_entity import CodeEntity
from app.models.code_file import CodeFile
from app.models.repository import Repository
from app.services import code_parser, repository_service
from app.services.github_service import GitHubFile, RepositoryCheckError
from app.services.repository_service import _ENTITY_COPY, RepositoryService

MODULE_A = "import os\n\ndef alpha():\n    return 1\n\nclass Beta:\n    def gamma(self):\n        pass\n"
MODULE_B = "def delta(x):\n    return x\n"
QUOTED = 'pkg/q"uote.py'


def github_file(path, content):
    return GitHubFile(
        path=path, content=content, size=len(content.encode()), language="python",
        filename=path.split("/")[-1],
    )


@pytest.fixture
def repository(db_session):
    repo = Repository(
        name="octo/demo", url="https://github.com/octo/demo", status="pending",
        total_files=0, processed_files=0, total_lines=0,
    )
    db_session.add(repo)
    db_session.commit()
    return repo


@pytest.fixture
def parsed(monkeypatch):
    """Paths the parser was asked to parse"""
    paths = []
    real = code_parser.CodeParser.extract_entities

    async def record(self, path, content, language):
        paths.append(path)
        return await real(self, path, content, language)

    monkeypatch.setattr(code_parser.CodeParser, "extract_entities", record)
    return paths


async def run(db_session, repository, incremental=False):
    await RepositoryService(db_session).process_repository(
        repository, force_reprocess=True, incremental=incremental
    )
    db_session.refresh(repository)


def entity_rows(db_session, repository_id):
    rows = db_session.query(CodeEntity, CodeFile.file_path).join(CodeFile).filter(
        CodeEntity.repository_id == repository_id
    )
    return sorted((path, *(getattr(e, name) for name in _ENTITY_COPY)) for e, path in rows)


async def test_unchanged_files_are_copied_without_parsing_or_new_records(
    db_session, repository, github, algolia_index, parsed
):
    github.files = [github_file("pkg/a.py", MODULE_A), github_file("pkg/b.py", MODULE_B)]
    github.commit_sha = "c1"
    await run(db_session, repository)
    records, rows = dict(algolia_index.records), entity_rows(db_session, repository.id)
    saves = len(algolia_index.save_batch_sizes)
    parsed.clear()

    github.commit_sha = "c2"
    await run(db_session, repository, incremental=True)

    assert (repository.status, repository.error_message, repository.commit_sha) == ("completed", None, "c2")
    assert parsed == []
    # Same records, nothing saved, and the copied rows match the old ones column for column
    assert algolia_index.records == records
    assert len(algolia_index.save_batch_sizes) == saves
    assert entity_rows(db_session, repository.id) == rows
    assert db_session.query(CodeFile).filter_by(repository_id=repository.id).count() == 2


async def test_changed_and_removed_files_swap_only_their_records(
    db_session, repository, github, algolia_index, parsed
):
    a = github_file("pkg/a.py", MODULE_A)
    github.files = [a, github_file("pkg/b.py", MODULE_B), github_file(QUOTED, "def zeta():\n    pass\n")]
    await run(db_session, repository)
    a_records = {k: r for k, r in algolia_index.records.items() if r["file_path"] == "pkg/a.py"}
    parsed.clear()
    algolia_index.delete_filters.clear()

    github.files = [a, github_file("pkg/b.py", MODULE_B + "\ndef epsilon():\n    pass\n")]
    await run(db_session, repository, incremental=True)

    assert parsed == ["pkg/b.py"]
    by_path = {}
    for record in algolia_index.records.values():
        by_path.setdefault(record["file_path"], set()).add(record["entity_name"])
    assert by_path == {"pkg/a.py": {"import os", "alpha", "Beta", "gamma"}, "pkg/b.py": {"delta", "epsilon"}}
    assert {k: r for k, r in algolia_index.records.items() if r["file_path"] == "pkg/a.py"} == a_records
    new_run = next(r["run_id"] for r in algolia_index.records.values() if r["file_path"] == "pkg/b.py")
    assert algolia_index.delete_filters == [
        f'repository_id={repository.id} AND NOT run_id:"{new_run}" '
        'AND (file_path:"pkg/b.py" OR file_path:"pkg/q\\"uote.py")'
    ]


async def test_an_unchanged_file_that_fails_to_store_loses_its_old_records(
    db_session, repository, github, algolia_index, monkeypatch
):
    github.files = [github_file("pkg/a.py", MODULE_A), github_file("pkg/b.py", MODULE_B)]
    await run(db_session, repository)
    monkeypatch.setattr(repository_service, "DB_BATCH_SIZE", 1)
    real_commit = db_session.commit

    def commit():
        if any(getattr(o, "file_path", None) == "pkg/b.py" for o in db_session.new):
            raise RuntimeError("database is locked")
        real_commit()

    monkeypatch.setattr(db_session, "commit", commit)
    await run(db_session, repository, incremental=True)

    # b.py's rows didn't commit, so its search hits would point at a file that isn't there
    assert {r["file_path"] for r in algolia_index.records.values()} == {"pkg/a.py"}
    assert repository.error_message == "Partially indexed: 1 of 2 files could not be stored"


async def test_a_failed_incremental_run_keeps_the_previous_index(
    db_session, repository, github, algolia_index
):
    github.files = [github_file("pkg/a.py", MODULE_A), github_file("pkg/b.py", MODULE_B)]
    await run(db_session, repository)
    records, rows = dict(algolia_index.records), entity_rows(db_session, repository.id)

    github.files = [github_file("pkg/a.py", MODULE_A), github_file("pkg/b.py", "def changed():\n    pass\n")]
    algolia_index.fail_saves = True
    await run(db_session, repository, incremental=True)

    assert repository.status == "completed"
    assert repository.error_message.startswith("Reprocessing failed")
    assert algolia_index.records == records
    assert entity_rows(db_session, repository.id) == rows


async def test_an_incremental_run_with_no_previous_index_indexes_everything(
    db_session, repository, github, algolia_index, parsed
):
    github.files = [github_file("pkg/a.py", MODULE_A), github_file("pkg/b.py", MODULE_B)]

    await run(db_session, repository, incremental=True)

    assert repository.status == "completed"
    assert sorted(parsed) == ["pkg/a.py", "pkg/b.py"]
    assert len(algolia_index.records) == 5


async def test_an_incremental_run_started_through_the_api_reuses_unchanged_files(
    db_session, repository, github, algolia_index, parsed, job_sessions, async_api, wait_for_job
):
    # The only test of inline mode handing `incremental` from the endpoint to the job: a full run would parse both
    a = github_file("pkg/a.py", MODULE_A)
    github.files = [a, github_file("pkg/b.py", MODULE_B)]
    await run(db_session, repository)
    parsed.clear()
    github.files = [a, github_file("pkg/b.py", MODULE_B + "\ndef epsilon():\n    pass\n")]

    response = await async_api.post(f"/api/v1/repositories/{repository.id}/process", params={"incremental": "true"})
    await wait_for_job(repository.id)

    assert response.status_code == 202
    db_session.refresh(repository)
    assert (repository.status, repository.error_message) == ("completed", None)
    assert parsed == ["pkg/b.py"]
    names = sorted(r["entity_name"] for r in algolia_index.records.values())
    assert names == sorted(["import os", "alpha", "Beta", "gamma", "delta", "epsilon"])


# --- scheduled refresh ---------------------------------------------------------


@pytest.fixture
def refresh(db_session, job_sessions, monkeypatch):
    """Completed repositories, each with a scripted freshness answer; returns the runs started"""
    answers = {
        "moved": {"changed": True},
        "same": {"changed": False},
        "busy": {"changed": True},
        "force-pushed": RepositoryCheckError(422, "Branch 'main' or the indexed commit no longer exists"),
        "rate-limited": RepositoryCheckError(503, "GitHub's API rate limit was reached."),
        "broken": RuntimeError("boom"),
        "after-broken": {"changed": True},
    }
    ids = {}
    for name in answers:
        repo = Repository(name=name, url=f"https://github.com/o/{name}", status="completed", commit_sha="c1")
        db_session.add(repo)
        db_session.commit()
        ids[repo.id] = name

    async def freshness(repository):
        answer = answers[repository.name]
        if isinstance(answer, Exception):
            raise answer
        return answer

    started = []

    def start(repository_id, force_reprocess=False, incremental=False):
        started.append((ids[repository_id], force_reprocess, incremental))

    monkeypatch.setattr(repository_service, "index_freshness", freshness)
    monkeypatch.setattr(repository_service, "start_processing", start)
    monkeypatch.setattr(repository_service, "is_processing", lambda repository_id: ids[repository_id] == "busy")
    return started


async def test_refresh_starts_incremental_runs_for_moved_branches_only(refresh):
    count = await repository_service.refresh_once()

    # A force-push (422) is retried by the run itself; a rate limit or a crash only skips that one
    assert refresh == [
        ("moved", True, True),
        ("force-pushed", True, True),
        ("after-broken", True, True),
    ]
    assert count == 3


async def test_refresh_skips_repositories_that_are_not_completed(db_session, job_sessions, monkeypatch):
    db_session.add(Repository(name="new", url="https://github.com/o/new", status="pending", commit_sha=None))
    db_session.add(Repository(name="failed", url="https://github.com/o/failed", status="failed", commit_sha="c1"))
    db_session.commit()

    async def never(repository):
        raise AssertionError("not asked")

    monkeypatch.setattr(repository_service, "index_freshness", never)
    assert await repository_service.refresh_once() == 0


async def test_refresh_loop_survives_a_failed_tick(monkeypatch):
    ticks = []

    async def tick():
        ticks.append(1)
        if len(ticks) == 1:
            raise RuntimeError("database is locked")
        if len(ticks) == 3:
            raise asyncio.CancelledError
        return 1

    monkeypatch.setattr(repository_service, "refresh_once", tick)
    with pytest.raises(asyncio.CancelledError):
        await repository_service.refresh_loop(0.0001)  # about 6 ms
    assert len(ticks) == 3
