from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class FileBase(BaseModel):
    """Base file schema"""

    file_path: str = Field(..., description="File path")
    file_name: str = Field(..., description="File name")
    language: Optional[str] = Field(None, description="Programming language")


class FileResponse(FileBase):
    """Schema for file listing responses"""

    id: int = Field(..., description="File ID")
    file_extension: Optional[str] = Field(None, description="File extension")
    line_count: int = Field(default=0, description="Number of lines")
    char_count: int = Field(default=0, description="Number of characters")
    function_count: int = Field(default=0, description="Number of functions")
    class_count: int = Field(default=0, description="Number of classes")
    is_parsed: bool = Field(default=False, description="Whether file is parsed")
    is_analyzed: bool = Field(default=False, description="Whether file is analyzed")
    is_indexed: bool = Field(default=False, description="Whether file is indexed")
    complexity_score: Optional[int] = Field(None, description="Complexity score (1-10)")
    maintainability_score: Optional[int] = Field(
        None, description="Maintainability score (1-10)"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        from_attributes = True


class EntityResponse(BaseModel):
    """Schema for code entity responses"""

    id: int = Field(..., description="Entity ID")
    name: str = Field(..., description="Entity name")
    entity_type: str = Field(
        ..., description="Entity type (function, class, variable, etc.)"
    )
    full_name: Optional[str] = Field(None, description="Full qualified name")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    signature: Optional[str] = Field(None, description="Function/method signature")
    docstring: Optional[str] = Field(None, description="Documentation string")
    summary: Optional[str] = Field(None, description="AI-generated summary")
    complexity_score: Optional[int] = Field(None, description="Complexity score (1-10)")

    class Config:
        from_attributes = True


class FileContentResponse(FileResponse):
    """Schema for file content responses"""

    content: Optional[str] = Field(None, description="File content")
    entities: List[EntityResponse] = Field(
        default_factory=list, description="Code entities in file"
    )
