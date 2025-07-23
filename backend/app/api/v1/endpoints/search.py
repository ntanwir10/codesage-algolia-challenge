from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
import structlog
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.schemas.search import SearchQuery, SearchResponse, SearchSuggestion
from app.services.search_service import SearchService
from app.services.algolia_service import AlgoliaService
from app.services.security_service import rate_limit_search, rate_limit_default

logger = structlog.get_logger()
router = APIRouter()


# Enhanced request models for better validation
class AdvancedSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    repository_id: Optional[int] = Field(
        None, description="Filter by specific repository"
    )
    language: Optional[str] = Field(None, description="Filter by programming language")
    entity_type: Optional[str] = Field(
        None, description="Filter by entity type (function, class, file)"
    )
    filters: Optional[str] = Field(None, description="Additional search filters")
    page: int = Field(default=0, ge=0, description="Page number (0-based)")
    per_page: int = Field(default=20, ge=1, le=100, description="Results per page")
    include_content: bool = Field(
        default=True, description="Include code content in results"
    )
    similarity_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Similarity threshold"
    )


class VoiceSearchRequest(BaseModel):
    audio_data: str = Field(..., description="Base64 encoded audio data")
    language: Optional[str] = Field("en", description="Audio language code")
    format: Optional[str] = Field("wav", description="Audio format")


class SimilaritySearchRequest(BaseModel):
    entity_type: str = Field(..., description="Type of entity (function, class, file)")
    entity_id: int = Field(..., description="ID of the reference entity")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of results")
    threshold: float = Field(
        default=0.8, ge=0.1, le=1.0, description="Similarity threshold"
    )
    include_repository: Optional[str] = Field(
        None, description="Limit to specific repository"
    )


@router.post(
    "/",
    response_model=SearchResponse,
    summary="Advanced Code Search",
    description="Perform advanced search across repositories with filters and options",
)
@rate_limit_search
async def search_code(
    search_request: AdvancedSearchRequest, db: Session = Depends(get_db)
):
    """Perform advanced natural language search across all repositories"""
    try:
        # Convert to SearchQuery schema
        search_query = SearchQuery(
            query=search_request.query,
            repository_id=search_request.repository_id,
            language=search_request.language,
            entity_type=search_request.entity_type,
            filters=search_request.filters,
            page=search_request.page,
            per_page=search_request.per_page,
        )

        search_service = SearchService()
        results = await search_service.search(search_query, db)

        # Filter content if requested
        if not search_request.include_content:
            for hit in results.hits:
                if hasattr(hit, "content"):
                    hit.content = None

        logger.info(
            "Advanced search performed",
            query=search_request.query,
            results_count=len(results.hits),
            repository_id=search_request.repository_id,
            language=search_request.language,
        )
        return results

    except Exception as e:
        logger.error("Advanced search failed", query=search_request.query, error=str(e))
        raise HTTPException(status_code=400, detail=f"Search failed: {str(e)}")


@router.get(
    "/suggestions",
    response_model=List[SearchSuggestion],
    summary="Get Search Suggestions",
    description="Get intelligent search suggestions based on partial query",
)
async def get_search_suggestions(
    q: str = Query(
        ..., min_length=2, max_length=100, description="Partial search query"
    ),
    limit: int = Query(
        default=10, ge=1, le=20, description="Maximum number of suggestions"
    ),
    context: Optional[str] = Query(
        None, description="Search context (repository, language, etc.)"
    ),
    db: Session = Depends(get_db),
):
    """Get search suggestions based on partial query"""
    try:
        search_service = SearchService()
        suggestions = await search_service.get_suggestions(q, limit, context)

        logger.info("Search suggestions generated", query=q, count=len(suggestions))
        return suggestions

    except Exception as e:
        logger.error("Suggestions failed", query=q, error=str(e))
        raise HTTPException(
            status_code=400, detail=f"Failed to get suggestions: {str(e)}"
        )


@router.post(
    "/voice",
    response_model=SearchResponse,
    summary="Voice Search",
    description="Process voice search query and return results",
)
async def voice_search(
    voice_request: VoiceSearchRequest, db: Session = Depends(get_db)
):
    """Process voice search query"""
    try:
        # Validate audio data format
        if not voice_request.audio_data:
            raise HTTPException(status_code=400, detail="Audio data is required")

        # Basic validation for base64 format
        if len(voice_request.audio_data) < 100:
            raise HTTPException(
                status_code=400, detail="Audio data appears to be too short"
            )

        search_service = SearchService()
        # Convert voice search to text search for now
        voice_query = f"voice query: {voice_request.audio_data[:50]}"
        results = await search_service.search_by_voice(voice_query, db)

        logger.info("Voice search performed", results_count=len(results.hits))
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Voice search failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Voice search failed: {str(e)}")


@router.get(
    "/repositories/{repository_id}",
    response_model=SearchResponse,
    summary="Repository-Specific Search",
    description="Search within a specific repository",
)
async def search_repository(
    repository_id: int,
    q: str = Query(..., min_length=1, description="Search query"),
    filters: Optional[str] = Query(None, description="Additional search filters"),
    page: int = Query(default=0, ge=0, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Results per page"),
    include_content: bool = Query(default=True, description="Include code content"),
    db: Session = Depends(get_db),
):
    """Search within a specific repository"""
    try:
        # Validate repository exists
        from app.models.repository import Repository

        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404, detail=f"Repository {repository_id} not found"
            )

        search_service = SearchService()
        search_query = SearchQuery(
            query=q,
            repository_id=repository_id,
            filters=filters,
            page=page,
            per_page=per_page,
        )
        results = await search_service.search(search_query, db)

        # Filter content if requested
        if not include_content:
            for hit in results.hits:
                if hasattr(hit, "content"):
                    hit.content = None

        logger.info(
            "Repository search performed",
            repository_id=repository_id,
            query=q,
            results_count=len(results.hits),
        )
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Repository search failed",
            repository_id=repository_id,
            query=q,
            error=str(e),
        )
        raise HTTPException(
            status_code=400, detail=f"Repository search failed: {str(e)}"
        )


