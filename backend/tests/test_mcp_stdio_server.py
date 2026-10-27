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


# The SDK warns that ping is legacy-only; testing that legacy path is the point here
@pytest.mark.filterwarnings("ignore:ping is removed")
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
    assert len(result.tools) == 7
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
    [(401, "CODESAGE_API_KEY"), (404, "returned 404"), (429, "rate limit"), (503, "503")],
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
    assert "check MCP_SERVER_URL and that the host is up" in result.content[0].text
    assert len(calls) == 2


@pytest.mark.parametrize("url", ["http://127.0.0.1:8001", "http://localhost:8001", "http://[::1]:8001"])
async def test_loopback_unreachable_suggests_starting_the_backend(url):
    def down(request):
        raise httpx.ConnectError("refused")

    async with make_client(Backend(down), config=Config(server_url=url)) as client:
        result = await client.call_tool("list_repositories", {})
    assert "make start-backend" in result.content[0].text
    assert "check MCP_SERVER_URL" not in result.content[0].text


async def test_resources_never_send_the_key_over_plain_http_to_another_host():
    backend = Backend()
    config = Config(server_url="http://codesage.example", api_key="k-123")
    async with make_client(backend, config=config) as client:
        with pytest.raises(MCPError, match="CODESAGE_ALLOW_INSECURE_AUTH"):
            await client.list_resources()
        with pytest.raises(MCPError, match="CODESAGE_ALLOW_INSECURE_AUTH"):
            await client.read_resource("codesage://repositories")
    assert backend.requests == []


async def test_a_login_in_the_url_stays_out_of_messages():
    def down(request):
        raise httpx.ConnectError("refused")

    config = Config(server_url="https://ann:s3cret@codesage.example")
    assert config.display_url == "https://codesage.example"
    async with make_client(Backend(down), config=config) as client:
        result = await client.call_tool("list_repositories", {})
    text = result.content[0].text
    assert "not reachable at https://codesage.example" in text
    assert "s3cret" not in text and "ann" not in text


@pytest.mark.parametrize("body", [["a", "list"], "a string", 42])
async def test_an_unexpected_200_body_is_a_tool_error(body):
    backend = Backend(lambda request: httpx.Response(200, json=body))
    async with make_client(backend) as client:
        result = await client.call_tool("list_repositories", {})
    assert result.is_error
    assert "unexpected response" in result.content[0].text


async def test_unexpected_resource_bodies_are_mcp_errors():
    for body in ([1, 2], {"resources": [{"no_uri": True}]}):
        backend = Backend(lambda request, body=body: httpx.Response(200, json=body))
        async with make_client(backend) as client:
            with pytest.raises(MCPError, match="unexpected response"):
                await client.list_resources()
    backend = Backend(lambda request: httpx.Response(200, json=["not", "an", "object"]))
    async with make_client(backend) as client:
        with pytest.raises(MCPError, match="unexpected response"):
            await client.read_resource("codesage://repositories")


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
        assert len(tools.tools) == 7
        result = await client.call_tool("list_repositories", {})
        assert result.is_error
        assert "not reachable" in result.content[0].text
        # Still answering after the failed call
        assert len((await client.list_tools()).tools) == 7


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


# --- error wording, shared by tool calls and resource reads -------------------------------


async def tool_text(backend: Backend, config: Config | None = None) -> str:
    async with make_client(backend, api_key="k", config=config) as client:
        result = await client.call_tool("list_repositories", {})
    assert result.is_error
    return result.content[0].text


async def resource_text(backend: Backend, config: Config | None = None) -> str:
    async with make_client(backend, api_key="k", config=config) as client:
        with pytest.raises(MCPError) as err:
            await client.read_resource("codesage://repos")
    return err.value.message


def reply(status, **kwargs):
    return Backend(lambda r: httpx.Response(status, **kwargs))


@pytest.mark.parametrize("ask", [tool_text, resource_text])
async def test_status_wording_matches_for_tools_and_resources(ask):
    assert "rejected the API key" in await ask(reply(401, json={"detail": "x"}))
    assert "rate limit exceeded (429)" in await ask(reply(429, json={"detail": "slow"}))
    text = await ask(reply(403, json={"detail": "Invalid host header"}))
    assert "refused the request (403): Invalid host header." in text and "ALLOWED_HOSTS" in text
    text = await ask(reply(404, text="<html>nope</html>"))
    assert "returned 404 for /api/v1/ai/mcp/" in text and "no /api/v1" in text
    text = await ask(reply(502, text="<html>Bad Gateway</html>"))
    assert text.startswith("CodeSage backend error (502); the backend or the proxy")
    assert "Bad Gateway" not in text


async def test_missing_key_vs_wrong_key():
    cfg = Config(server_url="https://backend.test")
    missing = await tool_text(reply(401, json={"detail": "x"}), Config(server_url="https://backend.test"))
    assert "No API key is configured" in missing and "CODESAGE_API_KEY" in missing
    wrong = await tool_text(reply(401, json={"detail": "x"}), Config(server_url=cfg.server_url, api_key="bad"))
    assert "rejected the API key" in wrong
    assert "No API key is configured" in await resource_text(reply(401), cfg)


async def test_5xx_with_json_detail_and_request_id():
    body = {"detail": "boom", "request_id": "abc123"}
    assert await tool_text(reply(500, json=body)) == "CodeSage backend error (500): boom (request abc123)"
    assert await resource_text(reply(500, json=body)) == "CodeSage backend error (500): boom (request abc123)"
    header = reply(503, json={"detail": "busy"}, headers={"X-Request-ID": "h-9"})
    assert await tool_text(header) == "CodeSage backend error (503): busy (request h-9)"
    assert await tool_text(reply(500, json={"detail": "boom"})) == "CodeSage backend error (500): boom"


async def test_resource_404_with_json_detail_is_a_real_not_found():
    text = await resource_text(reply(404, json={"detail": "Unknown resource"}))
    assert text == "Resource or repository not found: Unknown resource"


async def test_timeout_is_reported_with_the_limit():
    def slow(request):
        raise httpx.ReadTimeout("slow")

    assert await tool_text(Backend(slow)) == "CodeSage backend did not answer within 30 s."
    assert "did not answer within 30 s" in await resource_text(Backend(slow))


@pytest.mark.parametrize("url", ["localhost:8001", "backend.test", "ftp://backend.test"])
async def test_url_without_http_scheme_is_refused_before_any_request(url):
    backend = Backend()
    config = Config(server_url=url)
    expected = f"MCP_SERVER_URL must start with http:// or https:// (got '{url}')"
    assert await tool_text(backend, config) == expected
    assert await resource_text(backend, config) == expected
    assert backend.requests == []


async def test_resource_transport_errors_keep_type_and_message():
    def boom(request):
        raise httpx.ReadError("reset by peer")

    assert "ReadError: reset by peer" in await resource_text(Backend(boom))
