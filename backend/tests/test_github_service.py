"""GitHubService against local HTTP servers that mimic the GitHub API and raw host"""

import asyncio
import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.services import github_service as gh
from app.services.github_service import (
    GitHubAPIError,
    GitHubService,
    is_denied_path,
    parse_github_url,
)

REPO_URL = "https://github.com/octo/demo"


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr(gh, "RETRY_BACKOFF_BASE", 0.01)


@pytest.fixture
async def github_api():
    """Fake API + raw host. Records requests; per-route failures are queued"""
    state = {
        "default_branch": "main",
        "trees": {},  # branch -> list of tree entries (or full response dict)
        "listings": {},  # contents path -> list
        "raw": {},  # path -> bytes
        "fail": {},  # route name -> list of (status, headers) consumed in order
        "always_fail": {},  # route name -> (status, headers)
        "requests": [],
        "raw_delay": 0.0,
        "in_flight": 0,
        "max_in_flight": 0,
    }

    def failure(name):
        queued = state["fail"].get(name)
        if queued:
            status, headers = queued.pop(0)
        elif name in state["always_fail"]:
            status, headers = state["always_fail"][name]
        else:
            return None
        return web.json_response({"message": "error"}, status=status, headers=headers)

    async def repo_info(request):
        state["requests"].append(request.path_qs)
        return failure("repo") or web.json_response({"default_branch": state["default_branch"]})

    async def tree(request):
        state["requests"].append(request.path_qs)
        branch = request.match_info["branch"]
        assert request.query.get("recursive") == "1"
        if (err := failure("tree")) is not None:
            return err
        data = state["trees"][branch]
        body = data if isinstance(data, dict) else {"tree": data, "truncated": False}
        return web.json_response(body)

    async def contents(request):
        state["requests"].append(request.path_qs)
        path = request.match_info["path"]
        if (err := failure(f"contents:{path}")) is not None:
            return err
        return web.json_response(state["listings"][path])

    async def raw(request):
        state["requests"].append(request.path)
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        try:
            await asyncio.sleep(state["raw_delay"])
            if (err := failure(f"raw:{request.match_info['path']}")) is not None:
                return err
            key = f"{request.match_info['branch']}:{request.match_info['path']}"
            if key not in state["raw"]:
                return web.Response(status=404)
            return web.Response(body=state["raw"][key])
        finally:
            state["in_flight"] -= 1

    app = web.Application()
    app.router.add_get("/repos/octo/demo", repo_info)
    app.router.add_get("/repos/octo/demo/git/trees/{branch}", tree)
    app.router.add_get("/repos/octo/demo/contents/{path:.*}", contents)
    app.router.add_get("/raw/octo/demo/{branch}/{path:.*}", raw)
    server = TestServer(app)
    await server.start_server()
    state["base"] = str(server.make_url("")).rstrip("/")
    try:
        yield state
    finally:
        await server.close()


def service_for(api) -> GitHubService:
    service = GitHubService()
    service.base_url = api["base"]
    service.raw_base_url = f"{api['base']}/raw"
    return service


def blob(path, size):
    return {"type": "blob", "path": path, "size": size, "mode": "100644"}


def downloads(api):
    return [r for r in api["requests"] if r.startswith("/raw/")]


async def test_content_is_decoded_and_unwanted_files_are_never_downloaded(github_api):
    app_py = "﻿def café():\n    return 'é'\n".encode()
    util_py = b"def helper():\n    pass\n"
    binary_json = b'{"a": 1}\x00\x01'
    github_api["raw"] = {
        "main:app.py": app_py,
        "main:pkg/util.py": util_py,
        "main:data.json": binary_json,
    }
    github_api["trees"]["main"] = [
        blob("app.py", len(app_py)),
        blob("logo.png", 10),
        blob("data.json", len(binary_json)),
        blob("big.js", 2 * 1024 * 1024),
        {"type": "tree", "path": "pkg", "mode": "040000"},
        blob("pkg/util.py", len(util_py)),
    ]

    files = await service_for(github_api).get_repository_files(REPO_URL)

    assert [f.path for f in files] == ["app.py", "pkg/util.py"]
    assert all(isinstance(f.content, str) for f in files)
    # UTF-8 decoded with the byte-order mark removed
    assert files[0].content == "def café():\n    return 'é'\n"
    assert files[0].filename == "app.py"
    assert files[1].language == "python"
    # Wrong extension and oversized files are filtered before any download
    assert not any("logo.png" in r or "big.js" in r for r in downloads(github_api))
    # Binary content is downloaded (size unknown beforehand) but dropped
    assert "/raw/octo/demo/main/data.json" in downloads(github_api)