@router.post(
    "/similar",
    summary="Find Similar Code Entities",
    description="Find code entities similar to a reference entity",
)
async def find_similar_entities(
    request: SimilaritySearchRequest,
    db: Session = Depends(get_db),
):
    """Find similar code entities across repositories"""
    try:
        # Validate entity exists
        from app.models.code_entity import CodeEntity

        entity = db.query(CodeEntity).filter(CodeEntity.id == request.entity_id).first()
        if not entity:
            raise HTTPException(
                status_code=404, detail=f"Entity {request.entity_id} not found"
            )

        search_service = SearchService()
        results = await search_service.find_similar(
            request.entity_type,
            request.entity_id,
            request.limit,
            request.threshold,
            request.include_repository,
        )

        logger.info(
            "Similarity search performed",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            results_count=len(results) if results else 0,
        )
        return {
            "reference_entity": {
                "id": entity.id,
                "name": entity.name,
                "type": entity.entity_type,
                "repository_id": (
                    entity.code_file.repository_id if entity.code_file else None
                ),
            },
            "similar_entities": results,
            "threshold": request.threshold,
            "total_found": len(results) if results else 0,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Similarity search failed",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=400, detail=f"Similarity search failed: {str(e)}"
        )


@router.get(
    "/trending",
    summary="Get Trending Searches",
    description="Get trending search queries and patterns",
)
async def get_trending_searches(
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
    limit: int = Query(
        default=10, ge=1, le=50, description="Maximum number of results"
    ),
    category: Optional[str] = Query(None, description="Search category filter"),
    db: Session = Depends(get_db),
):
    """Get trending search queries"""
    try:
        search_service = SearchService()
        trending = await search_service.get_trending_searches(hours, limit, category)

        logger.info(
            "Trending searches retrieved",
            hours=hours,
            count=len(trending) if trending else 0,
        )
        return {
            "time_window_hours": hours,
            "trending_searches": trending,
            "generated_at": "now",  # This would be a proper timestamp
            "total_count": len(trending) if trending else 0,
        }

    except Exception as e:
        logger.error("Trending searches failed", hours=hours, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get trending searches: {str(e)}"
        )


@router.get(
    "/analytics",
    summary="Search Analytics",
    description="Get search usage analytics and insights",
)
async def get_search_analytics(
    days: int = Query(
        default=7, ge=1, le=90, description="Analytics time window in days"
    ),
    include_popular_terms: bool = Query(
        default=True, description="Include popular search terms"
    ),
    include_performance: bool = Query(
        default=True, description="Include performance metrics"
    ),
    db: Session = Depends(get_db),
):
    """Get search analytics and insights"""
    try:
        search_service = SearchService()
        analytics = await search_service.get_search_analytics(
            days, include_popular_terms, include_performance
        )

        logger.info("Search analytics retrieved", days=days)
        return analytics

    except Exception as e:
        logger.error("Search analytics failed", days=days, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get search analytics: {str(e)}"
        )


@router.post(
    "/index/refresh",
    summary="Refresh Search Index",
    description="Trigger a refresh of the search index",
)
async def refresh_search_index(
    repository_id: Optional[int] = Query(
        None, description="Refresh specific repository only"
    ),
    force: bool = Query(default=False, description="Force complete reindex"),
    db: Session = Depends(get_db),
):
    """Refresh the search index for better results"""
    try:
        search_service = SearchService()
        result = await search_service.refresh_index(repository_id, force)

        logger.info(
            "Search index refresh triggered", repository_id=repository_id, force=force
        )
        return {
            "message": "Search index refresh started",
            "repository_id": repository_id,
            "force_reindex": force,
            "status": "processing",
            "result": result,
        }

    except Exception as e:
        logger.error("Index refresh failed", repository_id=repository_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Index refresh failed: {str(e)}")


@router.get(
    "/health",
    summary="Search Service Health",
    description="Check health of search service and Algolia connection",
)
async def get_search_health(db: Session = Depends(get_db)):
    """Get search service health status"""
    try:
        search_service = SearchService()

        # Test database connection
        db_status = "healthy"
        try:
            from sqlalchemy import text

            db.execute(text("SELECT 1"))
        except Exception:
            db_status = "unhealthy"

        # Test Algolia connection
        algolia_service = AlgoliaService()
        algolia_status = "healthy" if algolia_service.is_available() else "unhealthy"

        # Test search functionality
        search_status = "healthy"
        try:
            test_query = SearchQuery(query="test", per_page=1)
            await search_service.search(test_query, db)
        except Exception:
            search_status = "degraded"

        health_status = {
            "search_service": "healthy",
            "database": db_status,
            "algolia": algolia_status,
            "search_functionality": search_status,
            "version": "1.0.0",
            "mcp_integration": "active",
        }

        logger.info("Search health check performed", status=health_status)
        return health_status

    except Exception as e:
        logger.error("Search health check failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
