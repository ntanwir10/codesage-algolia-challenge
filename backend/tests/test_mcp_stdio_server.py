"""Tests for the stdio MCP bridge (codesage_mcp) using the SDK's in-memory client."""

import json
import sys
from pathlib import Path

import httpx2 as httpx
import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError

from codesage_mcp.schemas import TOOLS, input_schema
from codesage_mcp.server import Config, build_server

BACKEND_DIR = Path(__file__).resolve().parent.parent
OK_BODY = {"tool": "t", "result": {"ok": True}, "is_error": False, "error": None}


class Backend:
    """Records requests and answers them with a canned handler."""

    def __init__(self, handler=None):
        self.requests: list[httpx.Request] = []
        self.handler = handler or (lambda request: httpx.Response(200, json=OK_BODY))

    def factory(self, config: Config):
        def respond(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self.handler(request)

        return httpx.AsyncClient(
            base_url=config.base_url,
            headers=config.headers,
            auth=config.auth,
            transport=httpx.MockTransport(respond),
        )


def make_client(
    backend: Backend, api_key: str | None = None, mode: str = "auto", config: Config | None = None
) -> Client:
    server = build_server(
        config or Config(server_url="https://backend.test", api_key=api_key), backend.factory
    )
    return Client(server, mode=mode)


async def test_initialize_succeeds():
    async with make_client(Backend()) as client:
        assert client.server_info.name == "codesage"


async def test_ping_legacy_handshake():
    # ping only exists in the initialize-handshake era, which is what Claude Desktop speaks
    async with make_client(Backend(), mode="legacy") as client:
        await client.send_ping()


async def test_tools_list_matches_schemas_without_backend():
    def down(request):
        raise httpx.ConnectError("down")

    backend = Backend(down)
    async with make_client(backend) as client:
        result = await client.list_tools()
    assert [t.name for t in result.tools] == list(TOOLS)
    assert len(result.tools) == 6
    for tool in result.tools:
        assert tool.input_schema == input_schema(tool.name)
    assert backend.requests == []


async def test_successful_call_returns_json_text_and_posts_expected_body():
    payload = {
        "tool": "list_repositories",
        "result": {"repositories": [{"id": 1}]},
        "is_error": False,
        "error": None,
    }
    backend = Backend(lambda r: httpx.Response(200, json=payload))
    async with make_client(backend) as client:
        result = await client.call_tool("list_repositories", {})
    assert not result.is_error
    assert json.loads(result.content[0].text) == {"repositories": [{"id": 1}]}
    req = backend.requests[0]
    assert req.method == "POST"
    assert req.url.path == "/api/v1/ai/mcp/tools/call"
    assert json.loads(req.content) == {"tool_name": "list_repositories", "arguments": {}}


async def test_backend_is_error_maps_to_is_error():
    body = {"tool": "get_file", "result": None, "is_error": True, "error": "File not found: x.py"}
    async with make_client(Backend(lambda r: httpx.Response(200, json=body))) as client:
        result = await client.call_tool("get_file", {"repository": "r", "path": "x.py"})
    assert result.is_error
    assert "File not found: x.py" in result.content[0].text


async def test_422_includes_field_errors():
    detail = [{"loc": ["body", "arguments", "limit"], "msg": "too big", "type": "less_than_equal"}]
    async with make_client(
        Backend(lambda r: httpx.Response(422, json={"detail": detail}))
    ) as client:
        result = await client.call_tool("search_code", {"query": "x"})
    assert result.is_error
    assert "too big" in result.content[0].text and "limit" in result.content[0].text


@pytest.mark.parametrize(
    ("status", "needle"),
    [(401, "CODESAGE_API_KEY"), (404, "Unknown tool"), (429, "rate limit"), (503, "503")],
)
async def test_http_errors_become_is_error(status, needle):
    async with make_client(
        Backend(lambda r: httpx.Response(status, json={"detail": "nope"}))
    ) as client:
        result = await client.call_tool("list_repositories", {})
    assert result.is_error
    assert needle in result.content[0].text


async def test_unreachable_backend_retries_once_and_reports():
    calls = []

    def down(request):
        calls.append(1)
        raise httpx.ConnectError("refused")

    async with make_client(Backend(down)) as client:
        result = await client.call_tool("list_repositories", {})
    assert result.is_error
    assert "CodeSage backend not reachable at https://backend.test" in result.content[0].text
    assert "make start-backend" in result.content[0].text
    assert len(calls) == 2


async def test_retry_recovers_after_one_connection_error():
    state = {"n": 0}

    def flaky(request):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json=OK_BODY)

    async with make_client(Backend(flaky)) as client:
        result = await client.call_tool("list_repositories", {})
    assert not result.is_error