async def test_default_branch_is_resolved_when_not_given(github_api):
    github_api["default_branch"] = "trunk"
    github_api["trees"]["trunk"] = [blob("a.py", 5)]
    github_api["raw"] = {"trunk:a.py": b"x = 1\n"}

    files = await service_for(github_api).get_repository_files(REPO_URL)

    assert [f.path for f in files] == ["a.py"]
    assert "/repos/octo/demo" in github_api["requests"]
    assert downloads(github_api) == ["/raw/octo/demo/trunk/a.py"]


async def test_explicit_branch_skips_default_branch_lookup(github_api):
    github_api["trees"]["dev"] = [blob("a.py", 5)]
    github_api["raw"] = {"dev:a.py": b"x = 1\n"}

    files = await service_for(github_api).get_repository_files(REPO_URL, "dev")

    assert [f.path for f in files] == ["a.py"]
    assert "/repos/octo/demo" not in github_api["requests"]
    assert downloads(github_api) == ["/raw/octo/demo/dev/a.py"]


async def test_branch_in_url_is_used_and_argument_wins(github_api):
    github_api["trees"]["feature"] = [blob("a.py", 5)]
    github_api["trees"]["dev"] = [blob("b.py", 5)]
    github_api["raw"] = {"feature:a.py": b"x = 1\n", "dev:b.py": b"y = 2\n"}
    service = service_for(github_api)

    from_url = await service.get_repository_files(f"{REPO_URL}/tree/feature")
    from_arg = await service.get_repository_files(f"{REPO_URL}/tree/feature", "dev")

    assert [f.path for f in from_url] == ["a.py"]
    assert [f.path for f in from_arg] == ["b.py"]


async def test_deny_list_paths_are_never_downloaded(github_api):
    kept = ["lodash.js", "src/index.js", "src/build.py"]
    denied = [
        "dist/lodash.js",
        "node_modules/x/index.js",
        "vendor/lib.css",
        "src/third_party/a.py",
        "docs/build/out.html",
        ".next/server.js",
        "coverage/report.html",
        "__pycache__/m.py",
        ".git/config.json",
        "app.min.js",
        "static/site.min.css",
        "out.bundle.js",
        "app.js.map",
        "package-lock.json",
        "sub/package-lock.json",
        "poetry.lock",
    ]
    github_api["trees"]["main"] = [blob(p, 5) for p in kept + denied]
    github_api["raw"] = {f"main:{p}": b"x = 1\n" for p in kept + denied}

    files = await service_for(github_api).get_repository_files(REPO_URL)

    assert [f.path for f in files] == sorted(kept)
    assert sorted(downloads(github_api)) == sorted(f"/raw/octo/demo/main/{p}" for p in kept)


def test_is_denied_path():
    assert is_denied_path("a/node_modules/b.js")
    assert is_denied_path("Cargo.lock")
    assert is_denied_path("yarn.lock")
    assert is_denied_path("pnpm-lock.yaml")
    # Only whole segments match, and only directories
    assert not is_denied_path("src/distance.py")
    assert not is_denied_path("src/dist.py")
    assert not is_denied_path("src/builder/x.py")


