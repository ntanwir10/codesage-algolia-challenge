import hashlib
import hmac
import json

import pytest

from app.api.v1.endpoints import webhooks
from app.core.config import get_settings
from app.models.repository import Repository
from app.services.repository_service import RepositoryBusyError

SECRET = "webhook-secret"
URL = "/api/v1/webhooks/github"


def push(ref="refs/heads/main", html_url="https://github.com/Octo/Demo", after="c2", default_branch="main"):
    return {"ref": ref, "after": after, "repository": {"html_url": html_url, "default_branch": default_branch}}


def send(client, payload, event="push", secret=SECRET, signature=None):
    body = json.dumps(payload).encode()
    if signature is None:
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        URL,
        content=body,
        headers={"X-GitHub-Event": event, "X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )


@pytest.fixture
def started(monkeypatch):
    monkeypatch.setattr(get_settings(), "github_webhook_secret", SECRET)
    monkeypatch.setattr(get_settings(), "codesage_api_key", None)
    calls = []

    def start(repository_id, force_reprocess=False, incremental=False):
        calls.append((repository_id, force_reprocess, incremental))

    monkeypatch.setattr(webhooks, "start_processing", start)
    return calls


def add(db, name, url="https://github.com/octo/demo", branch=None, status="completed", commit_sha="c1"):
    repo = Repository(name=name, url=url, branch=branch, status=status, commit_sha=commit_sha)
    db.add(repo)
    db.commit()
    return repo.id


def test_a_push_starts_an_incremental_run_for_the_matching_repository(client, db_session, started):
    demo = add(db_session, "demo")  # no branch: follows the default branch; the payload's case differs
    add(db_session, "other", url="https://github.com/octo/other")
    add(db_session, "gitlab", url="https://gitlab.com/octo/demo2")
    add(db_session, "failed", url="https://github.com/octo/failed", status="failed")

    response = send(client, push())

    assert response.status_code == 202
    assert response.json() == {"started": [demo], "busy": []}
    assert started == [(demo, True, True)]


def test_only_a_push_to_the_indexed_branch_counts(client, db_session, started):
    dev = add(db_session, "dev", branch="dev")
    assert send(client, push(ref="refs/heads/main")).json()["started"] == []
    assert "not a branch" in send(client, push(ref="refs/tags/v1")).json()["detail"]
    assert started == []
    assert send(client, push(ref="refs/heads/dev")).json()["started"] == [dev]


def test_a_push_of_the_indexed_commit_starts_nothing(client, db_session, started):
    # A redelivery after the run finished
    add(db_session, "demo", commit_sha="c2")
    assert send(client, push(after="c2")).json()["started"] == []


def test_a_repository_already_running_is_reported_busy(client, db_session, started, monkeypatch):
    repo = add(db_session, "default")

    def busy(*args, **kwargs):
        raise RepositoryBusyError("busy")

    monkeypatch.setattr(webhooks, "start_processing", busy)
    assert send(client, push()).json() == {"started": [], "busy": [repo]}


@pytest.mark.parametrize(
    "signature", ["", "sha256=" + "0" * 64, "sha1=abc", "sha256=" + hmac.new(b"wrong", b"{}", hashlib.sha256).hexdigest()]
)
def test_a_missing_or_wrong_signature_is_refused(client, db_session, started, signature):
    add(db_session, "default")
    response = send(client, push(), signature=signature)
    assert response.status_code == 401
    assert started == []


def test_the_signature_must_cover_the_body_sent(client, db_session, started):
    add(db_session, "default")
    signature = "sha256=" + hmac.new(SECRET.encode(), b"{}", hashlib.sha256).hexdigest()
    assert send(client, push(), signature=signature).status_code == 401


def test_off_without_a_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "github_webhook_secret", None)
    assert send(client, push()).status_code == 404


def test_ping_and_other_events_are_acknowledged_and_ignored(client, db_session, started):
    add(db_session, "default")
    response = send(client, {"zen": "Keep it simple."}, event="ping")
    assert response.status_code == 202 and response.json()["started"] == []
    assert send(client, push(), event="issues").json()["started"] == []
    assert started == []


@pytest.mark.parametrize("payload", [{}, {"ref": "refs/heads/main"}, {"ref": "refs/heads/main", "repository": {}}, []])
def test_a_signed_body_that_is_not_a_push_payload_is_400(client, started, payload):
    assert send(client, payload).status_code == 400


def test_works_with_an_api_key_configured_but_not_sent(client, db_session, started, monkeypatch):
    # GitHub can't send X-API-Key; the signature is the endpoint's authentication
    monkeypatch.setattr(get_settings(), "codesage_api_key", "s3cret")
    monkeypatch.setattr(get_settings(), "allowed_hosts", "localhost")
    repo = add(db_session, "default")
    response = send(client, push())
    assert response.status_code == 202
    assert response.json()["started"] == [repo]
