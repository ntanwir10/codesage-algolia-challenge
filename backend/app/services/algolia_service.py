"""
CodeSage - MCP-First Code Discovery: Algolia Service

This module provides search functionality for CodeSage - the only code discovery
tool built entirely around the Model Context Protocol (MCP) for seamless AI integration.

The Algolia service indexes code entities and provides search capabilities that
are accessed through MCP tools by Claude Desktop and other MCP clients.

This represents our core innovation: MCP-first architecture with powerful search integration.
"""

from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import structlog
from algoliasearch.search_client import SearchClient
from algoliasearch.exceptions import AlgoliaException
import hashlib

from app.core.config import get_settings
from app.services.code_parser import ParsedCodeEntity

logger = structlog.get_logger()
settings = get_settings()


class AlgoliaService:
    """Service for Algolia search index management and MCP server integration"""

    def __init__(self):
        """Initialize Algolia client with credentials from settings"""
        try:
            if not settings.algolia_app_id or not settings.algolia_admin_api_key:
                logger.warning("Algolia credentials not configured")
                self.client = None
                self.index = None
                return

            self.client = SearchClient.create(
                app_id=settings.algolia_app_id, api_key=settings.algolia_admin_api_key
            )
            self.index_name = settings.algolia_index_name
            self.index = self.client.init_index(self.index_name)

            logger.info(
                "Algolia client initialized",
                app_id=settings.algolia_app_id,
                index=self.index_name,
            )
        except Exception as e:
            logger.error("Failed to initialize Algolia client", error=str(e))
            self.client = None
            self.index = None

    def is_available(self) -> bool:
        """Check if Algolia service is available"""
        return self.client is not None and self.index is not None

    @staticmethod
    def _repository_filter(repository_id: int) -> str:
        """Filter matching one repository's records.

        Uses a numeric comparison: in a filters string the facet form
        `repository_id:2` matches no records, because the value is numeric.
        """
        return f"repository_id={int(repository_id)}"

    async def setup_index_settings(self):
        """Configure Algolia index settings for optimal code search"""
        if not self.is_available():
            logger.warning("Algolia not available, skipping index setup")
            return

        try:
            settings_config = {
                # Searchable attributes with priority
                "searchableAttributes": [
                    "entity_name",
                    "description",
                    "content",
                    "parameters",
                    "file_path",
                ],
                # Attributes for faceting and filtering
                "attributesForFaceting": [
                    "repository_id",
                    "entity_type",
                    "language",
                    "return_type",
                ],
                # Custom ranking for relevance
                "customRanking": [
                    "desc(entity_type)",  # Functions/classes ranked higher
                    "asc(file_path)",  # Shorter paths ranked higher
                ],
                # Highlight settings for search results
                "highlightPreTag": "<mark>",
                "highlightPostTag": "</mark>",
                # Performance settings
                "hitsPerPage": 20,
                "maxValuesPerFacet": 100,
            }

            self.index.set_settings(settings_config)
            logger.info("Algolia index settings configured")

        except AlgoliaException as e:
            logger.error("Failed to setup Algolia index settings", error=str(e))

    async def batch_index_entities(
        self,
        entities: List[ParsedCodeEntity],
        repository_id: int,
        file_path: str,
        language: str,
    ) -> bool:
        """
        Index code entities in Algolia for search.
        Based on architecture.md: Code Entity Structure for Algolia documents.
        """
        if not self.is_available():
            logger.warning("Algolia not available, skipping indexing")
            return False

        if not entities:
            return True

        try:
            # Convert entities to Algolia documents
            documents = []
            for entity in entities:
                doc = self._create_algolia_document(
                    entity, repository_id, file_path, language
                )
                documents.append(doc)

            # Batch index documents
            result = self.index.save_objects(documents)

            # Handle different response types from Algolia
            task_id = None
            if hasattr(result, "taskID"):
                task_id = result.taskID
            elif hasattr(result, "__dict__") and "taskID" in result.__dict__:
                task_id = result.__dict__["taskID"]
            elif isinstance(result, dict) and "taskID" in result:
                task_id = result["taskID"]

            logger.info(
                "Entities indexed in Algolia",
                repository_id=repository_id,
                file_path=file_path,
                entities_count=len(entities),
                algolia_task_id=task_id,
            )

            return True

        except AlgoliaException as e:
            logger.error(
                "Failed to index entities in Algolia",
                repository_id=repository_id,
                file_path=file_path,
                error=str(e),
            )
            return False

    def _create_algolia_document(
        self,
        entity: ParsedCodeEntity,
        repository_id: int,
        file_path: str,
        language: str,
    ) -> Dict[str, Any]:
        """
        Create Algolia document from code entity.
        Follows architecture.md structure exactly.
        """
        # Stable ID: re-indexing the same entity overwrites its record instead of duplicating it
        entity_key = f"{file_path}:{entity.entity_type}:{entity.name}:{entity.line_start}"
        return {
            "objectID": f"{repository_id}_{hashlib.sha1(entity_key.encode()).hexdigest()}",
            "repository_id": repository_id,
            "file_path": file_path,
            "entity_type": entity.entity_type,
            "entity_name": entity.name,
            "description": entity.description,
            "parameters": entity.parameters or [],
            "return_type": entity.return_type,
            "line_start": entity.line_start,
            "line_end": entity.line_end,
            "language": language,
            "content": entity.content or "",
            # Additional fields for better search
            "imports": entity.imports or [],
            "parameter_count": len(entity.parameters) if entity.parameters else 0,
            "lines_of_code": (
                (entity.line_end - entity.line_start + 1)
                if entity.line_end > entity.line_start
                else 1
            ),
        }

    async def search_code(
        self,
        query: str,
        repository_id: int = None,
        language: str = None,
        entity_type: str = None,
    ) -> Dict[str, Any]:
        """
        Search code entities in Algolia.
        Used by MCP tools for natural language code discovery.
        """
        if not self.is_available():
            logger.warning("Algolia not available for search")
            return {"hits": [], "nbHits": 0, "query": query}

        try:
            # Build search parameters
            search_params = {
                "query": query,
                "hitsPerPage": 20,
                "highlightPreTag": "<mark>",
                "highlightPostTag": "</mark>",
            }

            # Add filters
            filters = []
            if repository_id:
                filters.append(self._repository_filter(repository_id))
            if language:
                filters.append(f"language:{language}")
            if entity_type:
                filters.append(f"entity_type:{entity_type}")

            if filters:
                search_params["filters"] = " AND ".join(filters)

            # Perform search
            results = self.index.search(query, search_params)

            logger.info(
                "Code search performed",
                query=query,
                hits=results.get("nbHits", 0),
                repository_id=repository_id,
                language=language,
                entity_type=entity_type,
            )

            return results

        except AlgoliaException as e:
            logger.error("Algolia search failed", query=query, error=str(e))
            return {"hits": [], "nbHits": 0, "query": query, "error": str(e)}

    async def delete_repository_index(
        self, repository_id: int, wait: bool = False
    ) -> bool:
        """Delete all indexed entities for a repository.

        Pass wait=True before re-indexing so the delete can't land after the new records.
        """
        if not self.is_available():
            return True

        try:
            # Delete by repository_id filter
            response = self.index.delete_by(
                {"filters": self._repository_filter(repository_id)}
            )
            if wait:
                response.wait()

            logger.info(
                "Repository entities deleted from Algolia", repository_id=repository_id
            )
            return True

        except AlgoliaException as e:
            logger.error(
                "Failed to delete repository from Algolia",
                repository_id=repository_id,
                error=str(e),
            )
            return False

    async def get_repository_stats(self, repository_id: int) -> Dict[str, Any]:
        """Get statistics for indexed repository entities"""
        if not self.is_available():
            return {}

        try:
            # Search for all entities in this repository
            results = self.index.search(
                "",
                {
                    "filters": self._repository_filter(repository_id),
                    "hitsPerPage": 0,  # Just get facets, not actual hits
                    "facets": ["entity_type", "language"],
                    "maxValuesPerFacet": 100,
                },
            )

            stats = {
                "total_entities": results.get("nbHits", 0),
                "entity_types": results.get("facets", {}).get("entity_type", {}),
                "languages": results.get("facets", {}).get("language", {}),
            }

            return stats

        except AlgoliaException as e:
            logger.error(
                "Failed to get repository stats",
                repository_id=repository_id,
                error=str(e),
            )
            return {}
