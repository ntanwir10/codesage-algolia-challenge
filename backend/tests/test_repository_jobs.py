"""Background jobs, batching, statistics and the process/delete endpoints"""

import asyncio

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
    assert algolia_index.save_batch_sizes == [2, 2, 2]


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


async def test_delete_keeps_the_row_when_algolia_cannot_delete(db_session, algolia_index):
    repo = make_repository(db_session, status="completed")
    algolia_index.fail_deletes = True

    assert await RepositoryService(db_session).delete_repository(repo) is False
    assert db_session.get(Repository, repo.id) is not None


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