async def test_max_files_applies_after_filtering_in_sorted_order(github_api):
    github_api["trees"]["main"] = [
        blob("dist/a.js", 5),
        blob("z.py", 5),
        blob("b.py", 5),
        blob("a.py", 5),
        blob("img.png", 5),
    ]
    github_api["raw"] = {f"main:{p}": b"x = 1\n" for p in ("z.py", "b.py", "a.py")}
    service = service_for(github_api)
    service.max_files = 2

    files = await service.get_repository_files(REPO_URL)

    assert [f.path for f in files] == ["a.py", "b.py"]
    assert service.skipped_files == 1

    # A reused instance reports only its latest listing
    service.max_files = 1000
    await service.get_repository_files(REPO_URL)
    assert service.skipped_files == 0

    # The total size cap applies the same way
    service.max_files, service.max_total_bytes = 1000, 12
    files = await service.get_repository_files(REPO_URL)
    assert [f.path for f in files] == ["a.py", "b.py"]
    assert service.skipped_files == 1


async def test_truncated_tree_falls_back_to_contents_walk_on_the_branch(github_api):
    github_api["trees"]["dev"] = {"tree": [], "truncated": True}
    github_api["listings"] = {
        "": [
            {"type": "file", "path": "app.py", "size": 5},
            {"type": "file", "path": "logo.png", "size": 5},
            {"type": "dir", "path": "pkg"},
            {"type": "dir", "path": "node_modules"},
            {"type": "dir", "path": "dist"},
        ],
        "pkg": [{"type": "file", "path": "pkg/util.py", "size": 5}],
    }
    github_api["raw"] = {"dev:app.py": b"x = 1\n", "dev:pkg/util.py": b"y = 2\n"}

    files = await service_for(github_api).get_repository_files(REPO_URL, "dev")

    assert [f.path for f in files] == ["app.py", "pkg/util.py"]
    requests = github_api["requests"]
    assert "/repos/octo/demo/contents/?ref=dev" in requests
    assert "/repos/octo/demo/contents/pkg?ref=dev" in requests
    # Denied directories are not even listed
    assert not any("node_modules" in r or "dist" in r for r in requests)


async def test_contents_walk_stops_at_its_request_cap(github_api, monkeypatch):
    monkeypatch.setattr(gh, "MAX_WALK_REQUESTS", 2)
    github_api["trees"]["dev"] = {"tree": [], "truncated": True}
    github_api["listings"] = {
        "": [{"type": "file", "path": "app.py", "size": 5}, {"type": "dir", "path": "a"}, {"type": "dir", "path": "b"}],
        "a": [{"type": "file", "path": "a/x.py", "size": 5}],
        "b": [{"type": "file", "path": "b/y.py", "size": 5}],
    }
    github_api["raw"] = {"dev:app.py": b"x = 1\n", "dev:a/x.py": b"y = 2\n"}
    service = service_for(github_api)

    files = await service.get_repository_files(REPO_URL, "dev")

    assert [f.path for f in files] == ["a/x.py", "app.py"]
    assert service.listing_truncated
    assert "/repos/octo/demo/contents/b?ref=dev" not in github_api["requests"]

    # The same service listing a complete tree next reports it as complete
    github_api["trees"]["dev"] = {"tree": [blob("app.py", 5)], "truncated": False}
    await service.get_repository_files(REPO_URL, "dev")
    assert not service.listing_truncated


async def test_downloads_run_concurrently_within_the_limit(github_api):
    paths = [f"f{i}.py" for i in range(12)]
    github_api["trees"]["main"] = [blob(p, 5) for p in paths]
    github_api["raw"] = {f"main:{p}": b"x = 1\n" for p in paths}
    github_api["raw_delay"] = 0.2

    started = time.monotonic()
    files = await service_for(github_api).get_repository_files(REPO_URL, "main")
    elapsed = time.monotonic() - started

    assert len(files) == 12
    assert github_api["max_in_flight"] > 1
    assert github_api["max_in_flight"] <= gh.MAX_CONCURRENT_REQUESTS
    # Sequential would take 12 * 0.2s = 2.4s
    assert elapsed < 1.6


async def test_failed_download_fails_the_fetch(github_api):
    # A partial file list would let a reprocess replace a complete index
    github_api["trees"]["main"] = [blob("ok.py", 5), blob("gone.py", 5)]
    github_api["raw"] = {"main:ok.py": b"x = 1\n"}  # gone.py -> 404

    with pytest.raises(GitHubAPIError, match=r"\(404\) for gone.py"):
        await service_for(github_api).get_repository_files(REPO_URL, "main")

    assert downloads(github_api).count("/raw/octo/demo/main/gone.py") == 1  # 4xx isn't retried


