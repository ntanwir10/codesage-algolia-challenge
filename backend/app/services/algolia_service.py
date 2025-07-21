from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import structlog
from algoliasearch.search_client import SearchClient
from algoliasearch.exceptions import AlgoliaException

from app.core.config import get_settings
from app.models.repository import Repository
from app.models.code_file import CodeFile
from app.models.code_entity import CodeEntity
from app.models.search_index import SearchIndex

logger = structlog.get_logger()
settings = get_settings()


class AlgoliaService:
    """Service for Algolia search index management and MCP server integration"""

    def __init__(self):
        """Initialize Algolia client with credentials from settings"""
        try:
            self.client = SearchClient.create(
                app_id=settings.ALGOLIA_APP_ID, api_key=settings.algolia_admin_api_key
            )
            self.index_name = settings.ALGOLIA_INDEX_NAME
            self.index = self.client.init_index(self.index_name)
            logger.info(
                "Algolia client initialized",
                app_id=settings.ALGOLIA_APP_ID,
                index=self.index_name,
            )
        except Exception as e:
            logger.error("Failed to initialize Algolia client", error=str(e))
            self.client = None
            self.index = None

    def is_available(self) -> bool:
        """Check if Algolia service is available"""
        return self.client is not None and self.index is not None

    async def setup_index_settings(self):
        """Configure Algolia index settings for optimal code search"""
        if not self.is_available():
            logger.warning("Algolia not available, skipping index setup")
            return

        try:
            settings_config = {
                # Searchable attributes with priority
                "searchableAttributes": [
                    "title",  # Highest priority
                    "entity_name",
                    "content",
                    "summary",
                    "file_path",
                    "keywords",
                ],
                # Attributes for faceting and filtering
                "attributesForFaceting": [
                    "language",
                    "entity_type",
                    "repository_name",
                    "security_score",
                    "complexity_score",
                    "tags",
                    "categories",
                ],
                # Custom ranking for code relevance
                "customRanking": [
                    "desc(importance_score)",
                    "desc(popularity_score)",
                    "desc(security_score)",
                    "asc(complexity_score)",
                ],
                # Highlighting for search results
                "attributesToHighlight": ["title", "content", "summary", "entity_name"],
                # Snippet extraction
                "attributesToSnippet": ["content:20", "summary:15"],
                # Advanced settings for code search
                "advancedSyntax": True,
                "allowCompressionOfIntegerArray": True,
                "minWordSizefor1Typo": 4,
                "minWordSizefor2Typos": 8,
                "hitsPerPage": 20,
                "maxValuesPerFacet": 100,
                # Enable features for better search
                "removeWordsIfNoResults": "allOptional",
                "separatorsToIndex": ".",
                "queryType": "prefixAll",
            }

            await self.index.set_settings(settings_config)
            logger.info("Algolia index settings configured successfully")

        except AlgoliaException as e:
            logger.error("Failed to configure Algolia index settings", error=str(e))

    async def index_repository(self, repository: Repository, db: Session) -> bool:
        """Index all entities from a repository"""
        if not self.is_available():
            logger.warning("Algolia not available, skipping repository indexing")
            return False

        try:
            # Get all code entities for this repository
            entities = (
                db.query(CodeEntity)
                .join(CodeFile)
                .filter(CodeFile.repository_id == repository.id)
                .all()
            )

            algolia_objects = []

            # Index repository-level information
            repo_object = {
                "objectID": f"repo_{repository.id}",
                "title": f"Repository: {repository.name}",
                "content": repository.description or f"Repository {repository.name}",
                "summary": f"{repository.language} repository with {repository.total_files} files",
                "entity_type": "repository",
                "entity_name": repository.name,
                "language": repository.language,
                "file_path": "",
                "line_number": None,
                "repository_id": repository.id,
                "repository_name": repository.name,
                "tags": (
                    [repository.language, repository.framework]
                    if repository.framework
                    else [repository.language]
                ),
                "categories": ["repository"],
                "keywords": [repository.name, repository.language, "repository"],
                "security_score": repository.security_score or 50,
                "complexity_score": 5,  # Default for repositories
                "importance_score": 10,  # High importance for repositories
                "popularity_score": 0,
            }
            algolia_objects.append(repo_object)

            # Index code entities
            for entity in entities:
                entity_object = {
                    "objectID": f"entity_{entity.id}",
                    "title": f"{entity.entity_type.title()}: {entity.name}",
                    "content": entity.code_snippet or entity.signature or entity.name,
                    "summary": entity.summary or f"{entity.entity_type} {entity.name}",
                    "entity_type": entity.entity_type,
                    "entity_name": entity.name,
                    "language": entity.code_file.language,
                    "file_path": entity.code_file.file_path,
                    "line_number": entity.start_line,
                    "repository_id": repository.id,
                    "repository_name": repository.name,
                    "tags": self._generate_tags(entity),
                    "categories": [entity.entity_type, "code"],
                    "keywords": self._generate_keywords(entity),
                    "security_score": self._calculate_security_score(entity),
                    "complexity_score": entity.complexity_score or 5,
                    "importance_score": self._calculate_importance_score(entity),
                    "popularity_score": 0,
                }
                algolia_objects.append(entity_object)

                # Create/update search index record
                search_index_record = (
                    db.query(SearchIndex)
                    .filter(SearchIndex.algolia_object_id == entity_object["objectID"])
                    .first()
                )

                if not search_index_record:
                    search_index_record = SearchIndex(
                        repository_id=repository.id,
                        algolia_object_id=entity_object["objectID"],
                        index_name=self.index_name,
                        entity_type=entity.entity_type,
                        entity_id=str(entity.id),
                        entity_name=entity.name,
                        title=entity_object["title"],
                        content=entity_object["content"],
                        summary=entity_object["summary"],
                        language=entity.code_file.language,
                        file_path=entity.code_file.file_path,
                        line_number=entity.start_line,
                        tags=entity_object["tags"],
                        categories=entity_object["categories"],
                        keywords=entity_object["keywords"],
                        security_score=entity_object["security_score"],
                        complexity_score=entity_object["complexity_score"],
                        importance_score=entity_object["importance_score"],
                    )
                    db.add(search_index_record)

            # Batch upload to Algolia
            if algolia_objects:
                response = await self.index.save_objects(algolia_objects)
                logger.info(
                    "Repository indexed successfully",
                    repository_id=repository.id,
                    objects_count=len(algolia_objects),
                    task_id=response.get("taskID"),
                )

                # Mark search index records as indexed
                db.query(SearchIndex).filter(
                    SearchIndex.repository_id == repository.id
                ).update({"is_indexed": True})

                db.commit()
                return True

        except Exception as e:
            logger.error(
                "Failed to index repository", repository_id=repository.id, error=str(e)
            )
            db.rollback()
            return False

    async def search(
        self, query: str, filters: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Perform search using Algolia"""
        if not self.is_available():
            logger.warning("Algolia not available, returning empty results")
            return {"hits": [], "nbHits": 0, "query": query}

        try:
            search_params = {
                "query": query,
                "hitsPerPage": kwargs.get("per_page", 20),
                "page": kwargs.get("page", 0),
                "highlightPreTag": "<mark>",
                "highlightPostTag": "</mark>",
            }

            # Add filters if provided
            if filters:
                search_params["filters"] = filters

            # Add facets for filtering
            if kwargs.get("facets"):
                search_params["facets"] = kwargs["facets"]

            response = await self.index.search(query, search_params)

            logger.info(
                "Search completed",
                query=query,
                hits=response.get("nbHits", 0),
                processing_time=response.get("processingTimeMS", 0),
            )

            return response

        except AlgoliaException as e:
            logger.error("Search failed", query=query, error=str(e))
            return {"hits": [], "nbHits": 0, "query": query, "error": str(e)}

    async def get_suggestions(self, query: str, limit: int = 10) -> List[str]:
        """Get search suggestions based on partial query"""
        if not self.is_available():
            return []

        try:
            # Use search for suggestions with specific parameters
            response = await self.index.search(
                query,
                {
                    "hitsPerPage": limit,
                    "attributesToRetrieve": ["title", "entity_name"],
                    "attributesToHighlight": [],
                },
            )

            suggestions = []
            for hit in response.get("hits", []):
                suggestions.append(hit.get("title", ""))
                if hit.get("entity_name") and hit["entity_name"] not in suggestions:
                    suggestions.append(hit["entity_name"])

            return suggestions[:limit]

        except Exception as e:
            logger.error("Failed to get suggestions", query=query, error=str(e))
            return []

    async def reindex_repository(self, repository_id: int, db: Session):
        """Reindex specific repository"""
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            logger.error(
                "Repository not found for reindexing", repository_id=repository_id
            )
            return

        # Delete existing index entries for this repository
        await self.delete_repository_index(repository_id, db)

        # Re-index the repository
        await self.index_repository(repository, db)

        logger.info("Repository reindexed successfully", repository_id=repository_id)

    async def delete_repository_index(self, repository_id: int, db: Session):
        """Remove repository from Algolia index"""
        if not self.is_available():
            return

        try:
            # Get all search index records for this repository
            index_records = (
                db.query(SearchIndex)
                .filter(SearchIndex.repository_id == repository_id)
                .all()
            )

            if index_records:
                object_ids = [record.algolia_object_id for record in index_records]

                # Delete from Algolia
                await self.index.delete_objects(object_ids)

                # Delete from our database
                db.query(SearchIndex).filter(
                    SearchIndex.repository_id == repository_id
                ).delete()

                db.commit()

                logger.info(
                    "Repository index deleted",
                    repository_id=repository_id,
                    objects_deleted=len(object_ids),
                )

        except Exception as e:
            logger.error(
                "Failed to delete repository index",
                repository_id=repository_id,
                error=str(e),
            )
            db.rollback()

    async def reindex_all(self, db: Session):
        """Reindex all repositories"""
        repositories = (
            db.query(Repository).filter(Repository.status == "completed").all()
        )

        for repository in repositories:
            await self.reindex_repository(repository.id, db)

    def _generate_tags(self, entity: CodeEntity) -> List[str]:
        """Generate tags for code entity"""
        tags = [entity.entity_type]

        if entity.code_file.language:
            tags.append(entity.code_file.language)

        if entity.visibility:
            tags.append(entity.visibility)

        if entity.is_async:
            tags.append("async")

        if entity.is_static:
            tags.append("static")

        if entity.has_security_issues:
            tags.append("security-issue")

        return list(set(tags))  # Remove duplicates

    def _generate_keywords(self, entity: CodeEntity) -> List[str]:
        """Generate keywords for code entity"""
        keywords = [entity.name, entity.entity_type]

        if entity.code_file.language:
            keywords.append(entity.code_file.language)

        # Extract keywords from signature
        if entity.signature:
            keywords.extend(entity.signature.split())

        return list(set(keywords))  # Remove duplicates

    def _calculate_security_score(self, entity: CodeEntity) -> int:
        """Calculate security score for entity"""
        base_score = 80

        if entity.security_issues:
            # Reduce score based on number and severity of issues
            issue_count = len(entity.security_issues)
            base_score -= min(issue_count * 10, 60)

        return max(base_score, 10)  # Minimum score of 10

    def _calculate_importance_score(self, entity: CodeEntity) -> int:
        """Calculate importance score based on entity characteristics"""
        score = 5  # Base score

        # Higher score for classes and functions
        if entity.entity_type in ["class", "function", "method"]:
            score += 3

        # Higher score for public entities
        if entity.visibility == "public":
            score += 2

        # Higher score for documented entities
        if entity.docstring:
            score += 2

        # Higher score for complex entities
        if entity.complexity_score and entity.complexity_score > 7:
            score += 1

        return min(score, 10)  # Maximum score of 10
