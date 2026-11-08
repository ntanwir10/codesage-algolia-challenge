"""How far an index is behind its branch: GitHub's compare API, git ls-remote, and the cache"""

import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.models.repository import Repository
from app.services import git_source, repository_service
from app.services.github_service import GitHubService, RepositoryCheckError

URL = "https://github.com/octo/demo"
GITLAB = "https://gitlab.com/group/repo"
SHA = "a" * 40
API = "/api/v1/repositories"


@pytest.fixture
async def github_api():
    """Fake GitHub API: `repo` and `compare` are (status, headers, body) answers"""
    state = {
        "repo": (200, {}, {"default_branch": "main"}),
        "compare": (200, {}, {"status": "identical", "ahead_by": 0, "behind_by": 0}),
        "requests": [],
    }

    def answer(name):
        async def handler(request):
            state["requests"].append(request.raw_path)
            status, headers, body = state[name]
            return web.json_response(body, status=status, headers=headers)

        return handler

    app = web.Application()
    app.router.add_get("/repos/octo/demo", answer("repo"))
    app.router.add_get("/repos/octo/demo/compare/{spec:.*}", answer("compare"))
    server = TestServer(app)
    await server.start_server()
    state["base"] = str(server.make_url("")).rstrip("/")
    try:
        yield state
    finally:
        await server.close()


async def behind(api, branch=None):
    service = GitHubService()
    service.base_url = api["base"]
    return await service.commits_behind(URL, SHA, branch)


# --- GitHub: one compare call ------------------------------------------------


async def test_no_branch_reads_the_default_one_then_compares(github_api):
    assert await behind(github_api) == ("main", 0, False)
    assert github_api["requests"] == ["/repos/octo/demo", f"/repos/octo/demo/compare/{SHA}...main"]


async def test_a_set_branch_is_compared_directly(github_api):
    github_api["compare"] = (200, {}, {"status": "ahead", "ahead_by": 3, "behind_by": 0})

    assert await behind(github_api, "feat/x") == ("feat/x", 3, True)
    assert github_api["requests"] == [f"/repos/octo/demo/compare/{SHA}...feat/x"]


@pytest.mark.parametrize("status", ["behind", "diverged"])
async def test_a_reset_or_force_pushed_branch_counts_as_changed(github_api, status):
    github_api["compare"] = (200, {}, {"status": status, "ahead_by": 0, "behind_by": 2})

    assert await behind(github_api, "main") == ("main", 0, True)


async def test_a_gone_commit_or_branch_is_a_422(github_api):
    github_api["compare"] = (404, {}, {"message": "Not Found"})

    with pytest.raises(RepositoryCheckError, match="no longer exists") as caught:
        await behind(github_api, "main")
    assert caught.value.status_code == 422


async def test_a_rate_limit_is_a_503_with_retry_after(github_api):
    reset = str(int(time.time()) + 120)
    github_api["compare"] = (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset}, {})

    with pytest.raises(RepositoryCheckError) as caught:
        await behind(github_api, "main")
    assert caught.value.status_code == 503
    assert "Retry-After" in caught.value.headers


# --- other hosts: git ls-remote -------------------------------------------------


@pytest.fixture
def ls_remote(monkeypatch):
    """Answer `git ls-remote` with `ls_remote.stdout`; record the arguments"""
    calls = []

    async def fake_git(args, timeout, host=None):
        calls.append(args)
        return 0, ls_remote.stdout, ""

    async def public(host):
        return {"140.82.112.3"}

    monkeypatch.setattr(git_source, "_git", fake_git)
    monkeypatch.setattr(git_source, "_resolve", public)
    ls_remote.calls = calls
    ls_remote.stdout = ""
    return ls_remote


async def test_no_branch_follows_head_to_the_default_branch(ls_remote):
    ls_remote.stdout = f"ref: refs/heads/trunk\tHEAD\n{SHA}\tHEAD\n"

    assert await git_source.remote_head(GITLAB) == ("trunk", SHA)
    [args] = ls_remote.calls
    assert args[args.index("ls-remote") :] == ["ls-remote", "--symref", "--", GITLAB, "HEAD"]


