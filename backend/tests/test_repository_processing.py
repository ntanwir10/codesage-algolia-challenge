"""process_repository end to end: honest final status and idempotent reprocessing"""

import asyncio

import pytest

from app.models.code_entity import CodeEntity
from app.models.code_file import CodeFile
from app.models.repository import Repository
from app.services.github_service import GitHubAPIError, GitHubFile
from app.services.repository_service import PREVIOUS_INDEX_NOTE, RepositoryService

MODULE_A = (
    "import os\n"
    "\n"
    "def alpha():\n"
    "    return 1\n"
    "\n"
    "class Beta:\n"
    "    def gamma(self):\n"
    "        pass\n"
)  # import os, alpha, Beta, gamma
MODULE_B = "def delta(x):\n    return x\n"  # delta


def github_file(path, content):
    return GitHubFile(
        path=path,
        content=content,
        size=len(content.encode()),
        language="python",
        filename=path.split("/")[-1],
    )


FILE_A = github_file("pkg/a.py", MODULE_A)
FILE_B = github_file("pkg/b.py", MODULE_B)


@pytest.fixture
def repository(db_session):
    repo = Repository(
        name="octo/demo",
        url="https://github.com/octo/demo",
        status="pending",
        total_files=0,
        processed_files=0,
        total_lines=0,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


async def process(db_session, repository, force=False):
    await RepositoryService(db_session).process_repository(
        repository, force_reprocess=force
    )
    db_session.refresh(repository)
    return repository


def stored_counts(db_session, repository_id):
    files = db_session.query(CodeFile).filter_by(repository_id=repository_id).count()
    entities = (
        db_session.query(CodeEntity).filter_by(repository_id=repository_id).count()
    )
    return files, entities


async def test_successful_run_completes_and_clears_a_stale_error(
    db_session, repository, github, algolia_index
):
    repository.error_message = "RuntimeError: from an earlier failed run"
    db_session.commit()
    github.files = [FILE_A, FILE_B]

    await process(db_session, repository)

    assert repository.status == "completed"
    assert repository.error_message is None
    assert (repository.total_files, repository.processed_files) == (2, 2)
    assert stored_counts(db_session, repository.id) == (2, 5)
    assert len(algolia_index.records) == 5
    names = {r["entity_name"] for r in algolia_index.records.values()}
    assert {"alpha", "Beta", "gamma", "delta"} <= names


@pytest.mark.parametrize("status", [401, 403, 404])
async def test_github_errors_mark_the_run_failed(
    db_session, repository, github, algolia_index, status
):
    github.error = GitHubAPIError(status, f"GitHub request failed ({status})")

    await process(db_session, repository)

    assert repository.status == "failed"
    assert repository.error_message == f"GitHub request failed ({status})"
    assert algolia_index.records == {}


async def test_repository_with_no_code_files_fails(
    db_session, repository, github, algolia_index
):
    github.files = []

    await process(db_session, repository)

    assert repository.status == "failed"
    assert "No supported code files found" in repository.error_message


async def test_run_that_extracts_no_entities_fails(
    db_session, repository, github, algolia_index
):
    github.files = [github_file("notes.py", "\n\n# just a comment\n")]

    await process(db_session, repository)

    assert repository.status == "failed"
    assert "No code entities were indexed from 1 files" in repository.error_message


async def test_run_whose_algolia_writes_fail_is_not_completed(
    db_session, repository, github, algolia_index
):
    github.files = [FILE_A]
    algolia_index.fail_saves = True

    await process(db_session, repository)

    assert repository.status == "failed"
    assert algolia_index.records == {}


async def test_reprocessing_replaces_rows_and_records_instead_of_duplicating(
    db_session, repository, github, algolia_index
):
    github.files = [FILE_A, FILE_B]

    await process(db_session, repository)
    first_ids = set(algolia_index.records)
    await process(db_session, repository, force=True)

    assert repository.status == "completed"
    assert stored_counts(db_session, repository.id) == (2, 5)
    # The new run's records replaced the old run's: none left over, none duplicated
    assert len(algolia_index.records) == 5
    assert set(algolia_index.records).isdisjoint(first_ids)
    assert len({r["run_id"] for r in algolia_index.records.values()}) == 1


async def test_reprocessing_drops_entities_removed_upstream(
    db_session, repository, github, algolia_index
):
    github.files = [FILE_A, FILE_B]
    await process(db_session, repository)

    github.files = [FILE_B]
    await process(db_session, repository, force=True)

    assert stored_counts(db_session, repository.id) == (1, 1)
    assert [r["entity_name"] for r in algolia_index.records.values()] == ["delta"]


async def test_failed_fetch_during_reprocess_keeps_the_existing_index(
    db_session, repository, github, algolia_index
):
    github.files = [FILE_A, FILE_B]
    await process(db_session, repository)

    github.error = GitHubAPIError(404, "GitHub repository or path not found (404)")
    await process(db_session, repository, force=True)

    # Still completed and searchable on the previous run, with the failure noted
    assert repository.status == "completed"
    assert repository.error_message == (
        "Reprocessing failed: GitHub repository or path not found (404)." + PREVIOUS_INDEX_NOTE
    )
    assert (repository.total_files, repository.processed_files) == (2, 2)
    assert stored_counts(db_session, repository.id) == (2, 5)
    assert len(algolia_index.records) == 5


async def test_a_failed_reprocess_started_through_the_api_keeps_the_existing_index(
    db_session, repository, github, algolia_index, job_sessions
):
    """The endpoint and the real job together: the job must still read 'completed' when it starts"""
    import httpx2 as httpx

    from app.core.database import get_db
    from app.main import app
    from app.services import repository_service

    github.files = [FILE_A, FILE_B]
    await process(db_session, repository)
    github.error = GitHubAPIError(404, "GitHub repository or path not found (404)")

    app.dependency_overrides[get_db] = lambda: db_session
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as api:
            response = await api.post(
                f"/api/v1/repositories/{repository.id}/process", params={"force_reprocess": "true"}
            )
        # The job runs on this event loop; let it finish
        for _ in range(500):
            if not repository_service.is_processing(repository.id):
                break
            await asyncio.sleep(0.01)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    db_session.refresh(repository)
    assert repository.status == "completed"
    assert repository.error_message.endswith(PREVIOUS_INDEX_NOTE)
    assert (repository.total_files, repository.processed_files) == (2, 2)


async def test_a_run_whose_old_records_cannot_be_removed_still_completes(
    db_session, repository, github, algolia_index
):
    github.files = [FILE_A, FILE_B]
    await process(db_session, repository)

    algolia_index.fail_deletes = True
    await process(db_session, repository, force=True)

    # The new run is complete, so it is kept; the old records go on the next run
    assert repository.status == "completed"
    assert "previous run's records" in repository.error_message
    assert stored_counts(db_session, repository.id) == (2, 5)
    assert len(algolia_index.records) == 10

    algolia_index.fail_deletes = False
    await process(db_session, repository, force=True)
    assert len(algolia_index.records) == 5


async def test_a_failed_index_keeps_the_previous_one_searchable(
    db_session, repository, github, algolia_index, monkeypatch
):
    github.files = [FILE_A, FILE_B]
    await process(db_session, repository)
    first = dict(algolia_index.records)

    def save_then_reject(self, documents):
        # Some of the new run's records land before Algolia refuses the rest
        algolia_index.save_objects(documents[:2])
        return False

    async def reject(self, documents):
        return save_then_reject(self, documents)

    monkeypatch.setattr("app.services.algolia_service.AlgoliaService.index_documents", reject)
    await process(db_session, repository, force=True)

    assert repository.status == "completed"
    assert repository.error_message.startswith("Reprocessing failed: Algolia rejected the indexing request")
    assert repository.error_message.endswith(PREVIOUS_INDEX_NOTE)
    assert len(repository.error_message) <= 500
    # The failed run's rows and records are gone; the previous run's are untouched
    assert stored_counts(db_session, repository.id) == (2, 5)
    assert algolia_index.records == first


async def test_a_failed_first_run_leaves_nothing_behind(
    db_session, repository, github, algolia_index, monkeypatch
):
    github.files = [FILE_A, FILE_B]

    async def reject(self, documents):
        return False

    monkeypatch.setattr("app.services.algolia_service.AlgoliaService.index_documents", reject)
    await process(db_session, repository)

    assert repository.status == "failed"
    assert repository.error_message == "Algolia rejected the indexing request"
    assert stored_counts(db_session, repository.id) == (0, 0)


async def test_entities_from_other_repositories_are_untouched(
    db_session, repository, github, algolia_index
):
    other = Repository(name="octo/other", url="https://github.com/octo/other")
    db_session.add(other)
    db_session.commit()
    github.files = [FILE_A]
    await process(db_session, other)
    github.files = [FILE_B]

    await process(db_session, repository)
    await process(db_session, repository, force=True)

    assert stored_counts(db_session, other.id) == (1, 4)
    assert sum(r["repository_id"] == other.id for r in algolia_index.records.values()) == 4
