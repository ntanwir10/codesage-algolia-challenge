"""process_repository end to end: honest final status and idempotent reprocessing"""

import pytest

from app.models.code_entity import CodeEntity
from app.models.code_file import CodeFile
from app.models.repository import Repository
from app.services.github_service import GitHubAPIError, GitHubFile
from app.services.repository_service import RepositoryService

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
    assert set(algolia_index.records) == first_ids
    # Each run waited for the delete before indexing again
    assert algolia_index.waited_deletes == 2


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

    assert repository.status == "failed"
    assert stored_counts(db_session, repository.id) == (2, 5)
    assert len(algolia_index.records) == 5


async def test_reprocess_stops_if_old_records_cannot_be_removed(
    db_session, repository, github, algolia_index
):
    github.files = [FILE_A, FILE_B]
    await process(db_session, repository)

    algolia_index.fail_deletes = True
    await process(db_session, repository, force=True)

    assert repository.status == "failed"
    assert "Could not remove previously indexed records" in repository.error_message
    assert stored_counts(db_session, repository.id) == (2, 5)
    assert len(algolia_index.records) == 5


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
