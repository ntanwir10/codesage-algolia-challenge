"""
CodeSage - MCP-First Code Discovery: Algolia Service

Indexes code entities in Algolia and searches them for the MCP tools that
Claude Desktop and other MCP clients call.

The v3 Algolia client is synchronous, so every call runs in a worker thread
to keep the event loop (API, WebSocket, MCP) responsive.
"""

import asyncio
import hashlib
import json
import time
from typing import Any

import structlog
from algoliasearch.exceptions import RequestException
from algoliasearch.search_client import SearchClient

from app.core.config import get_settings
from app.services.code_parser import ParsedCodeEntity

logger = structlog.get_logger()
settings = get_settings()

# Records per save_objects request (Algolia's recommended batch size)
INDEX_BATCH_SIZE = 1000

# Longest waits for Algolia to publish a task; Algolia's v3 wait() has no limit
INDEX_WAIT_SECONDS = 300
DELETE_WAIT_SECONDS = 120

# Characters of entity body stored with each record, well under the 10 KB record limit
MAX_BODY_CHARS = 2000
# Algolia rejects a whole batch if one record is over 10 KB; keep headroom below it
MAX_RECORD_BYTES = 9000
# Name, description, signature and return type are display text, not the body
MAX_FIELD_CHARS = 500

# Higher ranks first when relevance ties
RANK_WEIGHTS = {"class": 3, "function": 2, "terraform_block": 2, "doc_section": 1, "import": 0}


def _fit_record(record: dict[str, Any]) -> dict[str, Any]:
    """Trim content, then parameters, until the record's UTF-8 JSON fits MAX_RECORD_BYTES"""
    while (excess := len(json.dumps(record, ensure_ascii=False).encode()) - MAX_RECORD_BYTES) > 0:
        if record["content"]:
            # Dropping n source bytes drops at least n JSON bytes, so one pass is enough
            raw = record["content"].encode()
            record["content"] = raw[: max(0, len(raw) - excess)].decode(errors="ignore")
        elif record["parameters"]:
            record["parameters"] = []
        else:
            break  # only capped fields are left
    return record

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

# One client per credentials: each holds its own HTTP connection pool, and a service is
# built per request, so a fresh client each time meant no connection reuse
_clients: dict[tuple[str, str], SearchClient] = {}


def _client_for(app_id: str, api_key: str) -> SearchClient:
    if (app_id, api_key) not in _clients:
        _clients[(app_id, api_key)] = SearchClient.create(app_id=app_id, api_key=api_key)
    return _clients[(app_id, api_key)]


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

            self.client = _client_for(settings.algolia_app_id, settings.algolia_admin_api_key)
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

    def _wait_for_task(self, response, timeout: float):
        """Block until an indexing response's tasks are published, or raise TimeoutError.

        The v3 client's response.wait() polls forever, and Algolia can leave a
        task unpublished indefinitely (an unchanged set_settings does), so poll
        get_task ourselves with a deadline.
        """
        task_ids = [raw["taskID"] for raw in getattr(response, "raw_responses", []) if "taskID" in raw]
        if not task_ids:
            response.wait()
            return
        deadline = time.monotonic() + timeout
        for task_id in task_ids:
            delay = 0.1
            while self.index.get_task(task_id).get("status") != "published":
                if time.monotonic() > deadline:
                    raise TimeoutError(f"Algolia task {task_id} not published after {timeout:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 2.0)

    async def setup_index_settings(self):
        """Apply the index settings once per process, only when the live ones differ.

        Not waited on: Algolia applies an index's tasks in order, and an
        unchanged settings task may never be reported as published.
        """
        if not self.is_available() or self.index_name in _configured_indexes:
            return

        def apply() -> bool:
            try:
                live = self.index.get_settings()
            except RequestException as e:
                if e.status_code != 404:
                    raise
                live = {}  # A new index: set_settings creates it
            if all(live.get(key) == value for key, value in INDEX_SETTINGS.items()):
                return False
            self.index.set_settings(INDEX_SETTINGS)
            return True

        try:
            changed = await asyncio.to_thread(apply)
            _configured_indexes.add(self.index_name)
            logger.info("Algolia index settings checked", index=self.index_name, changed=changed)
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
            responses = [
                self.index.save_objects(documents[start : start + INDEX_BATCH_SIZE])
                for start in range(0, len(documents), INDEX_BATCH_SIZE)
            ]
            for response in responses:
                try:
                    self._wait_for_task(response, INDEX_WAIT_SECONDS)
                except TimeoutError as e:
                    # The records were accepted; they become searchable shortly
                    logger.warning("Algolia indexing still publishing", error=str(e))
                    return

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
        signature = (entity.content or "")[:MAX_FIELD_CHARS]
        body = (entity.body or "")[:MAX_BODY_CHARS]
        # Parsers may strip the signature line while the body keeps its indentation
        repeats_signature = body.lstrip().startswith(signature.strip())
        content = f"{signature}\n{body}" if body and not repeats_signature else (body or signature)
        return _fit_record({
            "objectID": f"{repository_id}_{hashlib.sha1(entity_key.encode()).hexdigest()}",
            "repository_id": repository_id,
            "file_path": file_path,
            "entity_type": entity.entity_type,
            "entity_name": entity.name[:MAX_FIELD_CHARS],
            "description": entity.description[:MAX_FIELD_CHARS],
            "parameters": entity.parameters or [],
            "return_type": entity.return_type[:MAX_FIELD_CHARS] if entity.return_type else None,
            "line_start": entity.line_start,
            "line_end": entity.line_end,
            "language": language,
            "signature": signature,
            "content": content,
            "rank_weight": RANK_WEIGHTS.get(entity.entity_type, 0),
            "parameter_count": len(entity.parameters) if entity.parameters else 0,
            "lines_of_code": max(entity.line_end - entity.line_start + 1, 1),
        })

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
            # Natural-language questions: drop words that miss instead of returning nothing
            "removeWordsIfNoResults": "allOptional",
            "removeStopWords": True,
            "ignorePlurals": True,
            "queryLanguages": ["en"],
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
                # A timeout here fails the caller rather than risking stale records
                self._wait_for_task(response, DELETE_WAIT_SECONDS)

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
