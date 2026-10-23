"""
Shared fixtures for the ingestion pipeline tests.

Settings are pinned before any app module is imported. load_dotenv() never
overrides variables that are already set, so the real .env keys and the
local codesage.db are never used here.
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DEBUG"] = "false"
os.environ["GITHUB_TOKEN"] = "test-token"
os.environ["ALGOLIA_APP_ID"] = "test-app"
os.environ["ALGOLIA_ADMIN_API_KEY"] = "test-key"

import pytest
from algoliasearch.exceptions import AlgoliaException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  registers every table on Base.metadata
from app.core.database import Base
from app.services import algolia_service as algolia_module
from app.services import github_service as github_module
from app.services.algolia_service import AlgoliaService


@pytest.fixture
def db_session():
    """A fresh in-memory SQLite database per test"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class _CompletedTask:
    def wait(self):
        return self


class FakeAlgoliaIndex:
    """In-memory stand-in for an algoliasearch v3 SearchIndex"""

    def __init__(self):
        self.records = {}
        self.fail_saves = False
        self.fail_deletes = False
        self.waited_deletes = 0
        self.searches = []

    @staticmethod
    def _repository_id(filters: str) -> int:
        # Real Algolia matches nothing for the facet form `repository_id:2` on a
        # numeric value, so only the numeric comparison is accepted here
        field, separator, value = filters.partition("=")
        assert (field, separator) == ("repository_id", "="), f"unsupported filter {filters!r}"
        return int(value)

    def set_settings(self, settings):
        return _CompletedTask()

    def search(self, query, params):
        self.searches.append(params)
        return {"hits": [], "nbHits": 0, "facets": {}}

    def save_objects(self, objects):
        if self.fail_saves:
            raise AlgoliaException("save_objects failed")
        for record in objects:
            self.records[record["objectID"]] = record
        return _CompletedTask()

    def delete_by(self, params):
        if self.fail_deletes:
            raise AlgoliaException("delete_by failed")
        repository_id = self._repository_id(params["filters"])
        self.records = {
            object_id: record
            for object_id, record in self.records.items()
            if record["repository_id"] != repository_id
        }
        index = self

        class _DeleteTask(_CompletedTask):
            def wait(self):
                index.waited_deletes += 1
                return self

        return _DeleteTask()


@pytest.fixture
def algolia_index(monkeypatch):
    """Route every AlgoliaService through one fake index, keeping the real document logic"""
    index = FakeAlgoliaIndex()

    class FakeAlgoliaService(AlgoliaService):
        def __init__(self):
            self.client = object()
            self.index = index
            self.index_name = "test_index"

    monkeypatch.setattr(algolia_module, "AlgoliaService", FakeAlgoliaService)
    return index


class FakeGitHub:
    """Controls what GitHubService.get_repository_files returns in a test"""

    def __init__(self):
        self.files = []
        self.error = None


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()

    class FakeGitHubService:
        async def get_repository_files(self, repo_url):
            if fake.error:
                raise fake.error
            return list(fake.files)

    monkeypatch.setattr(github_module, "GitHubService", FakeGitHubService)
    return fake