async def test_only_the_exact_branch_ref_counts(ls_remote):
    # Patterns match by suffix, so refs/heads/dev also lists refs/heads/feature/dev
    ls_remote.stdout = f"{'1' * 40}\trefs/heads/feature/dev\n{'2' * 40}\trefs/heads/dev\n"

    assert await git_source.remote_head(GITLAB, "dev") == ("dev", "2" * 40)


async def test_a_missing_branch_is_a_422(ls_remote):
    ls_remote.stdout = f"{'1' * 40}\trefs/heads/feature/dev\n"

    with pytest.raises(RepositoryCheckError, match="Branch 'dev' does not exist") as caught:
        await git_source.remote_head(GITLAB, "dev")
    assert caught.value.status_code == 422


# --- the endpoint and its cache -------------------------------------------------


def add(db_session, url=URL, commit_sha=SHA, branch=None) -> Repository:
    repository = Repository(name="r", url=url, status="completed", commit_sha=commit_sha, branch=branch)
    db_session.add(repository)
    db_session.commit()
    return repository


@pytest.fixture
def compares(monkeypatch):
    """GitHubService.commits_behind answering 4 commits on main; records its calls"""
    calls = []

    async def fake(self, url, sha, branch=None):
        calls.append((url, sha, branch))
        return "main", 4, True

    monkeypatch.setattr(GitHubService, "commits_behind", fake)
    return calls


def test_github_reports_the_count_and_asks_once_per_commit(client, db_session, compares):
    repository = add(db_session)

    first = client.get(f"{API}/{repository.id}/freshness")
    again = client.get(f"{API}/{repository.id}/freshness")

    assert first.status_code == 200
    assert {k: first.json()[k] for k in ("branch", "commits_behind", "changed")} == {
        "branch": "main",
        "commits_behind": 4,
        "changed": True,
    }
    assert again.json() == first.json()
    assert compares == [(URL, SHA, None)]

    # A reprocess records a new commit, which is a new question
    repository.commit_sha = "b" * 40
    db_session.commit()
    client.get(f"{API}/{repository.id}/freshness")
    assert compares[-1] == (URL, "b" * 40, None)


def test_the_cache_expires(client, db_session, compares, monkeypatch):
    repository = add(db_session)
    client.get(f"{API}/{repository.id}/freshness")
    monkeypatch.setattr(repository_service, "FRESHNESS_TTL", 0)

    client.get(f"{API}/{repository.id}/freshness")

    assert len(compares) == 2


@pytest.mark.parametrize(("head", "changed"), [(SHA, False), ("b" * 40, True)])
def test_other_hosts_say_only_whether_the_branch_moved(client, db_session, monkeypatch, head, changed):
    async def remote_head(url, branch=None):
        return "main", head

    monkeypatch.setattr(git_source, "remote_head", remote_head)
    repository = add(db_session, url=GITLAB)

    body = client.get(f"{API}/{repository.id}/freshness").json()

    assert (body["branch"], body["commits_behind"], body["changed"]) == ("main", None, changed)


def test_a_repository_without_an_indexed_commit_is_a_409(client, db_session, compares):
    repository = add(db_session, commit_sha=None)

    assert client.get(f"{API}/{repository.id}/freshness").status_code == 409
    assert client.get(f"{API}/999/freshness").status_code == 404
    assert compares == []


def test_a_refused_check_keeps_its_status_and_headers(client, db_session, monkeypatch):
    async def limited(self, url, sha, branch=None):
        raise RepositoryCheckError(503, "GitHub's API rate limit was reached.", {"Retry-After": "90"})

    monkeypatch.setattr(GitHubService, "commits_behind", limited)
    repository = add(db_session)

    response = client.get(f"{API}/{repository.id}/freshness")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "90"
