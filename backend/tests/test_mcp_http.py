"""MCP over streamable HTTP at /mcp: what a URL-based client (ChatGPT, a remote agent) gets"""

import httpx2 as httpx
import jsonschema
import pytest
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


async def test_the_demo_offers_only_tools_that_read(mcp):
    init = await mcp("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "chatgpt", "version": "1"}})
    assert init.json()["result"]["serverInfo"]["name"] == "codesage"

    tools = (await mcp("tools/list")).json()["result"]["tools"]
    assert len(tools) == 7 and "add_repository" not in [t["name"] for t in tools]
    assert all(t["annotations"]["readOnlyHint"] for t in tools)

    # A client that calls it anyway gets an error, not a new repository
    call = await mcp("tools/call", {"name": "add_repository", "arguments": {"url": "https://github.com/a/b"}})
    assert call.json()["result"]["isError"] is True


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
