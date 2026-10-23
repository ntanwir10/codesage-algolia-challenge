import json

import structlog
from fastapi import WebSocket, WebSocketDisconnect

logger = structlog.get_logger()


class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        # Store active connections
        self.active_connections: set[WebSocket] = set()
        # Store connections by repository ID for targeted updates
        self.repository_connections: dict[int, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(
            "WebSocket connection established",
            total_connections=len(self.active_connections),
        )

    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

            # Remove from repository-specific connections
            for repo_id, connections in self.repository_connections.items():
                connections.discard(websocket)

            # Clean up empty repository connection sets
            self.repository_connections = {
                repo_id: connections
                for repo_id, connections in self.repository_connections.items()
                if connections
            }

        logger.info(
            "WebSocket connection closed",
            total_connections=len(self.active_connections),
        )

    async def subscribe_to_repository(self, websocket: WebSocket, repository_id: int):
        """Subscribe a WebSocket to updates for a specific repository"""
        if repository_id not in self.repository_connections:
            self.repository_connections[repository_id] = set()

        self.repository_connections[repository_id].add(websocket)
        logger.info("WebSocket subscribed to repository", repository_id=repository_id)

    async def broadcast_to_all(self, message: dict):
        """Broadcast a message to all connected clients"""
        if not self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.warning("Failed to send message to WebSocket", error=str(e))
                disconnected.add(connection)

        # Clean up disconnected connections
        for connection in disconnected:
            await self.disconnect(connection)

    async def broadcast_to_repository(self, repository_id: int, message: dict):
        """Broadcast a message to all clients subscribed to a specific repository"""
        if repository_id not in self.repository_connections:
            return

        connections = self.repository_connections[repository_id].copy()
        disconnected = set()

        for connection in connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(
                    "Failed to send repository message to WebSocket",
                    repository_id=repository_id,
                    error=str(e),
                )
                disconnected.add(connection)

        # Clean up disconnected connections
        for connection in disconnected:
            await self.disconnect(connection)

    async def send_repository_status(self, repository_id: int, status: str, **kwargs):
        """Send repository status update to subscribed clients"""
        message = {
            "type": "repository_status",
            "repository_id": repository_id,
            "status": status,
            "timestamp": "2024-01-01T00:00:00Z",  # Would be actual timestamp
            **kwargs,
        }
        await self.broadcast_to_repository(repository_id, message)

    def get_connection_count(self) -> int:
        """Get the number of active connections"""
        return len(self.active_connections)

    def get_repository_connection_count(self, repository_id: int) -> int:
        """Get the number of connections for a specific repository"""
        return len(self.repository_connections.get(repository_id, set()))


# Global WebSocket manager instance
websocket_manager = WebSocketManager()


async def repository_status_websocket(websocket: WebSocket):
    """WebSocket endpoint for repository status updates"""
    await websocket_manager.connect(websocket)

    try:
        while True:
            # Wait for messages from the client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)

                # Handle subscription to repository updates
                if message.get("type") == "subscribe" and "repository_id" in message:
                    repository_id = int(message["repository_id"])
                    await websocket_manager.subscribe_to_repository(
                        websocket, repository_id
                    )

                    # Send confirmation
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "subscription_confirmed",
                                "repository_id": repository_id,
                            }
                        )
                    )

                # Handle ping/pong for connection health
                elif message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

            except json.JSONDecodeError:
                logger.warning("Received invalid JSON from WebSocket client")
            except ValueError as e:
                logger.warning(
                    "Invalid repository ID in WebSocket message", error=str(e)
                )

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
    finally:
        await websocket_manager.disconnect(websocket)


async def websocket_health():
    """WebSocket health check endpoint"""
    return {
        "status": "healthy",
        "active_connections": websocket_manager.get_connection_count(),
        "repository_subscriptions": len(websocket_manager.repository_connections),
        "service": "websocket",
    }
