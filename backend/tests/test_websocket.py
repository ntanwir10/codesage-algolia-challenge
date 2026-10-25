import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.websocket_service import WebSocketManager, websocket_manager


class FakeWebSocket:
    def __init__(self, fail_send: bool = False, fail_close: bool = False):
        self.sent: list[dict] = []
        self.closed = False
        self.fail_send = fail_send
        self.fail_close = fail_close

    async def send_text(self, text: str):
        if self.fail_send:
            raise RuntimeError("socket dead")
        self.sent.append(json.loads(text))

    async def close(self):
        self.closed = True
        if self.fail_close:
            raise RuntimeError("already closed")


@pytest.fixture(autouse=True)
def clean_global_manager():
    yield
    websocket_manager.active_connections.clear()
    websocket_manager.repository_connections.clear()


def _status(manager, repo_id=7, **kw):
    return manager.send_repository_status(
        repository_id=repo_id,
        status="processing",
        name="acme/widgets",
        processed_files=3,
        total_files=10,
        **kw,
    )


# ---- TestClient (real /ws route) ----


def test_connected_frame_on_connect():
    client = TestClient(app, base_url="http://localhost")
    with client.websocket_connect("ws://localhost/ws") as ws:
        frame = ws.receive_json()
    assert frame["type"] == "connected"
    assert isinstance(frame["data"], dict)


def test_subscribe_ping_unsubscribe_and_errors():
    client = TestClient(app, base_url="http://localhost")
    with client.websocket_connect("ws://localhost/ws") as ws:
        ws.receive_json()  # connected

        ws.send_json({"type": "subscribe", "repository_id": 5})
        assert ws.receive_json() == {
            "type": "subscribed",
            "data": {"repository_id": 5},
        }
        assert len(websocket_manager.repository_connections[5]) == 1

        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}

        ws.send_text("not json {")
        assert ws.receive_json()["type"] == "error"

        ws.send_text("[1, 2]")
        assert ws.receive_json()["type"] == "error"

        ws.send_json({"type": "bogus"})
        assert ws.receive_json()["type"] == "error"

        for bad in (0, -1, "5", None, True, 1.5):
            ws.send_json({"type": "subscribe", "repository_id": bad})
            frame = ws.receive_json()
            assert frame["type"] == "error"
            assert "message" in frame["data"]
        ws.send_json({"type": "subscribe"})
        assert ws.receive_json()["type"] == "error"

        ws.send_json({"type": "unsubscribe", "repository_id": 5})
        assert ws.receive_json()["type"] == "unsubscribed"
        assert not websocket_manager.repository_connections.get(5)
    # disconnect cleans up
    assert websocket_manager.get_connection_count() == 0


def test_status_delivery_over_real_websocket():
    client = TestClient(app, base_url="http://localhost")
    with client.websocket_connect("ws://localhost/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "subscribe", "repository_id": 42})
        ws.receive_json()
        asyncio.run(
            websocket_manager.send_repository_status(
                repository_id=42,
                status="completed",
                name="acme/widgets",
                processed_files=10,
                total_files=10,
                message="done",
            )
        )
        frame = ws.receive_json()
    assert frame["type"] == "repository_status"
    data = frame["data"]
    assert data["repository_id"] == 42
    assert data["status"] == "completed"
    assert data["name"] == "acme/widgets"
    assert data["processed_files"] == 10
    assert data["total_files"] == 10
    assert data["message"] == "done"
    assert "error" not in data
    assert datetime.fromisoformat(data["timestamp"]).year == datetime.now(UTC).year


# ---- Manager unit tests ----


async def test_envelope_and_timestamp():
    manager = WebSocketManager()
    ws = FakeWebSocket()
    manager.active_connections.add(ws)
    await manager.subscribe_to_repository(ws, 7)

    await _status(manager, error="boom")

    assert len(ws.sent) == 1
    frame = ws.sent[0]
    assert frame["type"] == "repository_status"
    data = frame["data"]
    assert data["repository_id"] == 7
    assert data["status"] == "processing"
    assert data["name"] == "acme/widgets"
    assert data["processed_files"] == 3
    assert data["total_files"] == 10
    assert data["error"] == "boom"
    ts = datetime.fromisoformat(data["timestamp"])
    assert ts.year == datetime.now(UTC).year
    assert abs((datetime.now(UTC) - ts).total_seconds()) < 5


async def test_only_subscribers_receive():
    manager = WebSocketManager()
    a, b = FakeWebSocket(), FakeWebSocket()
    manager.active_connections.update({a, b})
    await manager.subscribe_to_repository(a, 1)
    await manager.subscribe_to_repository(b, 2)
    await _status(manager, repo_id=1)
    assert len(a.sent) == 1
    assert b.sent == []


async def test_unsubscribe_stops_delivery():
    manager = WebSocketManager()
    ws = FakeWebSocket()
    manager.active_connections.add(ws)
    await manager.subscribe_to_repository(ws, 7)
    await manager.unsubscribe_from_repository(ws, 7)
    await _status(manager)
    assert ws.sent == []
    assert manager.repository_connections == {}


async def test_a_client_that_stops_reading_is_dropped_not_waited_on(monkeypatch):
    monkeypatch.setattr("app.services.websocket_service.SEND_TIMEOUT_SECONDS", 0.01)

    class StuckWebSocket(FakeWebSocket):
        async def send_text(self, text: str):
            await asyncio.Event().wait()  # the send buffer never drains

    manager = WebSocketManager()
    stuck, alive = StuckWebSocket(), FakeWebSocket()
    manager.active_connections.update({stuck, alive})
    await manager.subscribe_to_repository(stuck, 7)
    await manager.subscribe_to_repository(alive, 7)

    await asyncio.wait_for(_status(manager), 1)

    assert stuck not in manager.active_connections
    assert len(alive.sent) == 1


async def test_dead_socket_closed_and_removed_on_repository_broadcast():
    manager = WebSocketManager()
    dead, alive = FakeWebSocket(fail_send=True, fail_close=True), FakeWebSocket()
    manager.active_connections.update({dead, alive})
    await manager.subscribe_to_repository(dead, 7)
    await manager.subscribe_to_repository(alive, 7)

    await _status(manager)

    assert dead.closed
    assert dead not in manager.active_connections
    assert dead not in manager.repository_connections[7]
    assert len(alive.sent) == 1


async def test_broadcast_survives_set_mutation_during_send():
    manager = WebSocketManager()

    class Joiner(FakeWebSocket):
        async def send_text(self, text):
            await super().send_text(text)
            manager.active_connections.add(FakeWebSocket())
            await asyncio.sleep(0)

    sockets = [Joiner() for _ in range(3)]
    manager.active_connections.update(sockets)
    manager.repository_connections[1] = set(sockets)
    await manager.broadcast_to_repository(1, {"type": "x"})  # must not raise
    assert all(len(s.sent) == 1 for s in sockets)


async def test_disconnect_cleans_subscriptions():
    manager = WebSocketManager()
    ws = FakeWebSocket()
    manager.active_connections.add(ws)
    await manager.subscribe_to_repository(ws, 1)
    await manager.subscribe_to_repository(ws, 2)
    await manager.disconnect(ws)
    assert manager.get_connection_count() == 0
    assert manager.repository_connections == {}
