from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime


class SearchQuery(BaseModel):
    """Schema for search queries"""

    query: str = Field(..., min_length=1, description="Search query")
    repository_id: Optional[int] = Field(
        None, description="Limit search to specific repository"
    )
    filters: Optional[str] = Field(None, description="Search filters")
    page: int = Field(default=0, ge=0, description="Page number")
    per_page: int = Field(default=20, ge=1, le=100, description="Results per page")
    language: Optional[str] = Field(None, description="Filter by programming language")
    entity_type: Optional[str] = Field(
        None, description="Filter by entity type (function, class, etc.)"
    )
    sort_by: Optional[str] = Field(default="relevance", description="Sort order")


class SearchHit(BaseModel):
    """Schema for individual search results"""

    id: str = Field(..., description="Result ID")
    title: str = Field(..., description="Result title")
    content: str = Field(..., description="Result content")
    summary: Optional[str] = Field(None, description="AI-generated summary")
    entity_type: str = Field(..., description="Entity type")
    file_path: str = Field(..., description="File path")
    line_number: Optional[int] = Field(None, description="Line number")
    language: Optional[str] = Field(None, description="Programming language")
    repository_id: int = Field(..., description="Repository ID")
    repository_name: Optional[str] = Field(None, description="Repository name")
    score: float = Field(..., description="Relevance score")
    highlighted: Dict[str, List[str]] = Field(
        default_factory=dict, description="Highlighted snippets"
    )


class SearchResponse(BaseModel):
    """Schema for search responses"""

    query: str = Field(..., description="Original query")
    hits: List[SearchHit] = Field(..., description="Search results")
    total_hits: int = Field(..., description="Total number of results")
    processing_time: float = Field(..., description="Processing time in seconds")
    page: int = Field(..., description="Current page")
    per_page: int = Field(..., description="Results per page")
    has_more: bool = Field(default=False, description="Whether there are more results")
    facets: Dict[str, Any] = Field(default_factory=dict, description="Search facets")
    suggestions: List[str] = Field(
        default_factory=list, description="Query suggestions"
    )


class SearchSuggestion(BaseModel):
    """Schema for search suggestions"""

    text: str = Field(..., description="Suggestion text")
    score: float = Field(..., description="Suggestion score")
    type: str = Field(..., description="Suggestion type")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
