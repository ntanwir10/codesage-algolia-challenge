"""Creating a repository checks GitHub first; errors name the field and the cause"""

import asyncio
import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.models.repository import Repository
from app.services import algolia_service as algolia_module
from app.services import repository_service
from app.services.github_service import GitHubService, RepositoryCheckError

URL = "https://github.com/octo/demo"
API = "/api/v1/repositories"
real_check = pytest.mark.real_github_check


@pytest.fixture
async def github_api():
    """Fake GitHub API: `repo` and `branch` are (status, headers, body) answers"""
    state = {
        "repo": (200, {}, {"default_branch": "main", "size": 10}),
        "branch": (200, {}, {"name": "main"}),
        "requests": [],
        "delay": 0.0,
    }

    def answer(name):
        async def handler(request):
            state["requests"].append(request.raw_path)
            if state["delay"]:
                await asyncio.sleep(state["delay"])
            status, headers, body = state[name]
            return web.json_response(body, status=status, headers=headers)

        return handler

    app = web.Application()
    app.router.add_get("/repos/octo/demo", answer("repo"))
    app.router.add_get("/repos/octo/demo/branches/{branch:.*}", answer("branch"))
    server = TestServer(app)
    await server.start_server()
    state["base"] = str(server.make_url("")).rstrip("/")
    try:
        yield state
    finally:
        await server.close()


async def check(api, url=URL, branch=None) -> RepositoryCheckError | None:
    service = GitHubService()
    service.base_url = api["base"]
    try:
        await service.check_repository(url, branch)
    except RepositoryCheckError as e:
        return e
    return None


@real_check
async def test_a_reachable_repository_and_default_branch_pass(github_api):
    assert await check(github_api) is None
    assert github_api["requests"] == ["/repos/octo/demo", "/repos/octo/demo/branches/main"]


@real_check
async def test_the_branch_comes_from_the_argument_before_the_url(github_api):
    assert await check(github_api, f"{URL}/tree/from-url", "feat/x") is None
    assert github_api["requests"][-1] == "/repos/octo/demo/branches/feat/x"
    assert await check(github_api, f"{URL}/tree/from-url") is None
    assert github_api["requests"][-1] == "/repos/octo/demo/branches/from-url"


@real_check
@pytest.mark.parametrize(
    ("repo", "status", "detail"),
    [
        (
            (404, {}, {}),
            422,
            "GitHub repository octo/demo was not found. Check the URL; "
            "if it's private, the server's GITHUB_TOKEN needs access.",
        ),
        ((403, {"X-RateLimit-Remaining": "5"}, {}), 422, "GitHub denied access to octo/demo."),
        (
            (401, {}, {}),
            502,
            "GitHub rejected the server's GITHUB_TOKEN; check the token configured on the CodeSage server.",
        ),
        ((500, {}, {}), 502, "Could not reach GitHub; try again."),
        ((503, {}, {}), 502, "Could not reach GitHub; try again."),
    ],
)
async def test_repository_errors_map_to_a_status_and_message(github_api, repo, status, detail):
    github_api["repo"] = repo

    error = await check(github_api)

    assert (error.status_code, error.detail) == (status, detail)
    assert len(github_api["requests"]) == 1  # no retries, no branch lookup


@real_check
async def test_missing_branch_and_empty_repository(github_api):
    github_api["branch"] = (404, {}, {})
    error = await check(github_api, branch="nope")
    assert (error.status_code, error.detail) == (
        422,
        "Branch 'nope' does not exist in octo/demo.",
    )

    # Assumed GitHub behaviour: an empty repository has no branches, so the lookup 404s
    github_api["repo"] = (200, {}, {"default_branch": "main", "size": 0})
    error = await check(github_api)
    assert (error.status_code, error.detail) == (
        422,
        "octo/demo is empty; there is nothing to index.",
    )


@real_check
async def test_branch_lookup_failures_use_the_same_mapping(github_api):
    github_api["branch"] = (403, {}, {})
    assert (await check(github_api)).detail == "GitHub denied access to octo/demo."
    github_api["branch"] = (502, {}, {})
    assert (await check(github_api)).status_code == 502


@real_check
async def test_rate_limit_from_the_reset_header(github_api):
    reset = int(time.time()) + 150
    github_api["repo"] = (
        403,
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)},
        {},
    )

    error = await check(github_api)

    assert error.status_code == 503
    assert error.detail == "GitHub's API rate limit was reached; try again in about 3 minutes."
    assert 148 <= int(error.headers["Retry-After"]) <= 151


@real_check
async def test_rate_limit_from_retry_after(github_api):
    github_api["branch"] = (429, {"Retry-After": "30"}, {})

    error = await check(github_api)

    assert error.status_code == 503
    assert error.detail == "GitHub's API rate limit was reached; try again in about 1 minute."
    assert error.headers == {"Retry-After": "30"}


@real_check
async def test_a_slow_github_times_out(github_api, monkeypatch):
    github_api["delay"] = 1
    monkeypatch.setattr(GitHubService, "_new_session", _fast_session(GitHubService._new_session))

    error = await check(github_api)

    assert (error.status_code, error.detail) == (504, "GitHub did not respond in time; try again.")


def _fast_session(original):
    return lambda self, total_timeout=30: original(self, total_timeout=0.1)