async def test_local_validation_rejects_bad_arguments_without_http():
    backend = Backend()
    async with make_client(backend) as client:
        bad_limit = await client.call_tool("search_code", {"query": "x", "limit": 9999})
        unknown_arg = await client.call_tool("list_repositories", {"bogus": 1})
        missing = await client.call_tool("get_file", {"repository": "r"})
        unknown_tool = await client.call_tool("nope", {})
    for result in (bad_limit, unknown_arg, missing, unknown_tool):
        assert result.is_error
    assert "limit" in bad_limit.content[0].text
    assert "path" in missing.content[0].text
    assert backend.requests == []


async def test_api_key_header_sent_only_when_set():
    with_key, without_key = Backend(), Backend()
    async with make_client(with_key, api_key="secret") as client:
        await client.call_tool("list_repositories", {})
    async with make_client(without_key) as client:
        await client.call_tool("list_repositories", {})
    assert with_key.requests[0].headers["x-api-key"] == "secret"
    assert "x-api-key" not in without_key.requests[0].headers


async def test_resources_list_and_read():
    def handler(request):
        if request.url.path.endswith("/mcp/resources/read"):
            if request.url.params["uri"] == "codesage://missing":
                return httpx.Response(404, json={"detail": "Resource not found"})
            return httpx.Response(
                200,
                json={"uri": "codesage://repos", "mimeType": "application/json", "content": "[1]"},
            )
        return httpx.Response(
            200,
            json={
                "resources": [
                    {
                        "uri": "codesage://repos",
                        "name": "Repos",
                        "description": "d",
                        "mimeType": "application/json",
                    }
                ],
                "count": 1,
            },
        )

    async with make_client(Backend(handler)) as client:
        listed = await client.list_resources()
        assert [(r.uri, r.name, r.mime_type) for r in listed.resources] == [
            ("codesage://repos", "Repos", "application/json")
        ]
        read = await client.read_resource("codesage://repos")
        assert read.contents[0].text == "[1]"
        with pytest.raises(MCPError) as err:
            await client.read_resource("codesage://missing")
    assert "not found" in err.value.message.lower()


async def test_stdio_subprocess_smoke():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "codesage_mcp"],
        cwd=str(BACKEND_DIR),
        env={"MCP_SERVER_URL": "http://127.0.0.1:9", "CODESAGE_API_KEY": ""},
    )
    async with Client(stdio_client(params), mode="legacy") as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 6
        result = await client.call_tool("list_repositories", {})
        assert result.is_error
        assert "not reachable" in result.content[0].text
        await client.send_ping()


async def test_proxy_401_blames_the_login_not_the_api_key():
    challenge = {"WWW-Authenticate": 'Basic realm="CodeSage"'}
    async with make_client(Backend(lambda r: httpx.Response(401, headers=challenge))) as client:
        result = await client.call_tool("list_repositories", {})
    assert result.is_error
    assert "rejected the login" in result.content[0].text
    assert "CODESAGE_API_KEY" not in result.content[0].text


async def test_basic_auth_login_is_sent():
    backend = Backend()
    config = Config(server_url="https://codesage.example", basic_user="ann", basic_password="pw")
    async with make_client(backend, config=config) as client:
        await client.call_tool("list_repositories", {})
    assert backend.requests[0].headers["authorization"].startswith("Basic ")


@pytest.mark.parametrize(
    ("url", "allow", "refused"),
    [
        ("http://codesage.example", False, True),
        ("http://ann:pw@codesage.example", False, True),  # a login inside the URL counts too
        ("http://codesage.example", True, False),
        ("https://codesage.example", False, False),
        ("http://127.0.0.1", False, False),
    ],
)
async def test_login_is_never_sent_over_plain_http_to_another_host(url, allow, refused):
    backend = Backend()
    user = None if "@" in url else "ann"
    config = Config(server_url=url, basic_user=user, basic_password="pw", allow_insecure_auth=allow)
    async with make_client(backend, config=config) as client:
        result = await client.call_tool("list_repositories", {})
    assert result.is_error is refused
    assert (backend.requests == []) is refused
    if refused:
        assert "CODESAGE_ALLOW_INSECURE_AUTH" in result.content[0].text


@pytest.mark.parametrize(
    ("url", "refused"),
    [("http://codesage.example", True), ("https://codesage.example", False), ("http://localhost:8001", False)],
)
async def test_api_key_is_never_sent_over_plain_http_to_another_host(url, refused):
    backend = Backend()
    async with make_client(backend, config=Config(server_url=url, api_key="k-123")) as client:
        result = await client.call_tool("list_repositories", {})
    assert result.is_error is refused
    assert (backend.requests == []) is refused
