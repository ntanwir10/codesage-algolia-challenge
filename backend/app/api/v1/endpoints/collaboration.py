from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Query,
)
from sqlalchemy.orm import Session
import structlog
import json

from app.core.database import get_db
from app.models.session import Session as UserSession
from app.schemas.collaboration import (
    RoomCreate,
    RoomResponse,
    ParticipantResponse,
    CursorPosition,
    CollaborationEvent,
)
from app.services.collaboration_service import CollaborationService
from app.services.websocket_manager import WebSocketManager

logger = structlog.get_logger()
router = APIRouter()

# WebSocket manager for real-time communication
websocket_manager = WebSocketManager()


@router.post("/rooms", response_model=RoomResponse, status_code=201)
async def create_collaboration_room(
    room_data: RoomCreate, db: Session = Depends(get_db)
):
    """Create a new collaboration room"""
    try:
        collaboration_service = CollaborationService(db)
        room = await collaboration_service.create_room(room_data)
        logger.info("Collaboration room created", room_id=room.room_id)
        return room
    except Exception as e:
        logger.error("Failed to create room", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/rooms/{room_id}", response_model=RoomResponse)
async def get_collaboration_room(room_id: str, db: Session = Depends(get_db)):
    """Get collaboration room details"""
    collaboration_service = CollaborationService(db)
    room = await collaboration_service.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.get("/rooms/{room_id}/participants", response_model=List[ParticipantResponse])
async def get_room_participants(room_id: str, db: Session = Depends(get_db)):
    """Get active participants in a collaboration room"""
    collaboration_service = CollaborationService(db)
    participants = await collaboration_service.get_participants(room_id)
    return participants


@router.post("/rooms/{room_id}/join")
async def join_collaboration_room(
    room_id: str,
    session_id: str,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Join a collaboration room"""
    try:
        collaboration_service = CollaborationService(db)
        result = await collaboration_service.join_room(room_id, session_id, user_id)
        logger.info("User joined room", room_id=room_id, session_id=session_id)
        return result
    except Exception as e:
        logger.error("Failed to join room", room_id=room_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rooms/{room_id}/leave")
async def leave_collaboration_room(
    room_id: str, session_id: str, db: Session = Depends(get_db)
):
    """Leave a collaboration room"""
    try:
        collaboration_service = CollaborationService(db)
        await collaboration_service.leave_room(room_id, session_id)
        logger.info("User left room", room_id=room_id, session_id=session_id)
        return {"message": "Left room successfully"}
    except Exception as e:
        logger.error("Failed to leave room", room_id=room_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rooms/{room_id}/cursor")
async def update_cursor_position(
    room_id: str,
    cursor_data: CursorPosition,
    session_id: str,
    db: Session = Depends(get_db),
):
    """Update cursor position for real-time collaboration"""
    try:
        collaboration_service = CollaborationService(db)
        await collaboration_service.update_cursor(room_id, session_id, cursor_data)

        # Broadcast cursor update to other participants
        event = CollaborationEvent(
            type="cursor_update",
            room_id=room_id,
            session_id=session_id,
            data=cursor_data.dict(),
        )
        await websocket_manager.broadcast_to_room(
            room_id, event.dict(), exclude_session=session_id
        )

        return {"message": "Cursor position updated"}
    except Exception as e:
        logger.error("Failed to update cursor", room_id=room_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/rooms/{room_id}/activity")
async def get_room_activity(
    room_id: str,
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """Get recent activity in a collaboration room"""
    try:
        collaboration_service = CollaborationService(db)
        activity = await collaboration_service.get_room_activity(room_id, hours)
        return activity
    except Exception as e:
        logger.error("Failed to get room activity", room_id=room_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.websocket("/ws/{room_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket, room_id: str, session_id: str, db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time collaboration"""
    await websocket_manager.connect(websocket, room_id, session_id)

    try:
        # Update session with WebSocket connection
        session = (
            db.query(UserSession).filter(UserSession.session_id == session_id).first()
        )
        if session:
            session.is_websocket_connected = True
            session.websocket_id = f"{room_id}:{session_id}"
            db.commit()

        # Notify room that user joined
        join_event = CollaborationEvent(
            type="user_joined",
            room_id=room_id,
            session_id=session_id,
            data={"session_id": session_id},
        )
        await websocket_manager.broadcast_to_room(
            room_id, join_event.dict(), exclude_session=session_id
        )

        # Keep connection alive and handle messages
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Process different message types
            if message.get("type") == "cursor_update":
                await websocket_manager.broadcast_to_room(
                    room_id, message, exclude_session=session_id
                )
            elif message.get("type") == "file_changed":
                await websocket_manager.broadcast_to_room(
                    room_id, message, exclude_session=session_id
                )
            elif message.get("type") == "annotation":
                # Handle code annotations
                await websocket_manager.broadcast_to_room(
                    room_id, message, exclude_session=session_id
                )

            logger.debug(
                "WebSocket message processed",
                room_id=room_id,
                session_id=session_id,
                type=message.get("type"),
            )

    except WebSocketDisconnect:
        websocket_manager.disconnect(room_id, session_id)

        # Update session status
        session = (
            db.query(UserSession).filter(UserSession.session_id == session_id).first()
        )
        if session:
            session.is_websocket_connected = False
            session.websocket_id = None
            db.commit()

        # Notify room that user left
        leave_event = CollaborationEvent(
            type="user_left",
            room_id=room_id,
            session_id=session_id,
            data={"session_id": session_id},
        )
        await websocket_manager.broadcast_to_room(room_id, leave_event.dict())

        logger.info("WebSocket disconnected", room_id=room_id, session_id=session_id)

    except Exception as e:
        logger.error(
            "WebSocket error", room_id=room_id, session_id=session_id, error=str(e)
        )
        websocket_manager.disconnect(room_id, session_id)


@router.get("/sessions/{session_id}/status")
async def get_session_status(session_id: str, db: Session = Depends(get_db)):
    """Get current session status and collaboration state"""
    session = db.query(UserSession).filter(UserSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "is_active": session.is_active,
        "is_collaborative": session.is_collaborative,
        "room_id": session.room_id,
        "is_websocket_connected": session.is_websocket_connected,
        "active_repository_id": session.active_repository_id,
        "active_file_path": session.active_file_path,
        "last_activity": (
            session.last_activity.isoformat() if session.last_activity else None
        ),
    }


@router.post("/annotations")
async def create_code_annotation(
    room_id: str,
    file_path: str,
    line_number: int,
    annotation: str,
    session_id: str,
    db: Session = Depends(get_db),
):
    """Create a code annotation for collaborative discussion"""
    try:
        collaboration_service = CollaborationService(db)
        annotation_obj = await collaboration_service.create_annotation(
            room_id, file_path, line_number, annotation, session_id
        )

        # Broadcast annotation to room participants
        event = CollaborationEvent(
            type="annotation_created",
            room_id=room_id,
            session_id=session_id,
            data={
                "file_path": file_path,
                "line_number": line_number,
                "annotation": annotation,
                "annotation_id": annotation_obj.id,
            },
        )
        await websocket_manager.broadcast_to_room(room_id, event.dict())

        return annotation_obj
    except Exception as e:
        logger.error("Failed to create annotation", room_id=room_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
