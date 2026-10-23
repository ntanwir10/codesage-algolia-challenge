from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class CodeEntity(Base):
    """Model for code entities (functions, classes, variables, etc.)"""

    __tablename__ = "code_entities"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("code_files.id"), nullable=False, index=True)
    repository_id = Column(
        Integer, ForeignKey("repositories.id"), nullable=False, index=True
    )

    # Entity information
    entity_type = Column(
        String(50), nullable=False, index=True
    )  # function, class, variable, etc.
    entity_name = Column(String(255), nullable=False, index=True)
    full_name = Column(String(500), nullable=True, index=True)  # namespace.class.method

    # Location information
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    start_column = Column(Integer, nullable=True)
    end_column = Column(Integer, nullable=True)

    # Content and analysis
    signature = Column(
        Text, nullable=True
    )  # Function signature, class definition, etc.
    docstring = Column(Text, nullable=True)
    complexity_score = Column(Integer, nullable=True)  # Cyclomatic complexity
    is_public = Column(Boolean, default=True)
    is_async = Column(Boolean, default=False)

    # Metadata
    entity_metadata = Column(JSON, nullable=True)  # Additional metadata for analysis

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    code_file = relationship("CodeFile", back_populates="entities")
    repository = relationship("Repository")

    def __repr__(self):
        return f"<CodeEntity(id={self.id}, name='{self.entity_name}', type='{self.entity_type}')>"
