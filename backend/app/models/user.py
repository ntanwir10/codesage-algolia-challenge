from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    """Model for users"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=True, index=True)
    full_name = Column(String(255), nullable=True)

    # Authentication
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Profile
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    github_username = Column(String(100), nullable=True)
    twitter_username = Column(String(100), nullable=True)

    # Preferences
    preferences = Column(JSON, nullable=True)

    # Usage tracking
    repositories_count = Column(Integer, default=0)
    searches_count = Column(Integer, default=0)
    last_active = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    verified_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', username='{self.username}')>"

    @property
    def display_name(self) -> str:
        """Get display name (full name or username or email)"""
        return self.full_name or self.username or self.email

    @property
    def is_new_user(self) -> bool:
        """Check if user is new (created in last 7 days)"""
        if not self.created_at:
            return False
        from datetime import datetime, timedelta

        return self.created_at > (datetime.utcnow() - timedelta(days=7))
