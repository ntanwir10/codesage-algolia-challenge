"""Background jobs, batching, statistics and the process/delete endpoints"""

import asyncio
import threading
import weakref

import pytest

from app.api.v1.endpoints import repositories as repositories_endpoint
from app.models.repository import Repository
from app.services import algolia_service as algolia_module
from app.services import repository_service
from app.services.github_service import GitHubFile
from app.services.repository_service import (
    RepositoryBusyError,
    RepositoryService,
    recover_interrupted_jobs,
    start_processing,
)

MODULE = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"


def github_file(path, content, language="python"):
    return GitHubFile(
        path=path,
        content=content,
        size=len(content.encode()),
        language=language,
        filename=path.split("/")[-1],
    )


def make_repository(db_session, **fields):
    repo = Repository(
        name=fields.pop("name", "octo/demo"),
        url=fields.pop("url", "https://github.com/octo/demo"),
        total_files=0,
        processed_files=0,
        total_lines=0,
        **fields,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


async def test_a_repository_never_runs_two_jobs_at_once(monkeypatch):
    release = asyncio.Event()

    async def slow_job(repository_id, force_reprocess):
        await release.wait()

    monkeypatch.setattr(repository_service, "_run_job", slow_job)

    first = start_processing(7)
    with pytest.raises(RepositoryBusyError):
        start_processing(7)

    release.set()
    await first
    # Once the job finishes the repository can be processed again
    await start_processing(7)


async def test_background_job_processes_with_its_own_session(
    db_session, job_sessions, github, algolia_index
):
    repo = make_repository(db_session, status="pending")
    github.files = [github_file("pkg/a.py", MODULE)]

    await start_processing(repo.id)

    db_session.refresh(repo)
    assert repo.status == "completed"
    assert repo.processed_at is not None
    assert len(algolia_index.records) == 2


async def test_runs_beyond_the_limit_wait_for_a_free_slot(db_session, job_sessions, monkeypatch):
    monkeypatch.setattr(repository_service, "MAX_CONCURRENT_RUNS", 1)
    monkeypatch.setattr(repository_service, "_run_slots", weakref.WeakKeyDictionary())
    started, release = [], asyncio.Event()

    async def blocking_files(self, repository):
        started.append(repository.id)
        await release.wait()

    monkeypatch.setattr(RepositoryService, "process_repository_files", blocking_files)
    a = make_repository(db_session, status="pending", url="https://github.com/octo/a")
    b = make_repository(db_session, status="pending", url="https://github.com/octo/b")

    first, second = start_processing(a.id), start_processing(b.id)
    await asyncio.sleep(0.05)
    assert started == [a.id]
    db_session.refresh(b)
    assert b.status == "processing"  # queued runs already show as processing

    release.set()
    await asyncio.gather(first, second)
    assert started == [a.id, b.id]


def test_run_slots_work_on_every_event_loop():
    # One module-level semaphore raised "bound to a different event loop" on the second run
    async def contend():
        async def hold():
            async with repository_service._run_slot():
                await asyncio.sleep(0.01)

        # One more holder than there are slots, so someone has to wait
        await asyncio.gather(*(hold() for _ in range(repository_service.MAX_CONCURRENT_RUNS + 1)))

    asyncio.run(contend())
    asyncio.run(contend())


async def test_a_cancelled_delete_keeps_the_slot_until_its_row_clear_finishes(
    db_session, algolia_index, monkeypatch
):
    repo = make_repository(db_session, status="completed")
    in_thread, release = threading.Event(), threading.Event()
    real_commit = db_session.commit

    def commit():
        if threading.current_thread() is not threading.main_thread():
            in_thread.set()
            release.wait(5)
        real_commit()

    monkeypatch.setattr(db_session, "commit", commit)
    deleting = asyncio.create_task(RepositoryService(db_session).delete_repository(repo))
    await asyncio.to_thread(in_thread.wait, 5)

    deleting.cancel()
    await asyncio.sleep(0.05)
    # The thread is still committing, so a new run must not be able to start yet
    assert repository_service.is_processing(repo.id)

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await deleting
    assert not repository_service.is_processing(repo.id)


async def test_a_crashed_job_does_not_stay_processing(db_session, job_sessions, monkeypatch):
    repo = make_repository(db_session, status="pending")

    async def crash(self, repository, force_reprocess=False):
        # e.g. "database is locked" while recording the failure itself
        repository.status = "processing"
        self.db.commit()
        raise RuntimeError("database is locked")

    monkeypatch.setattr(RepositoryService, "process_repository", crash)
    await start_processing(repo.id)

    db_session.refresh(repo)
    assert repo.status == "failed"
    assert "reprocess" in repo.error_message


async def test_database_errors_do_not_leak_sql_or_file_contents(
    db_session, github, algolia_index, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    async def broken_clear(self, repository_id, algolia_service):
        raise OperationalError("INSERT INTO code_files VALUES (?)", ("SECRET FILE BODY",), Exception())

    monkeypatch.setattr(RepositoryService, "_clear_repository_data", broken_clear)
    repo = make_repository(db_session, status="pending")
    github.files = [github_file("a.py", MODULE)]

    await RepositoryService(db_session).process_repository(repo)

    assert repo.status == "failed"
    assert repo.error_message == "Database error while storing the repository"


def test_restart_fails_repositories_left_mid_run(db_session):
    pending = make_repository(db_session, name="a", url="https://github.com/o/a", status="pending")
    running = make_repository(db_session, name="b", url="https://github.com/o/b", status="processing")
    done = make_repository(db_session, name="c", url="https://github.com/o/c", status="completed")

    assert recover_interrupted_jobs(db_session) == 2

    for repo in (pending, running, done):
        db_session.refresh(repo)
    assert (pending.status, running.status, done.status) == ("failed", "failed", "completed")
    assert "interrupted by a server restart" in pending.error_message
    assert done.error_message is None


@pytest.mark.parametrize("branch", ["develop", None])
async def test_branch_is_passed_to_github(db_session, github, algolia_index, branch):
    repo = make_repository(db_session, status="pending", branch=branch)
    github.files = [github_file("a.py", MODULE)]

    await RepositoryService(db_session).process_repository(repo)

    assert github.calls == [("https://github.com/octo/demo", branch)]


async def test_records_are_indexed_in_batches(db_session, github, algolia_index, monkeypatch):
    monkeypatch.setattr(algolia_module, "INDEX_BATCH_SIZE", 2)
    repo = make_repository(db_session, status="pending")
    github.files = [github_file("a.py", MODULE), github_file("b.py", MODULE), github_file("c.py", MODULE)]

    await RepositoryService(db_session).process_repository(repo)

    assert repo.status == "completed"
    assert repo.error_message is None
    assert algolia_index.save_batch_sizes == [2, 2, 2]


async def test_a_failed_batch_completes_but_says_what_is_missing(
    db_session, github, algolia_index, monkeypatch
):
    monkeypatch.setattr(repository_service, "DB_BATCH_SIZE", 1)
    real_commit = db_session.commit

    def commit():
        if any(getattr(o, "file_path", None) == "b.py" for o in db_session.new):
            raise RuntimeError("database is locked")
        real_commit()

    monkeypatch.setattr(db_session, "commit", commit)
    repo = make_repository(db_session, status="pending")
    github.files = [github_file("a.py", MODULE), github_file("b.py", MODULE)]

    await RepositoryService(db_session).process_repository(repo)

    assert repo.status == "completed"
    assert repo.error_message == "Partially indexed: 1 of 2 files could not be stored"
    assert {r["file_path"] for r in algolia_index.records.values()} == {"a.py"}


async def test_a_file_that_fails_to_parse_is_stored_and_reported(
    db_session, github, algolia_index, monkeypatch
):
    from app.models.code_file import CodeFile
    from app.services.code_parser import CodeParser

    real_parse = CodeParser.parse

    def parse(self, file_path, content, language):
        if file_path == "b.py":
            raise RuntimeError("tree-sitter blew up")
        return real_parse(self, file_path, content, language)

    monkeypatch.setattr(CodeParser, "parse", parse)
    repo = make_repository(db_session, status="pending")
    github.files = [github_file("a.py", MODULE), github_file("b.py", MODULE)]

    await RepositoryService(db_session).process_repository(repo)

    assert repo.status == "completed"
    assert repo.error_message == "Partially indexed: 1 files could not be parsed"
    stored = {f.file_path for f in db_session.query(CodeFile).filter_by(repository_id=repo.id)}
    assert stored == {"a.py", "b.py"}


async def test_a_reprocess_starts_progress_from_zero(db_session, github, algolia_index, monkeypatch):
    repo = make_repository(db_session, status="completed")
    repo.processed_files = repo.total_files = 10
    db_session.commit()
    seen = []

    async def record_progress(self, repository):
        seen.append(repository.processed_files)

    monkeypatch.setattr(RepositoryService, "process_repository_files", record_progress)
    await RepositoryService(db_session).process_repository(repo, force_reprocess=True)

    assert seen == [0]  # not the previous run's 10/10, which reads as 100%


async def test_files_over_the_limit_are_reported(db_session, github, algolia_index):
    repo = make_repository(db_session, status="pending")
    github.files = [github_file("a.py", MODULE)]
    github.skipped_files = 5

    await RepositoryService(db_session).process_repository(repo)

    assert repo.status == "completed"
    assert repo.error_message == "Partially indexed: 5 files over the 1000-file or 100 MB limit were skipped"


async def test_a_truncated_listing_is_reported(db_session, github, algolia_index):
    repo = make_repository(db_session, status="pending")
    github.files = [github_file("a.py", MODULE)]
    github.listing_truncated = True

    await RepositoryService(db_session).process_repository(repo)

    assert repo.status == "completed"
    assert "too large to list in full" in repo.error_message


async def test_record_content_carries_the_entity_body(db_session, github, algolia_index):
    repo = make_repository(db_session, status="pending")
    github.files = [github_file("a.py", MODULE)]

    await RepositoryService(db_session).process_repository(repo)

    alpha = next(r for r in algolia_index.records.values() if r["entity_name"] == "alpha")
    assert alpha["signature"] == "def alpha():"
    assert "return 1" in alpha["content"]
    assert alpha["rank_weight"] == 2
    assert "imports" not in alpha


async def test_statistics_count_stored_entities(db_session, github, algolia_index):
    repo = make_repository(db_session, status="pending")
    github.files = [
        github_file("a.py", MODULE),
        github_file("README.md", "# Demo\n\nHow to use it.\n", language="markdown"),
    ]
    await RepositoryService(db_session).process_repository(repo)

    stats = await RepositoryService(db_session).get_repository_statistics(repo)

    assert stats["total_entities"] == 3
    assert stats["entities_by_type"] == {"function": 2, "doc_section": 1}
    assert stats["files_by_language"] == {"python": 1, "markdown": 1}
    # Markdown doesn't count as the repository's programming language
    assert stats["language"] == "python"


def test_framework_comes_from_manifests_and_imports():
    package_json = github_file(
        "package.json", '{"dependencies": {"react": "^19.0.0"}}', language="json"
    )
    fastapi_app = github_file("app.py", "from fastapi import FastAPI\n")

    assert RepositoryService._detect_framework([package_json]) == "react"
    assert RepositoryService._detect_framework([fastapi_app]) == "fastapi"
    assert RepositoryService._detect_framework([github_file("x.py", "print(1)\n")]) is None


def test_framework_skips_manifests_that_are_not_objects():
    # Fixtures deep in a repo can hold any JSON; they used to fail an already-indexed run
    odd = [
        github_file(f"fixtures/{i}/package.json", body, language="json")
        for i, body in enumerate(['["react"]', "null", '"react"', '{"dependencies": ["react"]}'])
    ]
    real = github_file("package.json", '{"devDependencies": {"vue": "^3"}}', language="json")

    assert RepositoryService._detect_framework(odd) is None
    assert RepositoryService._detect_framework([*odd, real]) == "vue"


async def test_delete_keeps_the_row_when_algolia_cannot_delete(db_session, algolia_index):
    repo = make_repository(db_session, status="completed")
    algolia_index.fail_deletes = True

    assert await RepositoryService(db_session).delete_repository(repo) is False
    assert db_session.get(Repository, repo.id) is not None


async def test_no_run_can_start_while_a_delete_is_in_flight(db_session, monkeypatch):
    repo = make_repository(db_session, status="completed")
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_delete(self, repository_id, wait=False):
        entered.set()
        await release.wait()
        return True

    monkeypatch.setattr(algolia_module.AlgoliaService, "delete_repository_index", slow_delete)
    deleting = asyncio.create_task(RepositoryService(db_session).delete_repository(repo))
    await entered.wait()

    with pytest.raises(RepositoryBusyError):
        start_processing(repo.id, force_reprocess=True)
    with pytest.raises(RepositoryBusyError):
        await RepositoryService(db_session).delete_repository(repo)

    release.set()
    assert await deleting is True
    assert not repository_service.is_processing(repo.id)


class TestEndpoints:
    @pytest.fixture
    def scheduled(self, monkeypatch):
        calls = []

        def fake_start(repository_id, force_reprocess=False):
            calls.append((repository_id, force_reprocess))

        monkeypatch.setattr(repositories_endpoint, "start_processing", fake_start)
        return calls

    def test_process_schedules_a_job_and_returns_202(self, client, db_session, scheduled):
        repo = make_repository(db_session, status="failed")

        response = client.post(f"/api/v1/repositories/{repo.id}/process")

        assert response.status_code == 202
        assert scheduled == [(repo.id, False)]

    def test_completed_repository_needs_force(self, client, db_session, scheduled):
        repo = make_repository(db_session, status="completed")

        assert client.post(f"/api/v1/repositories/{repo.id}/process").status_code == 409
        forced = client.post(
            f"/api/v1/repositories/{repo.id}/process", params={"force_reprocess": "true"}
        )
        assert forced.status_code == 202
        assert scheduled == [(repo.id, True)]

    def test_process_while_running_returns_409(self, client, db_session, monkeypatch):
        repo = make_repository(db_session, status="processing")

        def busy(repository_id, force_reprocess=False):
            raise RepositoryBusyError("already being processed")

        monkeypatch.setattr(repositories_endpoint, "start_processing", busy)

        assert client.post(f"/api/v1/repositories/{repo.id}/process").status_code == 409

    def test_delete_returns_502_and_keeps_the_row_when_algolia_fails(
        self, client, db_session, algolia_index
    ):
        repo = make_repository(db_session, status="completed")
        algolia_index.fail_deletes = True

        response = client.delete(f"/api/v1/repositories/{repo.id}")

        assert response.status_code == 502
        assert db_session.get(Repository, repo.id) is not None

    def test_delete_removes_the_row_and_its_records(self, client, db_session, algolia_index):
        repo = make_repository(db_session, status="completed")
        algolia_index.records = {"r": {"objectID": "r", "repository_id": repo.id}}

        assert client.delete(f"/api/v1/repositories/{repo.id}").status_code == 200
        assert algolia_index.records == {}
        db_session.expire_all()
        assert db_session.get(Repository, repo.id) is None

    def test_upload_route_is_gone(self, client, db_session):
        repo = make_repository(db_session, status="completed")
        assert client.post(f"/api/v1/repositories/{repo.id}/upload").status_code in (404, 405)


async def test_failed_run_reports_its_reason_through_the_api(client, db_session, github, algolia_index):
    from app.services.github_service import GitHubAPIError

    repo = make_repository(db_session, status="pending")
    github.error = GitHubAPIError(404, "GitHub repository or path not found (404): octo/demo")
    await RepositoryService(db_session).process_repository(repo)

    body = client.get(f"/api/v1/repositories/{repo.id}").json()
    assert body["status"] == "failed"
    assert body["error_message"] == "GitHubAPIError: GitHub repository or path not found (404): octo/demo"
