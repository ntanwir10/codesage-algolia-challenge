from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class RepositoryBase(BaseModel):
    """Base repository schema"""

    name: str = Field(..., description="Repository name")
    description: Optional[str] = Field(None, description="Repository description")
    url: Optional[str] = Field(None, description="Repository URL")
    branch: str = Field(default="main", description="Repository branch")
    language: Optional[str] = Field(None, description="Primary programming language")
    framework: Optional[str] = Field(None, description="Primary framework")


class RepositoryCreate(RepositoryBase):
    """Schema for creating a repository"""

    pass


class RepositoryUpdate(BaseModel):
    """Schema for updating a repository"""

    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    branch: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None
    status: Optional[str] = None


class RepositoryResponse(RepositoryBase):
    """Schema for repository responses"""

    id: int
    status: str = Field(..., description="Processing status")
    total_files: int = Field(default=0, description="Total number of files")
    processed_files: int = Field(default=0, description="Number of processed files")
    total_lines: int = Field(default=0, description="Total lines of code")
    security_score: Optional[int] = Field(None, description="Security score (0-100)")
    vulnerability_count: int = Field(
        default=0, description="Number of vulnerabilities found"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    processed_at: Optional[datetime] = Field(
        None, description="Processing completion timestamp"
    )

    class Config:
        from_attributes = True
