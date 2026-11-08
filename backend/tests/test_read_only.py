"""READ_ONLY=true: a public, keyless server that can be searched but never changed"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import Settings, get_settings, validate_runtime_settings
from app.core.database import get_db
from app.core.migrations import database_is_current, upgrade_database
from app.main import app
from app.models.repository import Repository

DEMO_HOST = "codesage-demo.example.com"


@pytest.fixture
def read_only(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "read_only", True)
    monkeypatch.setattr(settings, "codesage_api_key", None)
    monkeypatch.setattr(settings, "allowed_hosts", DEMO_HOST)
    return settings


@pytest.fixture
def public_client(db_session):
    """A visitor from the internet reaching the demo by its public name"""
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app, base_url=f"https://{DEMO_HOST}", client=("203.0.113.9", 40000))
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def repo(db_session):
    repo = Repository(name="octo/demo", url="https://github.com/octo/demo", status="completed")
    db_session.add(repo)
    db_session.commit()
    return repo


def test_a_keyless_public_server_starts_only_when_read_only():
    public = {"mcp_server_host": "0.0.0.0", "codesage_api_key": None}
    with pytest.raises(RuntimeError):
        validate_runtime_settings(Settings(**public))
    validate_runtime_settings(Settings(**public, read_only=True))


def test_reads_reach_a_visitor_and_writes_are_refused(read_only, public_client, repo):
    # Without READ_ONLY this visitor gets 403 for everything (no key, not loopback)
    assert public_client.get("/api/v1/repositories/").status_code == 200
    writes = [
        public_client.post("/api/v1/repositories/", json={"url": "https://github.com/a/b"}),
        public_client.put(f"/api/v1/repositories/{repo.id}", json={"description": "x"}),
        public_client.delete(f"/api/v1/repositories/{repo.id}"),
        public_client.post(f"/api/v1/repositories/{repo.id}/process"),
        public_client.post("/api/v1/webhooks/github", content=b"{}"),
    ]
    assert [r.status_code for r in writes] == [403] * 5
    assert all("read-only" in r.json()["detail"] for r in writes)


def test_another_host_is_still_refused(read_only, db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        other = TestClient(app, base_url="https://attacker.example", client=("203.0.113.9", 40000))
        assert other.get("/api/v1/repositories/").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_the_tool_that_writes_is_neither_listed_nor_run(read_only, public_client):
    caps = public_client.get("/api/v1/ai/mcp/capabilities").json()
    listed = [t["name"] for t in public_client.get("/api/v1/ai/mcp/tools").json()["tools"]]
    assert caps["read_only"] is True
    assert "add_repository" not in caps["tools"] and "add_repository" not in listed
    assert len(listed) == 7

    call = public_client.post(
        "/api/v1/ai/mcp/tools/call",
        json={"tool_name": "add_repository", "arguments": {"url": "https://github.com/a/b"}},
    ).json()
    assert call["is_error"] is True and "read-only" in call["error"]


def test_the_schema_check_reads_without_migrating(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    assert database_is_current(engine) is False
    upgrade_database(engine)
    assert database_is_current(engine) is True
