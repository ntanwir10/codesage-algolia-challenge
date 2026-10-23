"""GitHubService against a local HTTP server that mimics the GitHub contents API"""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.services.github_service import GitHubAPIError, GitHubService

REPO_URL = "https://github.com/octo/demo"


@pytest.fixture
async def github_api():
    """Serves contents listings and raw downloads, recording every requested path"""
    state = {"listings": {}, "raw": {}, "errors": {}, "requests": []}

    async def contents(request):
        path = request.match_info["path"]
        state["requests"].append(request.path)
        if path in state["errors"]:
            status, headers = state["errors"][path]
            return web.json_response(
                {"message": "error"}, status=status, headers=headers
            )
        return web.json_response(state["listings"][path])

    async def raw(request):
        state["requests"].append(request.path)
        return web.Response(body=state["raw"][request.match_info["name"]])

    app = web.Application()
    app.router.add_get("/repos/octo/demo/contents/{path:.*}", contents)
    app.router.add_get("/raw/{name}", raw)
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
    return service


def file_entry(api, path, raw_name, size):
    return {
        "type": "file",
        "path": path,
        "size": size,
        "download_url": f"{api['base']}/raw/{raw_name}",
    }


async def test_content_is_decoded_and_unwanted_files_are_never_downloaded(github_api):
    app_py = "﻿def café():\n    return 'é'\n".encode("utf-8")
    util_py = b"def helper():\n    pass\n"
    binary_json = b'{"a": 1}\x00\x01'
    github_api["raw"] = {"app.py": app_py, "util.py": util_py, "data.json": binary_json}
    github_api["listings"] = {
        "": [
            file_entry(github_api, "app.py", "app.py", len(app_py)),
            file_entry(github_api, "logo.png", "logo.png", 10),
            file_entry(github_api, "data.json", "data.json", len(binary_json)),
            file_entry(github_api, "big.js", "big.js", 2 * 1024 * 1024),
            {"type": "dir", "path": "pkg"},
        ],
        "pkg": [file_entry(github_api, "pkg/util.py", "util.py", len(util_py))],
    }

    files = await service_for(github_api).get_repository_files(REPO_URL)

    assert [f.path for f in files] == ["app.py", "pkg/util.py"]
    assert all(isinstance(f.content, str) for f in files)
    # UTF-8 decoded with the byte-order mark removed
    assert files[0].content == "def café():\n    return 'é'\n"
    assert files[1].language == "python"
    # Wrong extension and oversized files are filtered before any download
    assert "/raw/logo.png" not in github_api["requests"]
    assert "/raw/big.js" not in github_api["requests"]


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
    github_api, status, headers, phrase
):
    github_api["errors"][""] = (status, headers)

    with pytest.raises(GitHubAPIError) as excinfo:
        await service_for(github_api).get_repository_files(REPO_URL)

    assert excinfo.value.status == status
    assert phrase in str(excinfo.value)
    assert "octo/demo" in str(excinfo.value)


async def test_error_in_a_subdirectory_is_not_swallowed(github_api):
    github_api["raw"] = {"app.py": b"def a():\n    pass\n"}
    github_api["listings"] = {
        "": [
            file_entry(github_api, "app.py", "app.py", 18),
            {"type": "dir", "path": "src"},
        ]
    }
    github_api["errors"]["src"] = (403, {"X-RateLimit-Remaining": "0"})

    with pytest.raises(GitHubAPIError) as excinfo:
        await service_for(github_api).get_repository_files(REPO_URL)

    assert excinfo.value.status == 403
    assert "octo/demo/src" in str(excinfo.value)
