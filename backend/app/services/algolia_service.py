"""
CodeSage - MCP-First Code Discovery: Algolia Service

Indexes code entities in Algolia and searches them for the MCP tools that
Claude Desktop and other MCP clients call.

The v3 Algolia client is synchronous, so every call runs in a worker thread
to keep the event loop (API, WebSocket, MCP) responsive.
"""

import asyncio
import hashlib
from typing import Any

import structlog
from algoliasearch.search_client import SearchClient

from app.core.config import get_settings
from app.services.code_parser import ParsedCodeEntity

logger = structlog.get_logger()
settings = get_settings()

# Records per save_objects request (Algolia's recommended batch size)
INDEX_BATCH_SIZE = 1000

# Characters of entity body stored with each record, well under the 10 KB record limit
MAX_BODY_CHARS = 2000

# Higher ranks first when relevance ties
RANK_WEIGHTS = {"class": 3, "function": 2, "doc_section": 1, "import": 0}

INDEX_SETTINGS = {
    "searchableAttributes": [
        "entity_name",
        "description",
        "content",
        "parameters",
        "file_path",
    ],
    "attributesForFaceting": [
        "filterOnly(repository_id)",
        "entity_type",
        "language",
        "file_path",
    ],
    "customRanking": ["desc(rank_weight)"],
    "highlightPreTag": "<mark>",
    "highlightPostTag": "</mark>",
    "hitsPerPage": 20,
    "maxValuesPerFacet": 100,
}

# Indexes whose settings this process has already applied
_configured_indexes: set[str] = set()


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
        """Apply the index settings once per process and wait until they're live"""
        if not self.is_available() or self.index_name in _configured_indexes:
            return

        def apply():
            self.index.set_settings(INDEX_SETTINGS).wait()

        try:
            await asyncio.to_thread(apply)
            _configured_indexes.add(self.index_name)
            logger.info("Algolia index settings configured", index=self.index_name)
        except Exception as e:
            logger.error("Failed to configure Algolia index settings", error=str(e))

    def build_documents(
        self,
        entities: list[ParsedCodeEntity],
        repository_id: int,
        file_path: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Algolia records for one file's entities"""
        return [
            self._create_algolia_document(entity, repository_id, file_path, language)
            for entity in entities
        ]

    async def index_documents(self, documents: list[dict[str, Any]]) -> bool:
        """Index records in batches and wait until they're searchable"""
        if not self.is_available():
            logger.warning("Algolia not available, skipping indexing")
            return False
        if not documents:
            return True

        def save():
            for start in range(0, len(documents), INDEX_BATCH_SIZE):
                self.index.save_objects(documents[start : start + INDEX_BATCH_SIZE]).wait()

        try:
            await asyncio.to_thread(save)
        except Exception as e:
            logger.error(
                "Failed to index entities in Algolia",
                documents=len(documents),
                error=str(e),
            )
            return False

        logger.info("Entities indexed in Algolia", documents=len(documents))
        return True

    def _create_algolia_document(
        self,
        entity: ParsedCodeEntity,
        repository_id: int,
        file_path: str,
        language: str,
    ) -> dict[str, Any]:
        """Algolia record for one code entity"""
        # Stable ID: re-indexing the same entity overwrites its record instead of duplicating it
        entity_key = f"{file_path}:{entity.entity_type}:{entity.name}:{entity.line_start}"
        signature = entity.content or ""
        body = (entity.body or "")[:MAX_BODY_CHARS]
        content = f"{signature}\n{body}" if body and not body.startswith(signature) else (
            body or signature
        )
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
            "signature": signature,
            "content": content,
            "rank_weight": RANK_WEIGHTS.get(entity.entity_type, 0),
            "parameter_count": len(entity.parameters) if entity.parameters else 0,
            "lines_of_code": max(entity.line_end - entity.line_start + 1, 1),
        }

    async def search_code(
        self,
        query: str,
        repository_id: int | None = None,
        language: str | None = None,
        entity_type: str | None = None,
        hits_per_page: int = 20,
        page: int = 0,
    ) -> dict[str, Any]:
        """Search code entities, optionally scoped by repository, language and type.

        Raises when Algolia is unavailable or the request fails, so callers can
        report an error instead of an empty result.
        """
        if not self.is_available():
            raise RuntimeError("Algolia is not configured")

        search_params = {
            "hitsPerPage": hits_per_page,
            "page": page,
            "highlightPreTag": "<mark>",
            "highlightPostTag": "</mark>",
        }
        filters = []
        if repository_id is not None:
            filters.append(self._repository_filter(repository_id))
        if language:
            filters.append(f'language:"{self._escape_filter_value(language)}"')
        if entity_type:
            filters.append(f'entity_type:"{self._escape_filter_value(entity_type)}"')
        if filters:
            search_params["filters"] = " AND ".join(filters)

        results = await asyncio.to_thread(self.index.search, query, search_params)
        logger.info(
            "Code search performed",
            query=query,
            hits=results.get("nbHits", 0),
            repository_id=repository_id,
        )
        return results

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        """Quote-safe facet value, so input can't add filter clauses"""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    async def delete_repository_index(self, repository_id: int, wait: bool = False) -> bool:
        """Delete all indexed entities for a repository.

        Pass wait=True before re-indexing so the delete can't land after the new records.
        """
        if not self.is_available():
            return True

        def delete():
            response = self.index.delete_by({"filters": self._repository_filter(repository_id)})
            if wait:
                response.wait()

        try:
            await asyncio.to_thread(delete)
        except Exception as e:
            logger.error(
                "Failed to delete repository from Algolia",
                repository_id=repository_id,
                error=str(e),
            )
            return False

        logger.info("Repository entities deleted from Algolia", repository_id=repository_id)
        return True

    async def get_repository_stats(self, repository_id: int) -> dict[str, Any]:
        """Entity and language counts for one repository's indexed records"""
        if not self.is_available():
            return {}

        try:
            results = await asyncio.to_thread(
                self.index.search,
                "",
                {
                    "filters": self._repository_filter(repository_id),
                    "hitsPerPage": 0,
                    "facets": ["entity_type", "language"],
                    "maxValuesPerFacet": 100,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to get repository stats",
                repository_id=repository_id,
                error=str(e),
            )
            return {}

        return {
            "total_entities": results.get("nbHits", 0),
            "entity_types": results.get("facets", {}).get("entity_type", {}),
            "languages": results.get("facets", {}).get("language", {}),
        }
