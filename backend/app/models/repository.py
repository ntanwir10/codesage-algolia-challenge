from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Repository(Base):
    """Model for code repositories"""

    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    url = Column(String(500), nullable=True, unique=True)
    branch = Column(String(100), nullable=True)  # None: the repository's default branch
    language = Column(String(50), nullable=True, index=True)
    framework = Column(String(100), nullable=True, index=True)

    # Processing status
    status = Column(
        String(50), default="pending", index=True
    )  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)

    # Statistics
    total_files = Column(Integer, default=0)
    total_lines = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    code_files = relationship(
        "CodeFile", back_populates="repository", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Repository(id={self.id}, name='{self.name}', status='{self.status}')>"

    @property
    def processing_progress(self) -> float:
        """Calculate processing progress percentage"""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100
