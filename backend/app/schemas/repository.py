from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.services.github_service import is_valid_branch, parse_repository_url, to_https_url

RepositoryStatus = Literal["pending", "processing", "completed", "failed"]


class RepositoryBase(BaseModel):
    """Base repository schema"""

    name: str = Field(default="", max_length=255, description="Repository name")
    description: str | None = Field(None, description="Repository description")
    url: str | None = Field(None, max_length=500, description="Repository URL")
    branch: str | None = Field(
        default=None, max_length=100, description="Branch to index; empty means the repository's default branch"
    )
    language: str | None = Field(None, max_length=50, description="Primary programming language")
    framework: str | None = Field(None, max_length=100, description="Primary framework")


class RepositoryCreate(RepositoryBase):
    """Schema for creating a repository"""

    url: str = Field(..., max_length=500, description="GitHub repository URL")

    # The REST API takes github.com only; the MCP tool sets this to accept any https git host
    any_host: ClassVar[bool] = False

    @field_validator("url", mode="before")
    @classmethod
    def url_to_https(cls, url):
        return to_https_url(url) if isinstance(url, str) else url

    @field_validator("url")
    @classmethod
    def url_is_valid(cls, url: str) -> str:
        try:
            host, _, _ = parse_repository_url(url)
        except ValueError as e:
            raise PydanticCustomError("invalid_url", str(e)) from e
        if not cls.any_host and host != "github.com":
            raise PydanticCustomError("invalid_url", "Invalid GitHub URL (host must be github.com): {url}", {"url": url})
        return url

    @field_validator("branch")
    @classmethod
    def branch_is_valid(cls, branch: str | None) -> str | None:
        if branch and not is_valid_branch(branch):
            raise PydanticCustomError("invalid_branch", "Invalid branch name")
        return branch

    @model_validator(mode="after")
    def normalise(self) -> "RepositoryCreate":
        host, path, url_branch = parse_repository_url(self.url)
        self.url = f"https://{host}/{path}"
        # An explicit empty branch means the default one, even with a /tree/<branch> URL;
        # an omitted or null branch falls back to the URL's. Stored as null, like an update does
        if self.branch is None:
            self.branch = url_branch
        self.branch = self.branch or None
        if not self.name.strip():
            # GitHub keeps owner/repo; other hosts are prefixed so names don't collide
            self.name = path if host == "github.com" else f"{host}/{path}"
        # Derived values skip the field limits; without this the row could not be listed back
        if self.branch and len(self.branch) > 100:
            raise PydanticCustomError("branch_too_long", "Branch name from the URL is too long (max 100 characters)")
        if len(self.name) > 255:
            raise PydanticCustomError("name_too_long", "Repository name from the URL is too long (max 255 characters)")
        return self


class AnyHostRepositoryCreate(RepositoryCreate):
    """RepositoryCreate for the MCP tool: any https git host"""

    any_host: ClassVar[bool] = True


class RepositoryUpdate(BaseModel):
    """Schema for updating a repository"""

    name: str | None = Field(None, max_length=255)
    description: str | None = None
    branch: str | None = Field(None, max_length=100)
    language: str | None = Field(None, max_length=50)
    framework: str | None = Field(None, max_length=100)

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
