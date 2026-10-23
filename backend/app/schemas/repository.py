from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepositoryBase(BaseModel):
    """Base repository schema"""

    name: str = Field(..., description="Repository name")
    description: str | None = Field(None, description="Repository description")
    url: str | None = Field(None, description="Repository URL")
    branch: str | None = Field(
        default=None, description="Branch to index; empty means the repository's default branch"
    )
    language: str | None = Field(None, description="Primary programming language")
    framework: str | None = Field(None, description="Primary framework")


class RepositoryCreate(RepositoryBase):
    """Schema for creating a repository"""

    pass


class RepositoryUpdate(BaseModel):
    """Schema for updating a repository"""

    name: str | None = None
    description: str | None = None
    url: str | None = None
    branch: str | None = None
    language: str | None = None
    framework: str | None = None
    status: str | None = None


class RepositoryResponse(RepositoryBase):
    """Schema for repository responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str = Field(..., description="Processing status")
    total_files: int = Field(default=0, description="Total number of files")
    processed_files: int = Field(default=0, description="Number of processed files")
    total_lines: int = Field(default=0, description="Total lines of code")
    security_score: int | None = Field(None, description="Security score (0-100)")
    vulnerability_count: int = Field(
        default=0, description="Number of vulnerabilities found"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")
    processed_at: datetime | None = Field(
        None, description="Processing completion timestamp"
    )