async def test_transient_download_failure_is_retried(github_api):
    github_api["trees"]["main"] = [blob("a.py", 5)]
    github_api["raw"] = {"main:a.py": b"x = 1\n"}
    github_api["fail"]["raw:a.py"] = [(503, {}), (429, {})]

    files = await service_for(github_api).get_repository_files(REPO_URL, "main")

    assert [f.path for f in files] == ["a.py"]
    assert len(downloads(github_api)) == 3


async def test_persistent_download_failure_raises_after_max_retries(github_api):
    github_api["trees"]["main"] = [blob("a.py", 5)]
    github_api["always_fail"]["raw:a.py"] = (502, {})

    with pytest.raises(GitHubAPIError, match=r"\(502\) for a.py"):
        await service_for(github_api).get_repository_files(REPO_URL, "main")

    assert len(downloads(github_api)) == gh.MAX_RETRIES


async def test_5xx_is_retried_then_succeeds(github_api):
    github_api["trees"]["main"] = [blob("a.py", 5)]
    github_api["raw"] = {"main:a.py": b"x = 1\n"}
    github_api["fail"]["tree"] = [(502, {}), (503, {})]

    files = await service_for(github_api).get_repository_files(REPO_URL, "main")

    assert [f.path for f in files] == ["a.py"]
    tree_calls = [r for r in github_api["requests"] if "/git/trees/" in r]
    assert len(tree_calls) == 3


async def test_persistent_5xx_raises_after_max_retries(github_api):
    github_api["always_fail"]["tree"] = (502, {})

    with pytest.raises(GitHubAPIError) as excinfo:
        await service_for(github_api).get_repository_files(REPO_URL, "main")

    assert excinfo.value.status == 502
    tree_calls = [r for r in github_api["requests"] if "/git/trees/" in r]
    assert len(tree_calls) == gh.MAX_RETRIES


async def test_rate_limit_waits_for_reset_then_retries_once(github_api):
    github_api["trees"]["main"] = [blob("a.py", 5)]
    github_api["raw"] = {"main:a.py": b"x = 1\n"}
    reset = str(int(time.time()) + 1)
    github_api["fail"]["tree"] = [(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset})]

    started = time.monotonic()
    files = await service_for(github_api).get_repository_files(REPO_URL, "main")

    assert [f.path for f in files] == ["a.py"]
    assert time.monotonic() - started >= 0.5


async def test_rate_limit_that_persists_raises_after_one_retry(github_api):
    reset = str(int(time.time()))
    github_api["always_fail"]["tree"] = (
        429,
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset},
    )

    with pytest.raises(GitHubAPIError) as excinfo:
        await service_for(github_api).get_repository_files(REPO_URL, "main")

    assert excinfo.value.status == 429
    assert "rate limit exceeded (429)" in str(excinfo.value)
    tree_calls = [r for r in github_api["requests"] if "/git/trees/" in r]
    assert len(tree_calls) == 2


@pytest.mark.parametrize("route", ["repo", "tree"])
@pytest.mark.parametrize(
    "status, headers, phrase",
    [
        (401, {}, "rejected the token (401)"),
        (403, {"X-RateLimit-Remaining": "0"}, "rate limit exceeded (403)"),
        (403, {"X-RateLimit-Remaining": "12"}, "denied access (403)"),
        (404, {}, "not found (404)"),
    ],
)
async def test_api_errors_raise_instead_of_returning_no_files(
    github_api, route, status, headers, phrase
):
    github_api["always_fail"][route] = (status, headers)
    branch = "main" if route == "tree" else None

    with pytest.raises(GitHubAPIError) as excinfo:
        await service_for(github_api).get_repository_files(REPO_URL, branch)

    # A missing tree on a repository that exists names the branch instead
    missing_branch = (route, status) == ("tree", 404)
    assert excinfo.value.status == status
    assert ("Branch 'main' not found" if missing_branch else phrase) in str(excinfo.value)
    assert "octo/demo" in str(excinfo.value)
    # Non-retryable errors are not repeated (a missing tree checks the repository once)
    expected_calls = 2 if missing_branch else 1
    assert len([r for r in github_api["requests"] if r.startswith("/repos")]) == expected_calls


