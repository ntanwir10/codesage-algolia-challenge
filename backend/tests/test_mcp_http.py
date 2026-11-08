"""MCP over streamable HTTP at /mcp: what a URL-based client (ChatGPT, a remote agent) gets"""

import httpx2 as httpx
import jsonschema
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.orm import sessionmaker

from app import mcp_http
from app.core.config import get_settings
from app.main import app
from app.models.repository import Repository
from codesage_mcp.schemas import output_schema

DEMO_HOST = "codesage-demo.example.com"
HEADERS = {"accept": "application/json, text/event-stream"}
HIT = {
    "entity_name": "create", "entity_type": "function", "file_path": "src/vanilla.ts",
    "line_start": 5, "line_end": 20, "language": "typescript", "signature": "create()",
    "content": "export const create = () => {}", "description": "makes a store",
}


@pytest.fixture
def settings(monkeypatch, db_engine):
    """The public demo: read-only, no key"""
    settings = get_settings()
    monkeypatch.setattr(settings, "read_only", True)
    monkeypatch.setattr(settings, "codesage_api_key", None)
    monkeypatch.setattr(settings, "allowed_hosts", DEMO_HOST)
    monkeypatch.setattr(mcp_http, "SessionLocal", sessionmaker(bind=db_engine))
    return settings


@pytest.fixture
async def mcp(settings):
    """An internet client posting JSON-RPC to the server's public name"""
    transport = httpx.ASGITransport(app=app, client=("203.0.113.9", 40000))
    async with httpx.AsyncClient(transport=transport, base_url=f"https://{DEMO_HOST}") as client:

        async def rpc(method, params=None, headers=None):
            body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
            return await client.post("/mcp", json=body, headers={**HEADERS, **(headers or {})})

        yield rpc


@pytest.fixture
def repo(db_session):
    repo = Repository(name="pmndrs/zustand", url="https://github.com/pmndrs/zustand", status="completed")
    db_session.add(repo)
    db_session.commit()
    return repo


async def test_a_real_client_on_the_demo_gets_only_tools_that_read(settings):
    # The SDK's own client, so the handshake (initialized notification, protocol-version header) is real
    transport = httpx.ASGITransport(app=app, client=("203.0.113.9", 40000))
    async with (
        httpx.AsyncClient(transport=transport, base_url=f"https://{DEMO_HOST}") as http,
        streamable_http_client(f"https://{DEMO_HOST}/mcp", http_client=http) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        assert (await session.initialize()).server_info.name == "codesage"

        tools = (await session.list_tools()).tools
        assert len(tools) == 7 and "add_repository" not in [t.name for t in tools]
        assert all(t.annotations.read_only_hint for t in tools)

        # A client that calls it anyway gets an error, not a new repository
        call = await session.call_tool("add_repository", {"url": "https://github.com/a/b"})
        assert call.is_error is True


async def test_search_answers_from_the_index(mcp, repo, algolia_index):
    algolia_index.search = lambda q, params: {"hits": [{**HIT, "repository_id": repo.id}], "nbHits": 1}

    result = (await mcp("tools/call", {"name": "search_code", "arguments": {"query": "create"}})).json()["result"]

    assert result["isError"] is False
    assert result["structuredContent"]["results"][0]["file_path"] == "src/vanilla.ts"
    jsonschema.validate(result["structuredContent"], output_schema("search_code"))


async def test_a_keyed_server_takes_the_key_or_a_bearer_token(settings, mcp, monkeypatch):
    monkeypatch.setattr(settings, "read_only", False)
    monkeypatch.setattr(settings, "codesage_api_key", "s3cret")

    refused = await mcp("tools/list")
    assert refused.status_code == 401 and refused.headers["www-authenticate"] == "Bearer"
    assert (await mcp("tools/list", headers={"authorization": "Bearer wrong"})).status_code == 401
    assert (await mcp("tools/list", headers={"authorization": "Bearer s3cret"})).status_code == 200
    assert (await mcp("tools/list", headers={"x-api-key": "s3cret"})).status_code == 200


async def test_calls_are_rate_limited_per_client(settings, mcp, monkeypatch):
    # slowapi doesn't see this route, so without its own check the public demo would have no limit
    monkeypatch.setattr(settings, "rate_limit_ai", "2/minute")
    assert [(await mcp("tools/list")).status_code for _ in range(3)] == [200, 200, 429]


async def test_resources_are_read_here(mcp, repo):
    listing = (await mcp("resources/read", {"uri": "codesage://repositories"})).json()["result"]
    assert "pmndrs/zustand" in listing["contents"][0]["text"]

    missing = (await mcp("resources/read", {"uri": "codesage://repositories/999/files"})).json()
    assert missing["error"]["code"] == -32602 and "not found" in missing["error"]["message"]


async def test_an_unexpected_failure_is_logged_not_shown(mcp, monkeypatch, caplog):
    # A database error's text carries SQL and file contents; an anonymous client must not see it
    async def broken(db, name, arguments):
        raise RuntimeError("SENTINEL select * from code_files")

    monkeypatch.setattr(mcp_http.mcp_tools, "call_tool", broken)
    body = (await mcp("tools/call", {"name": "list_repositories", "arguments": {}})).text
    assert "SENTINEL" not in body
    assert "SENTINEL" in caplog.text
