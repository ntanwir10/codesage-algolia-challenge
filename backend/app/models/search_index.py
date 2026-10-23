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


class SearchIndex(Base):
    """Model for search index entries (Algolia integration)"""

    __tablename__ = "search_indexes"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(
        Integer, ForeignKey("repositories.id"), nullable=False, index=True
    )
    algolia_object_id = Column(String(255), nullable=False, unique=True, index=True)
    entity_type = Column(
        String(50), nullable=False, index=True
    )  # function, class, variable, etc.
    entity_name = Column(String(255), nullable=False, index=True)
    file_path = Column(String(1000), nullable=False)
    line_number = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    search_metadata = Column(JSON, nullable=True)
    is_indexed = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    indexed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    repository = relationship("Repository", back_populates="search_indexes")

    def __repr__(self):
        return f"<SearchIndex(id={self.id}, entity='{self.entity_name}', type='{self.entity_type}')>"
