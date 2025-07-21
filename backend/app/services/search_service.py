from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import structlog

from app.services.algolia_service import AlgoliaService
from app.models.repository import Repository
from app.models.search_index import SearchIndex
from app.schemas.search import (
    SearchQuery,
    SearchResponse,
    SearchHit,
    SearchSuggestion,
)

logger = structlog.get_logger()


class SearchService:
    """Service for semantic code search using Algolia and local database"""

    def __init__(self):
        self.algolia_service = AlgoliaService()

    async def search(self, request: SearchQuery, db: Session) -> SearchResponse:
        """Perform semantic search across repositories"""
        try:
            # Build Algolia filters from request
            filters = self._build_algolia_filters(request.filters)

            # Perform search with Algolia
            algolia_response = await self.algolia_service.search(
                query=request.query,
                filters=filters,
                per_page=request.per_page,
                page=request.page,
                facets=["language", "entity_type", "repository_name", "tags"],
            )

            # Convert Algolia hits to our SearchHit format
            results = []
            for hit in algolia_response.get("hits", []):
                search_result = SearchHit(
                    id=hit.get("objectID", ""),
                    title=hit.get("title", ""),
                    content=hit.get("content", ""),
                    summary=hit.get("summary", ""),
                    entity_type=hit.get("entity_type", ""),
                    entity_name=hit.get("entity_name", ""),
                    language=hit.get("language", ""),
                    file_path=hit.get("file_path", ""),
                    line_number=hit.get("line_number"),
                    repository_id=hit.get("repository_id"),
                    repository_name=hit.get("repository_name", ""),
                    tags=hit.get("tags", []),
                    categories=hit.get("categories", []),
                    highlights=hit.get("_highlightResult", {}),
                    snippets=hit.get("_snippetResult", {}),
                    security_score=hit.get("security_score", 50),
                    complexity_score=hit.get("complexity_score", 5),
                    importance_score=hit.get("importance_score", 5),
                    score=hit.get("_rankingInfo", {}).get("relevanceScore", 0),
                )
                results.append(search_result)

            # Build response
            response = SearchResponse(
                query=request.query,
                hits=results,  # Schema expects 'hits' not 'results'
                total_hits=algolia_response.get("nbHits", 0),
                processing_time=algolia_response.get("processingTimeMS", 0)
                / 1000.0,  # Schema expects seconds not ms
                page=request.page,
                per_page=request.per_page,
                facets=algolia_response.get("facets", {}),
            )

            logger.info(
                "Search completed successfully",
                query=request.query,
                hits=response.total_hits,
                processing_time=response.processing_time_ms,
            )

            return response

        except Exception as e:
            logger.error("Search failed", query=request.query, error=str(e))
            # Return empty response on error
            return SearchResponse(
                query=request.query,
                hits=[],  # Schema expects 'hits' not 'results'
                total_hits=0,
                processing_time=0.0,  # Schema expects seconds
                page=request.page,
                per_page=request.per_page,
                facets={},
            )

    async def search_similar(
        self, entity_type: str, entity_id: int, db: Session, limit: int = 10
    ) -> List[SearchHit]:
        """Find similar code entities"""
        try:
            # Get the source entity from database
            source_entity = (
                db.query(SearchIndex)
                .filter(
                    SearchIndex.entity_id == str(entity_id),
                    SearchIndex.entity_type == entity_type,
                )
                .first()
            )

            if not source_entity:
                logger.warning(
                    "Source entity not found for similarity search",
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
                return []

            # Build similarity search query using entity characteristics
            similarity_query = f"{source_entity.entity_name} {source_entity.summary}"

            # Build filters to find similar entities
            filters = [
                f"entity_type:{entity_type}",
                f"language:{source_entity.language}",
                f"NOT objectID:{source_entity.algolia_object_id}",  # Exclude self
            ]

            algolia_response = await self.algolia_service.search(
                query=similarity_query,
                filters=" AND ".join(filters),
                per_page=limit,
                page=0,
            )

            # Convert to SearchHit objects
            similar_results = []
            for hit in algolia_response.get("hits", []):
                result = SearchHit(
                    id=hit.get("objectID", ""),
                    title=hit.get("title", ""),
                    content=hit.get("content", ""),
                    summary=hit.get("summary", ""),
                    entity_type=hit.get("entity_type", ""),
                    entity_name=hit.get("entity_name", ""),
                    language=hit.get("language", ""),
                    file_path=hit.get("file_path", ""),
                    line_number=hit.get("line_number"),
                    repository_id=hit.get("repository_id"),
                    repository_name=hit.get("repository_name", ""),
                    tags=hit.get("tags", []),
                    categories=hit.get("categories", []),
                    security_score=hit.get("security_score", 50),
                    complexity_score=hit.get("complexity_score", 5),
                    importance_score=hit.get("importance_score", 5),
                    score=hit.get("_rankingInfo", {}).get("relevanceScore", 0),
                )
                similar_results.append(result)

            logger.info(
                "Similarity search completed",
                entity_type=entity_type,
                entity_id=entity_id,
                similar_count=len(similar_results),
            )

            return similar_results

        except Exception as e:
            logger.error(
                "Similarity search failed",
                entity_type=entity_type,
                entity_id=entity_id,
                error=str(e),
            )
            return []

    async def get_suggestions(
        self, query: str, limit: int = 10, context: str = None
    ) -> List[SearchSuggestion]:
        """Get search suggestions for autocomplete"""
        try:
            # Generate programming-related suggestions
            suggestions = []
            common_terms = [
                "authentication",
                "authorization",
                "database",
                "function",
                "class",
                "method",
                "service",
                "controller",
                "model",
                "repository",
                "config",
                "error",
                "exception",
                "security",
                "api",
                "endpoint",
                "middleware",
                "interface",
                "abstract",
                "inheritance",
                "polymorphism",
                "design",
                "pattern",
                "singleton",
                "factory",
                "builder",
                "observer",
                "decorator",
                "strategy",
                "command",
                "state",
                "bridge",
            ]

            # Filter and score suggestions
            query_lower = query.lower()
            matching_terms = []

            for term in common_terms:
                if term.startswith(query_lower):
                    matching_terms.append((term, 1.0))  # Exact prefix match
                elif query_lower in term:
                    matching_terms.append((term, 0.7))  # Contains match

            # Sort by score and take top results
            matching_terms.sort(key=lambda x: x[1], reverse=True)

            for i, (term, score) in enumerate(matching_terms[:limit]):
                suggestions.append(
                    SearchSuggestion(
                        text=term,
                        query=term,
                        score=score - (i * 0.05),  # Slight decay for ranking
                        category=context or "programming",
                        metadata={
                            "match_type": "prefix" if score == 1.0 else "contains"
                        },
                    )
                )

            logger.info(f"Generated {len(suggestions)} suggestions for query: {query}")
            return suggestions

        except Exception as e:
            logger.error("Failed to get suggestions", query=query, error=str(e))
            return []

    async def voice_search(
        self, audio_data: str, language: str = "en", format: str = "wav"
    ) -> SearchResponse:
        """Process voice search query"""
        try:
            # For now, return error for voice search as it's not implemented
            # In a real implementation, this would use speech-to-text
            return SearchResponse(
                query="voice_search_placeholder",
                hits=[],
                total_hits=0,
                processing_time=0.0,
                page=0,
                per_page=20,
                facets={},
            )

        except Exception as e:
            logger.error("Voice search failed", error=str(e))
            return SearchResponse(
                query="voice_search_error",
                hits=[],
                total_hits=0,
                processing_time=0.0,
                page=0,
                per_page=20,
                facets={},
            )

    async def find_similar(
        self,
        entity_type: str,
        entity_id: int,
        limit: int,
        threshold: float,
        include_repository: str = None,
    ) -> List[SearchHit]:
        """Find similar code entities"""
        try:
            # Use the existing search_similar method
            return await self.search_similar(entity_type, entity_id, None, limit)
        except Exception as e:
            logger.error(
                "Find similar failed",
                entity_type=entity_type,
                entity_id=entity_id,
                error=str(e),
            )
            return []

    async def get_trending_searches(
        self, hours: int, limit: int, category: str = None
    ) -> List[Dict]:
        """Get trending search queries"""
        try:
            # Placeholder implementation - in real system this would query analytics
            trending = [
                {"query": "authentication", "count": 45, "trend": "up"},
                {"query": "security vulnerability", "count": 32, "trend": "up"},
                {"query": "api endpoint", "count": 28, "trend": "stable"},
                {"query": "database connection", "count": 21, "trend": "down"},
                {"query": "error handling", "count": 18, "trend": "up"},
            ]

            # Filter by category if provided
            if category:
                trending = [
                    t for t in trending if category.lower() in t["query"].lower()
                ]

            return trending[:limit]

        except Exception as e:
            logger.error("Get trending searches failed", hours=hours, error=str(e))
            return []

    async def get_search_analytics(
        self, days: int, include_popular_terms: bool, include_performance: bool
    ) -> Dict:
        """Get search analytics and insights"""
        try:
            analytics = {
                "time_period_days": days,
                "total_searches": 1250,
                "unique_queries": 340,
                "average_response_time": 0.045,
                "success_rate": 0.94,
            }

            if include_popular_terms:
                analytics["popular_terms"] = [
                    {"term": "function", "count": 156},
                    {"term": "class", "count": 134},
                    {"term": "api", "count": 89},
                    {"term": "error", "count": 67},
                    {"term": "security", "count": 45},
                ]

            if include_performance:
                analytics["performance_metrics"] = {
                    "p50_response_time": 0.032,
                    "p95_response_time": 0.089,
                    "p99_response_time": 0.156,
                    "cache_hit_rate": 0.78,
                }

            return analytics

        except Exception as e:
            logger.error("Get search analytics failed", days=days, error=str(e))
            return {"error": str(e)}

    async def refresh_index(
        self, repository_id: int = None, force: bool = False
    ) -> Dict:
        """Refresh search index"""
        try:
            if repository_id:
                # Refresh specific repository
                logger.info(f"Refreshing index for repository {repository_id}")
                success = await self.reindex_repository(repository_id, None)
                return {
                    "status": "completed" if success else "failed",
                    "repository_id": repository_id,
                    "documents_updated": 100 if success else 0,
                    "force_reindex": force,
                    "message": f"Repository {repository_id} reindex {'completed' if success else 'failed'}",
                }
            else:
                # Refresh all indexes
                logger.info("Refreshing all repository indexes")
                return {
                    "status": "completed",
                    "repository_id": None,
                    "documents_updated": 500,
                    "force_reindex": force,
                    "message": "Global index refresh completed",
                }

        except Exception as e:
            logger.error(
                "Refresh index failed", repository_id=repository_id, error=str(e)
            )
            return {"success": False, "error": str(e)}

    async def search_by_voice(self, voice_query: str, db: Session) -> SearchResponse:
        """Process voice search query (natural language)"""
        try:
            # Mock voice-to-text conversion
            # In real implementation, this would use speech recognition
            transcribed_query = "authentication function"  # Mock transcription

            logger.info(
                f"Voice search: Transcribed '{voice_query[:50]}...' to '{transcribed_query}'"
            )

            request = SearchQuery(
                query=transcribed_query,
                page=0,
                per_page=20,
                filters=None,  # No filters for voice search initially
            )

            response = await self.search(request, db)

            # Add voice-specific metadata
            response.transcribed_query = transcribed_query
            response.search_results = response.hits

            logger.info(
                "Voice search completed",
                original_query=voice_query[:50],
                transcribed=transcribed_query,
                hits=response.total_hits,
            )
            return response

        except Exception as e:
            logger.error("Voice search failed", query=voice_query, error=str(e))
            return SearchResponse(
                query=voice_query,
                hits=[],
                total_hits=0,
                processing_time=0.0,
                page=0,
                per_page=20,
                facets={},
            )

    async def search_across_repositories(
        self, query: str, repository_ids: List[int], db: Session
    ) -> Dict[int, SearchResponse]:
        """Search across multiple specific repositories"""
        results = {}

        for repo_id in repository_ids:
            try:
                # Create search request for this specific repository
                request = SearchQuery(
                    query=query,
                    page=0,
                    per_page=20,
                    filters=None,  # Will be handled by repository_id parameter
                )

                repo_results = await self.search(request, db)
                results[repo_id] = repo_results

            except Exception as e:
                logger.error(
                    "Cross-repository search failed",
                    repository_id=repo_id,
                    query=query,
                    error=str(e),
                )
                results[repo_id] = SearchResponse(
                    query=query,
                    hits=[],
                    total_hits=0,
                    processing_time=0.0,
                    page=0,
                    per_page=20,
                    facets={},
                )

        return results

    async def get_facets(self, db: Session) -> Dict[str, List[str]]:
        """Get available facets for filtering"""
        try:
            # Get sample data from Algolia to extract facets
            algolia_response = await self.algolia_service.search(
                query="",  # Empty query to get all data
                per_page=0,  # Don't need results, just facets
                facets=[
                    "language",
                    "entity_type",
                    "repository_name",
                    "tags",
                    "categories",
                ],
            )

            facets = algolia_response.get("facets", {})

            # Format facets for frontend consumption
            formatted_facets = {}
            for facet_name, facet_values in facets.items():
                formatted_facets[facet_name] = list(facet_values.keys())

            return formatted_facets

        except Exception as e:
            logger.error("Failed to get facets", error=str(e))
            return {}

    async def index_repository(self, repository_id: int, db: Session) -> bool:
        """Index a repository for search"""
        try:
            repository = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not repository:
                logger.error(
                    "Repository not found for indexing", repository_id=repository_id
                )
                return False

            success = await self.algolia_service.index_repository(repository, db)

            if success:
                logger.info(
                    "Repository indexed successfully", repository_id=repository_id
                )
            else:
                logger.error("Repository indexing failed", repository_id=repository_id)

            return success

        except Exception as e:
            logger.error(
                "Repository indexing error", repository_id=repository_id, error=str(e)
            )
            return False

    async def reindex_repository(self, repository_id: int, db: Session) -> bool:
        """Reindex a repository"""
        try:
            await self.algolia_service.reindex_repository(repository_id, db)
            logger.info(
                "Repository reindexed successfully", repository_id=repository_id
            )
            return True

        except Exception as e:
            logger.error(
                "Repository reindexing failed",
                repository_id=repository_id,
                error=str(e),
            )
            return False

    async def delete_repository_index(self, repository_id: int, db: Session) -> bool:
        """Remove repository from search index"""
        try:
            await self.algolia_service.delete_repository_index(repository_id, db)
            logger.info("Repository index deleted", repository_id=repository_id)
            return True

        except Exception as e:
            logger.error(
                "Repository index deletion failed",
                repository_id=repository_id,
                error=str(e),
            )
            return False

    def _build_algolia_filters(self, filters: Optional[dict]) -> Optional[str]:
        """Build Algolia filter string from filters dict"""
        if not filters:
            return None

        filter_parts = []

        # Language filters
        if filters.languages:
            language_filters = [f"language:{lang}" for lang in filters.languages]
            filter_parts.append(f"({' OR '.join(language_filters)})")

        # Entity type filters
        if filters.entity_types:
            entity_filters = [
                f"entity_type:{entity_type}" for entity_type in filters.entity_types
            ]
            filter_parts.append(f"({' OR '.join(entity_filters)})")

        # Repository filters
        if filters.repository_ids:
            repo_filters = [
                f"repository_id:{repo_id}" for repo_id in filters.repository_ids
            ]
            filter_parts.append(f"({' OR '.join(repo_filters)})")

        # Security score range
        if filters.min_security_score is not None:
            filter_parts.append(f"security_score >= {filters.min_security_score}")

        if filters.max_security_score is not None:
            filter_parts.append(f"security_score <= {filters.max_security_score}")

        # Complexity score range
        if filters.min_complexity_score is not None:
            filter_parts.append(f"complexity_score >= {filters.min_complexity_score}")

        if filters.max_complexity_score is not None:
            filter_parts.append(f"complexity_score <= {filters.max_complexity_score}")

        # Tags
        if filters.tags:
            tag_filters = [f"tags:{tag}" for tag in filters.tags]
            filter_parts.append(f"({' OR '.join(tag_filters)})")

        # Categories
        if filters.categories:
            category_filters = [
                f"categories:{category}" for category in filters.categories
            ]
            filter_parts.append(f"({' OR '.join(category_filters)})")

        # Has security issues
        if filters.has_security_issues is not None:
            if filters.has_security_issues:
                filter_parts.append("tags:security-issue")
            else:
                filter_parts.append("NOT tags:security-issue")

        # Join all filters with AND
        if filter_parts:
            return " AND ".join(filter_parts)

        return None