@real_check
async def test_an_unreachable_github_hides_the_aiohttp_text():
    service = GitHubService()
    service.base_url = "http://127.0.0.1:1"  # nothing listens here

    with pytest.raises(RepositoryCheckError) as caught:
        await service.check_repository(URL)

    assert (caught.value.status_code, caught.value.detail) == (
        502,
        "Could not reach GitHub; try again.",
    )


@pytest.fixture
def check_fails(monkeypatch):
    """Make the stubbed pre-flight check refuse with `RepositoryCheckError(*args)`"""

    def fail(*args):
        async def refuse(self, url, branch=None):
            raise RepositoryCheckError(*args)

        monkeypatch.setattr(GitHubService, "check_repository", refuse)

    return fail


def test_a_refused_repository_creates_no_row(client, db_session, check_fails):
    check_fails(422, "GitHub repository octo/demo was not found.")

    response = client.post(f"{API}/", json={"url": URL})

    assert response.status_code == 422
    assert response.json() == {"detail": "GitHub repository octo/demo was not found."}
    assert db_session.query(Repository).count() == 0


def test_a_rate_limited_check_sets_retry_after(client, db_session, check_fails):
    check_fails(503, "GitHub's API rate limit was reached; try again in about 2 minutes.", {"Retry-After": "90"})

    response = client.post(f"{API}/", json={"url": URL})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "90"
    assert db_session.query(Repository).count() == 0


def test_the_check_receives_the_url_and_branch(client, monkeypatch):
    seen = []

    async def record(self, url, branch=None):
        seen.append((url, branch))

    monkeypatch.setattr(GitHubService, "check_repository", record)
    monkeypatch.setattr(repository_service, "start_processing", lambda *a, **k: None)

    assert client.post(f"{API}/", json={"url": f"{URL}/tree/dev"}).status_code == 201
    assert seen == [(URL, "dev")]


def test_duplicates_ignore_case_and_name_the_existing_row(client, db_session, monkeypatch):
    monkeypatch.setattr(repository_service, "start_processing", lambda *a, **k: None)
    first = client.post(f"{API}/", json={"url": "https://github.com/Octo/Demo"})
    assert first.status_code == 201

    again = client.post(f"{API}/", json={"url": "https://github.com/octo/demo"})

    assert again.status_code == 409
    assert again.json() == {
        "detail": "octo/demo has already been added.",
        "repository_id": first.json()["id"],
    }
    assert db_session.query(Repository).count() == 1


@pytest.mark.parametrize(
    ("payload", "loc"),
    [
        ({"url": "https://example.com/octo/demo"}, ["body", "url"]),
        ({"url": URL, "branch": "a/../b"}, ["body", "branch"]),
        ({"url": URL, "name": "n" * 256}, ["body", "name"]),
        ({"url": URL, "branch": "b" * 101}, ["body", "branch"]),
    ],
)
def test_validation_errors_point_at_the_field(client, payload, loc):
    response = client.post(f"{API}/", json=payload)

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == loc
    assert not error["msg"].startswith("Value error")


def test_url_errors_keep_braces_literal(client):
    response = client.post(f"{API}/", json={"url": "https://example.com/{x}"})

    assert response.status_code == 422
    assert "{x}" in response.json()["detail"][0]["msg"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/99999999999999999999"),
        ("get", "/99999999999999999999/status"),
        ("get", "/99999999999999999999/stats"),
        ("put", "/99999999999999999999"),
        ("delete", "/99999999999999999999"),
        ("post", "/99999999999999999999/process"),
        ("get", "/0"),
    ],
)
def test_out_of_range_ids_are_422(client, method, path):
    kwargs = {"json": {}} if method == "put" else {}

    assert getattr(client, method)(f"{API}{path}", **kwargs).status_code == 422


def test_skip_is_bounded(client):
    assert client.get(f"{API}/?skip=99999999999999999999").status_code == 422


def test_process_marks_the_repository_processing_before_returning(client, db_session, monkeypatch):
    repo = Repository(
        name="d", url=URL, status="failed", error_message="old failure", processed_files=0,
        total_files=0, total_lines=0,
    )
    db_session.add(repo)
    db_session.commit()
    from app.api.v1.endpoints import repositories

    monkeypatch.setattr(repositories, "start_processing", lambda *a, **k: None)

    assert client.post(f"{API}/{repo.id}/process").status_code == 202

    status = client.get(f"{API}/{repo.id}/status").json()
    assert status["status"] == "processing"
    assert status["error_message"] is None


def test_status_reports_the_failure_reason(client, db_session):
    repo = Repository(
        name="d", url=URL, status="failed", error_message="Branch gone", processed_files=0,
        total_files=0, total_lines=0,
    )
    db_session.add(repo)
    db_session.commit()

    assert client.get(f"{API}/{repo.id}/status").json()["error_message"] == "Branch gone"


def test_create_and_process_need_algolia(client, db_session, monkeypatch):
    class NoAlgolia:
        def is_available(self):
            return False

    monkeypatch.setattr(algolia_module, "AlgoliaService", NoAlgolia)
    repo = Repository(
        name="d", url=URL, status="failed", processed_files=0, total_files=0, total_lines=0
    )
    db_session.add(repo)
    db_session.commit()

    created = client.post(f"{API}/", json={"url": "https://github.com/octo/other"})
    processed = client.post(f"{API}/{repo.id}/process")

    for response in (created, processed):
        assert response.status_code == 503
        assert response.json()["detail"].startswith("Search indexing is not configured")
    assert db_session.query(Repository).count() == 1
