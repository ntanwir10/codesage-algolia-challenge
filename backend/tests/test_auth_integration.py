"""The API key also guards the MCP tool call and the WebSocket"""

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

LOCAL = ("127.0.0.1", 50000)  # TestClient's default peer, "testclient", is not a loopback address

TOOL_CALL = "/api/v1/ai/mcp/tools/call"


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "codesage_api_key", "s3cret")
    return "s3cret"


def test_tool_call_requires_the_api_key(client, api_key):
    body = {"tool_name": "list_repositories", "arguments": {}}

    assert client.post(TOOL_CALL, json=body).status_code == 401
    response = client.post(TOOL_CALL, json=body, headers={"X-API-Key": api_key})
    assert response.status_code == 200
    assert response.json()["is_error"] is False


def test_search_suggestions_require_the_key_and_are_rate_limited(client, api_key, monkeypatch):
    url = "/api/v1/ai/search/suggestions"
    assert client.get(url, params={"query": "abc"}).status_code == 401

    monkeypatch.setattr(get_settings(), "rate_limit_default", "2/minute")
    statuses = [
        client.get(url, params={"query": "abc"}, headers={"X-API-Key": api_key}).status_code
        for _ in range(3)
    ]
    assert statuses == [200, 200, 429]


def test_tool_call_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_ai", "2/minute")
    body = {"tool_name": "list_repositories", "arguments": {}}

    statuses = [client.post(TOOL_CALL, json=body).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def key_protocols(key: str) -> list[str]:
    return ["codesage", "codesage.key." + key.encode().hex()]


def test_websocket_rejects_a_missing_or_wrong_key(api_key):
    client = TestClient(app, base_url="http://localhost", client=LOCAL)
    attempts = [
        ("/ws", None),
        ("/ws", key_protocols("wrong")),
        ("/ws", ["codesage", "codesage.key.not-hex"]),
        (f"/ws?api_key={api_key}", None),  # keys in URLs end up in access logs, so they're ignored
    ]
    for url, protocols in attempts:
        with pytest.raises(WebSocketDisconnect) as excinfo, client.websocket_connect(
            url, subprotocols=protocols
        ) as ws:
            ws.receive_json()
        assert excinfo.value.code == 1008


def test_websocket_accepts_the_key_in_a_subprotocol(api_key):
    client = TestClient(app, base_url="http://localhost", client=LOCAL)
    with client.websocket_connect("ws://localhost/ws", subprotocols=key_protocols(api_key)) as ws:
        assert ws.accepted_subprotocol == "codesage"
        assert ws.receive_json()["type"] == "connected"


def test_websocket_accepts_the_key_as_a_header(api_key):
    # The prod nginx proxy injects the key as a header; browsers never hold it
    with TestClient(app, base_url="http://localhost", client=LOCAL).websocket_connect("ws://localhost/ws", headers={"X-API-Key": api_key}) as ws:
        assert ws.receive_json()["type"] == "connected"
    with pytest.raises(WebSocketDisconnect) as excinfo, TestClient(app, base_url="http://localhost", client=LOCAL).websocket_connect(
        "ws://localhost/ws", headers={"X-API-Key": "wrong"}
    ) as ws:
        ws.receive_json()
    assert excinfo.value.code == 1008
