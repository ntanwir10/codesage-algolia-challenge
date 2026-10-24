from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class CodeFile(Base):
    """Model for code files within repositories"""

    __tablename__ = "code_files"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(
        Integer, ForeignKey("repositories.id"), nullable=False, index=True
    )
    file_path = Column(String(1000), nullable=False, index=True)
    content = Column(Text, nullable=False)
    language = Column(String(50), nullable=True, index=True)
    line_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    repository = relationship("Repository", back_populates="code_files")
    entities = relationship(
        "CodeEntity", back_populates="code_file", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<CodeFile(id={self.id}, path='{self.file_path}', language='{self.language}')>"
