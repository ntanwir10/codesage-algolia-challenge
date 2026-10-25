from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.github_service import parse_github_url

RepositoryStatus = Literal["pending", "processing", "completed", "failed"]


class RepositoryBase(BaseModel):
    """Base repository schema"""

    name: str = Field(default="", description="Repository name")
    description: str | None = Field(None, description="Repository description")
    url: str | None = Field(None, description="Repository URL")
    branch: str | None = Field(
        default=None, description="Branch to index; empty means the repository's default branch"
    )
    language: str | None = Field(None, description="Primary programming language")
    framework: str | None = Field(None, description="Primary framework")


class RepositoryCreate(RepositoryBase):
    """Schema for creating a repository"""

    url: str = Field(..., description="GitHub repository URL")

    @model_validator(mode="after")
    def normalise(self) -> "RepositoryCreate":
        owner, repo, url_branch = parse_github_url(self.url)
        self.url = f"https://github.com/{owner}/{repo}"
        if url_branch and not self.branch:
            self.branch = url_branch
        if not self.name.strip():
            self.name = f"{owner}/{repo}"
        return self


class RepositoryUpdate(BaseModel):
    """Schema for updating a repository"""

    name: str | None = None
    description: str | None = None
    branch: str | None = None
    language: str | None = None
    framework: str | None = None


class RepositoryResponse(RepositoryBase):
    """Schema for repository responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: RepositoryStatus = Field(..., description="Processing status")
    error_message: str | None = Field(
        None, description="Why the last run failed, or what a completed run left out"
    )
    total_files: int = Field(default=0, description="Total number of files")
    processed_files: int = Field(default=0, description="Number of processed files")
    total_lines: int = Field(default=0, description="Total lines of code")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")
    processed_at: datetime | None = Field(
        None, description="Processing completion timestamp"
    )
