import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from app.core.security import api_key_is_valid

logger = structlog.get_logger()

VALID_MESSAGE_TYPES = {"subscribe", "unsubscribe", "ping"}
SEND_TIMEOUT_SECONDS = 5  # a client that stops reading must not stall a processing run

# Browsers can't set headers on a WebSocket, so the key rides in a subprotocol
# (hex, to stay a valid token) rather than the URL, where access logs would keep it
SUBPROTOCOL = "codesage"
KEY_SUBPROTOCOL_PREFIX = "codesage.key."


def _key_from_subprotocols(protocols: list[str]) -> str | None:
    for protocol in protocols:
        if protocol.startswith(KEY_SUBPROTOCOL_PREFIX):
            try:
                return bytes.fromhex(protocol.removeprefix(KEY_SUBPROTOCOL_PREFIX)).decode()
            except ValueError:  # bad hex or bad UTF-8
                return None
    return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _error_frame(message: str) -> dict[str, Any]:
    return {"type": "error", "data": {"message": message}}


class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        # Store active connections
        self.active_connections: set[WebSocket] = set()
        # Store connections by repository ID for targeted updates
        self.repository_connections: dict[int, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, subprotocol: str | None = None):
        """Accept a new WebSocket connection"""
        await websocket.accept(subprotocol=subprotocol)
        self.active_connections.add(websocket)
        logger.info(
            "WebSocket connection established",
            total_connections=len(self.active_connections),
        )

    async def disconnect(self, websocket: WebSocket):
        """Remove a connection and all of its repository subscriptions"""
        self.active_connections.discard(websocket)

        for repo_id in list(self.repository_connections):
            connections = self.repository_connections[repo_id]
            connections.discard(websocket)
            if not connections:
                del self.repository_connections[repo_id]

        logger.info(
            "WebSocket connection closed",
            total_connections=len(self.active_connections),
        )

    async def _drop_dead(self, websocket: WebSocket):
        """Disconnect a failed socket and close it, ignoring close errors"""
        await self.disconnect(websocket)
        with contextlib.suppress(Exception):
            await websocket.close()

    async def subscribe_to_repository(self, websocket: WebSocket, repository_id: int):
        """Subscribe a WebSocket to updates for a specific repository"""
        self.repository_connections.setdefault(repository_id, set()).add(websocket)
        logger.info("WebSocket subscribed to repository", repository_id=repository_id)

    async def unsubscribe_from_repository(
        self, websocket: WebSocket, repository_id: int
    ):
        """Stop delivering a repository's updates to a WebSocket"""
        connections = self.repository_connections.get(repository_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            del self.repository_connections[repository_id]

    async def _send_to(self, connections: set[WebSocket], message: dict):
        payload = json.dumps(message)
        # Iterate a snapshot: sends await, and the live sets can change meanwhile
        for connection in list(connections):
            try:
                await asyncio.wait_for(connection.send_text(payload), SEND_TIMEOUT_SECONDS)
            except Exception as e:
                logger.warning("Failed to send message to WebSocket", error=str(e))
                await self._drop_dead(connection)

    async def broadcast_to_repository(self, repository_id: int, message: dict):
        """Broadcast a message to all clients subscribed to a specific repository"""
        connections = self.repository_connections.get(repository_id)
        if not connections:
            return
        await self._send_to(set(connections), message)

    async def send_repository_status(
        self,
        repository_id: int,
        status: str,
        name: str | None = None,
        processed_files: int = 0,
        total_files: int = 0,
        **kwargs,
    ):
        """Send repository status update to subscribed clients"""
        data: dict[str, Any] = {
            "repository_id": repository_id,
            "status": status,
            "name": name,
            "processed_files": processed_files,
            "total_files": total_files,
            "timestamp": _now_iso(),
        }
        for key in ("message", "error"):
            if kwargs.get(key) is not None:
                data[key] = kwargs[key]
        await self.broadcast_to_repository(
            repository_id, {"type": "repository_status", "data": data}
        )

    def get_connection_count(self) -> int:
        """Get the number of active connections"""
        return len(self.active_connections)


# Global WebSocket manager instance
websocket_manager = WebSocketManager()


def _parse_client_message(raw: str) -> tuple[dict | None, str | None]:
    """Return (message, None) if valid, else (None, error text)."""
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None, "Invalid JSON"
    if not isinstance(message, dict):
        return None, "Message must be a JSON object"
    msg_type = message.get("type")
    if not isinstance(msg_type, str) or msg_type not in VALID_MESSAGE_TYPES:
        return None, "Unknown message type"
    if msg_type in ("subscribe", "unsubscribe"):
        repo_id = message.get("repository_id")
        if isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id <= 0:
            return None, "repository_id must be a positive integer"
    return message, None


async def _send_json(websocket: WebSocket, frame: dict):
    await websocket.send_text(json.dumps(frame))


async def repository_status_websocket(websocket: WebSocket):
    """WebSocket endpoint for repository status updates"""
    # Browsers send the key in a subprotocol; the prod nginx proxy sends the header
    offered = websocket.scope.get("subprotocols", [])
    key = _key_from_subprotocols(offered) or websocket.headers.get("x-api-key")
    subprotocol = SUBPROTOCOL if SUBPROTOCOL in offered else None
    if not api_key_is_valid(key):
        # Accept first: a close before accept reaches browsers as 1006, and only
        # 1008 tells the client that retrying can't help
        await websocket.accept(subprotocol=subprotocol)
        await websocket.close(code=1008)
        return

    await websocket_manager.connect(websocket, subprotocol)

    try:
        await _send_json(
            websocket,
            {
                "type": "connected",
                "data": {
                    "message": "Connected to CodeSage real-time updates",
                    "timestamp": _now_iso(),
                },
            },
        )

        while True:
            raw = await websocket.receive_text()
            message, error = _parse_client_message(raw)
            if error is not None or message is None:
                await _send_json(websocket, _error_frame(error or "Invalid message"))
                continue

            msg_type = message["type"]
            if msg_type == "ping":
                await _send_json(websocket, {"type": "pong"})
            elif msg_type == "subscribe":
                repository_id = message["repository_id"]
                await websocket_manager.subscribe_to_repository(
                    websocket, repository_id
                )
                await _send_json(
                    websocket,
                    {"type": "subscribed", "data": {"repository_id": repository_id}},
                )
            else:  # unsubscribe
                repository_id = message["repository_id"]
                await websocket_manager.unsubscribe_from_repository(
                    websocket, repository_id
                )
                await _send_json(
                    websocket,
                    {"type": "unsubscribed", "data": {"repository_id": repository_id}},
                )

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
    finally:
        await websocket_manager.disconnect(websocket)
