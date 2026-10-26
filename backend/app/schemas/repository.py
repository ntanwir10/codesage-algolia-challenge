from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.services.github_service import is_valid_branch, parse_github_url

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

    @field_validator("url")
    @classmethod
    def url_is_github(cls, url: str) -> str:
        try:
            parse_github_url(url)
        except ValueError as e:
            raise PydanticCustomError("invalid_url", str(e)) from e
        return url

    @field_validator("branch")
    @classmethod
    def branch_is_valid(cls, branch: str | None) -> str | None:
        if branch and not is_valid_branch(branch):
            raise PydanticCustomError("invalid_branch", "Invalid branch name")
        return branch

    @model_validator(mode="after")
    def normalise(self) -> "RepositoryCreate":
        owner, repo, url_branch = parse_github_url(self.url)
        self.url = f"https://github.com/{owner}/{repo}"
        # An explicit empty branch means the default one, even with a /tree/<branch> URL;
        # an omitted or null branch falls back to the URL's. Stored as null, like an update does
        if self.branch is None:
            self.branch = url_branch
        self.branch = self.branch or None
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

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, name: str | None) -> str:
        # The column is NOT NULL; omit the field to leave the name alone
        if name is None or not name.strip():
            raise ValueError("name cannot be empty")
        return name

    @field_validator("branch")
    @classmethod
    def branch_is_valid(cls, branch: str | None) -> str | None:
        if branch and not is_valid_branch(branch):
            raise ValueError("Invalid branch name")
        return branch or None  # empty means the default branch, the same as null


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