async def test_error_in_a_subdirectory_of_the_fallback_walk_is_not_swallowed(
    github_api,
):
    github_api["trees"]["main"] = {"tree": [], "truncated": True}
    github_api["listings"] = {
        "": [
            {"type": "file", "path": "app.py", "size": 5},
            {"type": "dir", "path": "src"},
        ]
    }
    github_api["always_fail"]["contents:src"] = (403, {"X-RateLimit-Remaining": "12"})

    with pytest.raises(GitHubAPIError) as excinfo:
        await service_for(github_api).get_repository_files(REPO_URL, "main")

    assert excinfo.value.status == 403
    assert "octo/demo/src" in str(excinfo.value)


async def test_invalid_url_raises_value_error():
    with pytest.raises(ValueError):
        await GitHubService().get_repository_files("https://evil.example/octo/demo")


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/octo/demo", ("octo", "demo", None)),
        ("http://github.com/octo/demo", ("octo", "demo", None)),
        ("https://www.github.com/octo/demo", ("octo", "demo", None)),
        ("https://github.com/octo/demo/", ("octo", "demo", None)),
        ("https://github.com/octo/demo.git", ("octo", "demo", None)),
        ("https://github.com/octo/my.git.repo", ("octo", "my.git.repo", None)),
        ("https://github.com/octo/my.git.repo.git", ("octo", "my.git.repo", None)),
        ("  https://github.com/octo/demo  ", ("octo", "demo", None)),
        ("https://github.com/octo/demo/tree/dev", ("octo", "demo", "dev")),
        ("https://github.com/octo/demo/tree/dev/", ("octo", "demo", "dev")),
        (
            "https://github.com/octo/demo/tree/feature/x%20y",
            ("octo", "demo", "feature/x y"),
        ),
        ("git@github.com:octo/demo.git", ("octo", "demo", None)),
        ("git@github.com:octo/demo", ("octo", "demo", None)),
    ],
)
def test_parse_github_url_accepts(url, expected):
    assert parse_github_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "https://github.com/octo/demo?x=1",
        "https://github.com/octo/demo#readme",
        "https://github.com/octo",
        "https://github.com/",
        "https://github.com//demo",
        "https://gitlab.com/octo/demo",
        "https://github.com.evil.com/octo/demo",
        "https://evil.com/github.com/octo/demo",
        "https://user:pw@github.com/octo/demo",
        "https://github.com:8080/octo/demo",
        "ftp://github.com/octo/demo",
        "git://github.com/octo/demo",
        "git@evil.com:octo/demo.git",
        "https://github.com/octo/demo/issues/1",
        "https://github.com/octo/demo/tree",
        "https://github.com/octo/demo/tree/../x",
        "https://github.com/octo/.git",
        "https://github.com/octo/..",
        "not a url",
    ],
)
def test_parse_github_url_rejects(url):
    with pytest.raises(ValueError):
        parse_github_url(url)


async def test_missing_branch_is_named_when_the_repository_exists(github_api):
    github_api["always_fail"]["tree"] = (404, {})

    with pytest.raises(GitHubAPIError) as excinfo:
        await service_for(github_api).get_repository_files(REPO_URL, "no-such-branch")

    assert excinfo.value.status == 404
    assert str(excinfo.value) == "Branch 'no-such-branch' not found in octo/demo"


async def test_missing_repository_is_reported_even_with_a_branch(github_api):
    github_api["always_fail"]["tree"] = (404, {})
    github_api["always_fail"]["repo"] = (404, {})

    with pytest.raises(GitHubAPIError) as excinfo:
        await service_for(github_api).get_repository_files(REPO_URL, "main")

    assert "not found (404): octo/demo" in str(excinfo.value)
