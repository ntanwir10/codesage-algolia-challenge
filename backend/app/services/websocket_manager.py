from fastapi import WebSocket
from typing import Dict, List
import json
import structlog

logger = structlog.get_logger()


class WebSocketManager:
    """Manager for WebSocket connections and real-time communication"""

    def __init__(self):
        # Dict[room_id, Dict[session_id, WebSocket]]
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, session_id: str):
        """Accept WebSocket connection and add to room"""
        await websocket.accept()

        if room_id not in self.active_connections:
            self.active_connections[room_id] = {}

        self.active_connections[room_id][session_id] = websocket
        logger.info("WebSocket connected", room_id=room_id, session_id=session_id)

    def disconnect(self, room_id: str, session_id: str):
        """Remove WebSocket connection from room"""
        if room_id in self.active_connections:
            if session_id in self.active_connections[room_id]:
                del self.active_connections[room_id][session_id]

                # Clean up empty rooms
                if not self.active_connections[room_id]:
                    del self.active_connections[room_id]

                logger.info(
                    "WebSocket disconnected", room_id=room_id, session_id=session_id
                )

    async def send_personal_message(self, message: str, room_id: str, session_id: str):
        """Send message to specific session"""
        if room_id in self.active_connections:
            if session_id in self.active_connections[room_id]:
                websocket = self.active_connections[room_id][session_id]
                await websocket.send_text(message)

    async def broadcast_to_room(
        self, room_id: str, message: dict, exclude_session: str = None
    ):
        """Broadcast message to all connections in a room"""
        if room_id in self.active_connections:
            message_str = json.dumps(message)
            disconnected_sessions = []

            for session_id, websocket in self.active_connections[room_id].items():
                if exclude_session and session_id == exclude_session:
                    continue

                try:
                    await websocket.send_text(message_str)
                except Exception as e:
                    logger.error(
                        "Failed to send WebSocket message",
                        session_id=session_id,
                        error=str(e),
                    )
                    disconnected_sessions.append(session_id)

            # Clean up disconnected sessions
            for session_id in disconnected_sessions:
                self.disconnect(room_id, session_id)

    def get_room_connections(self, room_id: str) -> List[str]:
        """Get list of session IDs in a room"""
        if room_id in self.active_connections:
            return list(self.active_connections[room_id].keys())
        return []

    def get_connection_count(self, room_id: str) -> int:
        """Get number of active connections in a room"""
        if room_id in self.active_connections:
            return len(self.active_connections[room_id])
        return 0
