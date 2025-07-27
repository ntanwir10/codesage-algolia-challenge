from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class Session(Base):
    """Model for user sessions and collaboration"""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), nullable=False, unique=True, index=True)
    user_id = Column(String(255), nullable=True, index=True)  # For authenticated users
    is_active = Column(Boolean, default=True)
    is_collaborative = Column(Boolean, default=False)
    room_id = Column(String(255), nullable=True, index=True)
    is_websocket_connected = Column(Boolean, default=False)
    websocket_id = Column(String(255), nullable=True)
    active_repository_id = Column(Integer, nullable=True)
    active_file_path = Column(String(1000), nullable=True)
    session_data = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_activity = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<Session(id={self.id}, session_id='{self.session_id}', active={self.is_active})>"
