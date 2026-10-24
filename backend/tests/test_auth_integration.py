"""The API key also guards the MCP tool call and the WebSocket"""

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

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


def test_tool_call_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_ai", "2/minute")
    body = {"tool_name": "list_repositories", "arguments": {}}

    statuses = [client.post(TOOL_CALL, json=body).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def test_websocket_rejects_a_missing_or_wrong_key(api_key):
    client = TestClient(app)
    for url in ("/ws", "/ws?api_key=wrong"):
        with pytest.raises(WebSocketDisconnect) as excinfo, client.websocket_connect(url) as ws:
            ws.receive_json()
        assert excinfo.value.code == 1008


def test_websocket_accepts_the_key_as_a_query_parameter(api_key):
    with TestClient(app).websocket_connect(f"/ws?api_key={api_key}") as ws:
        assert ws.receive_json()["type"] == "connected"


def test_websocket_accepts_the_key_as_a_header(api_key):
    # The prod nginx proxy injects the key as a header; browsers never hold it
    with TestClient(app).websocket_connect("/ws", headers={"X-API-Key": api_key}) as ws:
        assert ws.receive_json()["type"] == "connected"
    with pytest.raises(WebSocketDisconnect) as excinfo, TestClient(app).websocket_connect(
        "/ws", headers={"X-API-Key": "wrong"}
    ) as ws:
        ws.receive_json()
    assert excinfo.value.code == 1008
