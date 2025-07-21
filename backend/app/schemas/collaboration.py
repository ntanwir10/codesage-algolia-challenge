from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class RoomCreate(BaseModel):
    """Schema for creating collaboration rooms"""

    name: str = Field(..., description="Room name")
    repository_id: int = Field(..., description="Repository ID")
    created_by: str = Field(..., description="Creator session/user ID")
    description: Optional[str] = Field(None, description="Room description")


class RoomResponse(BaseModel):
    """Schema for collaboration room responses"""

    room_id: str = Field(..., description="Unique room ID")
    name: str = Field(..., description="Room name")
    repository_id: int = Field(..., description="Repository ID")
    created_by: str = Field(..., description="Creator session/user ID")
    participant_count: int = Field(
        default=0, description="Number of active participants"
    )
    is_active: bool = Field(default=True, description="Whether room is active")
    description: Optional[str] = Field(None, description="Room description")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )


class ParticipantResponse(BaseModel):
    """Schema for room participant responses"""

    session_id: str = Field(..., description="Participant session ID")
    user_id: Optional[int] = Field(None, description="User ID (if authenticated)")
    display_name: Optional[str] = Field(None, description="Display name")
    is_online: bool = Field(default=True, description="Whether participant is online")
    joined_at: datetime = Field(..., description="Join timestamp")
    last_activity: Optional[datetime] = Field(
        None, description="Last activity timestamp"
    )
    current_file: Optional[str] = Field(None, description="Currently viewing file")


class CursorPosition(BaseModel):
    """Schema for cursor position updates"""

    file_path: str = Field(..., description="File path")
    line: int = Field(..., ge=0, description="Line number")
    column: int = Field(..., ge=0, description="Column number")
    selection_start: Optional[Dict[str, int]] = Field(
        None, description="Selection start position"
    )
    selection_end: Optional[Dict[str, int]] = Field(
        None, description="Selection end position"
    )


class CollaborationEvent(BaseModel):
    """Schema for collaboration events"""

    type: str = Field(..., description="Event type")
    room_id: str = Field(..., description="Room ID")
    session_id: str = Field(..., description="Session ID")
    data: Dict[str, Any] = Field(..., description="Event data")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )
