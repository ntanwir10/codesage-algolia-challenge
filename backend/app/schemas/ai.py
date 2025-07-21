from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime


class CodeAnalysisRequest(BaseModel):
    """Schema for code analysis requests"""

    entity_id: int = Field(..., description="Code entity ID to analyze")
    analysis_type: str = Field(
        default="full", description="Type of analysis to perform"
    )
    include_suggestions: bool = Field(
        default=True, description="Include improvement suggestions"
    )
    include_security: bool = Field(
        default=True, description="Include security analysis"
    )


class SecurityIssue(BaseModel):
    """Schema for security issues"""

    severity: str = Field(
        ..., description="Issue severity (low, medium, high, critical)"
    )
    title: str = Field(..., description="Issue title")
    description: str = Field(..., description="Issue description")
    line_number: Optional[int] = Field(
        None, description="Line number where issue occurs"
    )
    recommendation: str = Field(..., description="Recommended fix")
    cwe_id: Optional[str] = Field(
        None, description="CWE (Common Weakness Enumeration) ID"
    )


class CodeAnalysisResponse(BaseModel):
    """Schema for code analysis responses"""

    entity_id: int = Field(..., description="Analyzed entity ID")
    summary: str = Field(..., description="AI-generated summary")
    complexity_score: int = Field(
        ..., ge=1, le=10, description="Complexity score (1-10)"
    )
    maintainability_score: int = Field(
        ..., ge=1, le=10, description="Maintainability score (1-10)"
    )
    suggestions: List[str] = Field(
        default_factory=list, description="Improvement suggestions"
    )
    security_issues: List[SecurityIssue] = Field(
        default_factory=list, description="Security issues found"
    )
    similar_entities: List[int] = Field(
        default_factory=list, description="Similar entity IDs"
    )
    analysis_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Analysis timestamp"
    )


class SecurityAnalysisResponse(BaseModel):
    """Schema for security analysis responses"""

    repository_id: int = Field(..., description="Repository ID")
    file_path: Optional[str] = Field(
        None, description="Specific file path (if applicable)"
    )
    security_score: int = Field(..., ge=0, le=100, description="Overall security score")
    risk_level: str = Field(..., description="Risk level (low, medium, high, critical)")
    issues: List[SecurityIssue] = Field(..., description="Security issues found")
    recommendations: List[str] = Field(..., description="Security recommendations")
    scan_timestamp: str = Field(..., description="Scan timestamp")


class SuggestionResponse(BaseModel):
    """Schema for AI suggestions"""

    type: str = Field(..., description="Suggestion type")
    title: str = Field(..., description="Suggestion title")
    description: str = Field(..., description="Suggestion description")
    entity_id: Optional[int] = Field(None, description="Related entity ID")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class ConversationRequest(BaseModel):
    """Schema for AI conversation requests"""

    message: str = Field(..., min_length=1, description="User message")
    repository_id: Optional[int] = Field(None, description="Repository context")
    session_id: Optional[str] = Field(None, description="Conversation session ID")
    context: List[str] = Field(
        default_factory=list, description="Previous conversation context"
    )


class ConversationResponse(BaseModel):
    """Schema for AI conversation responses"""

    message: str = Field(..., description="AI response message")
    context: List[str] = Field(..., description="Updated conversation context")
    suggestions: List[str] = Field(
        default_factory=list, description="Follow-up suggestions"
    )
    related_entities: List[int] = Field(
        default_factory=list, description="Related code entities"
    )
    confidence: float = Field(..., ge=0, le=1, description="Response confidence")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
