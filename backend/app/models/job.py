from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class Job(Base):
    """A queued or running indexing run (INDEX_WORKERS=external): no claimed_by means queued"""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, nullable=False, index=True)
    force_reprocess = Column(Boolean, nullable=False, default=False)
    incremental = Column(Boolean, nullable=False, default=False)
    claimed_by = Column(String(200), nullable=True)  # the worker's host:pid
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
