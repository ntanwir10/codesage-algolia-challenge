from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import structlog

from app.core.config import get_settings
from app.services.algolia_service import AlgoliaService

logger = structlog.get_logger()
settings = get_settings()


class MCPToolsService:
    """Service for MCP (Model Context Protocol) Tools - NO DIRECT AI API CALLS

    This service implements MCP tools that AI models can call through the MCP protocol.
    All AI capabilities come through MCP clients, not direct API calls.
    """

    def __init__(self):
        self.algolia_service = AlgoliaService()

    async def search_code(
        self,
        query: str,
        repository: Optional[str] = None,
        language: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MCP Tool: Search code using natural language queries

        This tool is called by AI models through MCP protocol.
        """
        try:
            # Build Algolia filters
            filters = []
            if repository:
                filters.append(f"repository:'{repository}'")
            if language:
                filters.append(f"language:'{language}'")
            if entity_type:
                filters.append(f"type:'{entity_type}'")

            filter_string = " AND ".join(filters) if filters else None

            # Search via Algolia
            response = await self.algolia_service.search(
                query=query, filters=filter_string, per_page=20
            )

            logger.info(
                "MCP search_code tool executed",
                query=query,
                results=response.get("nbHits", 0),
            )

            return {
                "tool": "search_code",
                "query": query,
                "results": response.get("hits", []),
                "total_hits": response.get("nbHits", 0),
                "processing_time_ms": response.get("processingTimeMS", 0),
                "filters_applied": filter_string,
            }

        except Exception as e:
            logger.error("MCP search_code tool failed", query=query, error=str(e))
            return {"tool": "search_code", "error": str(e), "query": query}

    async def analyze_repository(
        self, repository_id: str, analysis_type: Optional[str] = "overview"
    ) -> Dict[str, Any]:
        """MCP Tool: Analyze repository structure and patterns"""
        try:
            # Get repository data from Algolia
            response = await self.algolia_service.search(
                query="*",
                filters=f"repository_id:'{repository_id}'",
                facets=["language", "type", "complexity", "tags"],
            )

            hits = response.get("hits", [])
            facets = response.get("facets", {})

            # Analyze patterns
            analysis = {
                "tool": "analyze_repository",
                "repository_id": repository_id,
                "analysis_type": analysis_type,
                "total_entities": len(hits),
                "languages": list(facets.get("language", {}).keys()),
                "entity_types": facets.get("type", {}),
                "complexity_distribution": facets.get("complexity", {}),
                "common_tags": facets.get("tags", {}),
                "insights": self._generate_repository_insights(hits, facets),
            }

            logger.info(
                "MCP analyze_repository tool executed",
                repository_id=repository_id,
                entities_found=len(hits),
            )

            return analysis

        except Exception as e:
            logger.error(
                "MCP analyze_repository tool failed",
                repository_id=repository_id,
                error=str(e),
            )
            return {
                "tool": "analyze_repository",
                "error": str(e),
                "repository_id": repository_id,
            }

    async def explore_functions(
        self,
        entity_name: Optional[str] = None,
        repository: Optional[str] = None,
        similarity_search: bool = False,
    ) -> Dict[str, Any]:
        """MCP Tool: Explore functions and classes in codebase"""
        try:
            query = entity_name if entity_name else "*"
            filters = []

            if repository:
                filters.append(f"repository:'{repository}'")

            # Focus on functions and classes
            filters.append("type:function OR type:class OR type:method")

            filter_string = (
                " AND ".join(filters)
                if filters
                else "type:function OR type:class OR type:method"
            )

            response = await self.algolia_service.search(
                query=query, filters=filter_string, per_page=50
            )

            hits = response.get("hits", [])

            result = {
                "tool": "explore_functions",
                "query": entity_name,
                "repository": repository,
                "functions_found": len(hits),
                "entities": [
                    {
                        "name": hit.get("name"),
                        "type": hit.get("type"),
                        "file_path": hit.get("file_path"),
                        "description": hit.get("description", ""),
                        "complexity": hit.get("complexity", 0),
                        "line_range": f"{hit.get('start_line', 0)}-{hit.get('end_line', 0)}",
                    }
                    for hit in hits
                ],
            }

            logger.info(
                "MCP explore_functions tool executed",
                entity_name=entity_name,
                functions_found=len(hits),
            )

            return result

        except Exception as e:
            logger.error(
                "MCP explore_functions tool failed",
                entity_name=entity_name,
                error=str(e),
            )
            return {
                "tool": "explore_functions",
                "error": str(e),
                "entity_name": entity_name,
            }

    async def explain_code(
        self,
        code_snippet: str,
        context: Optional[str] = None,
        detail_level: str = "brief",
    ) -> Dict[str, Any]:
        """MCP Tool: Explain code snippets and patterns

        Note: This provides structural analysis only.
        AI explanation comes through MCP client capabilities.
        """
        try:
            # Basic code analysis without AI
            analysis = {
                "tool": "explain_code",
                "code_length": len(code_snippet),
                "line_count": len(code_snippet.split("\n")),
                "context": context,
                "detail_level": detail_level,
                "structural_info": {
                    "has_functions": "def " in code_snippet
                    or "function " in code_snippet,
                    "has_classes": "class " in code_snippet,
                    "has_imports": "import " in code_snippet
                    or "#include" in code_snippet,
                    "has_comments": "#" in code_snippet
                    or "//" in code_snippet
                    or "/*" in code_snippet,
                },
                "note": "Full explanation provided by MCP client AI capabilities",
            }

            # Find similar patterns in codebase
            if len(code_snippet) > 50:  # Only for substantial code snippets
                similar_response = await self.algolia_service.search(
                    query=code_snippet[:200],  # Use first 200 chars for similarity
                    per_page=5,
                )

                analysis["similar_patterns"] = [
                    {
                        "file_path": hit.get("file_path"),
                        "name": hit.get("name"),
                        "similarity_score": hit.get("_highlightResult", {}).get(
                            "_score", 0
                        ),
                    }
                    for hit in similar_response.get("hits", [])
                ]

            logger.info("MCP explain_code tool executed", code_length=len(code_snippet))
            return analysis

        except Exception as e:
            logger.error("MCP explain_code tool failed", error=str(e))
            return {"tool": "explain_code", "error": str(e)}

    async def find_patterns(
        self, repository_id: str, pattern_type: str = "security"
    ) -> Dict[str, Any]:
        """MCP Tool: Find code patterns and anti-patterns"""
        try:
            # Define pattern search queries
            pattern_queries = {
                "security": [
                    "password",
                    "secret",
                    "token",
                    "auth",
                    "crypto",
                    "sql injection",
                    "xss",
                    "csrf",
                    "vulnerability",
                ],
                "performance": [
                    "loop",
                    "optimization",
                    "cache",
                    "async",
                    "parallel",
                    "performance",
                    "bottleneck",
                ],
                "architecture": [
                    "pattern",
                    "design",
                    "architecture",
                    "structure",
                    "class",
                    "interface",
                    "factory",
                    "singleton",
                ],
            }

            queries = pattern_queries.get(pattern_type, ["pattern"])
            all_patterns = []

            for query in queries:
                response = await self.algolia_service.search(
                    query=query, filters=f"repository_id:'{repository_id}'", per_page=10
                )

                for hit in response.get("hits", []):
                    all_patterns.append(
                        {
                            "pattern_type": pattern_type,
                            "query_matched": query,
                            "entity_name": hit.get("name"),
                            "file_path": hit.get("file_path"),
                            "description": hit.get("description", ""),
                            "tags": hit.get("tags", []),
                        }
                    )

            result = {
                "tool": "find_patterns",
                "repository_id": repository_id,
                "pattern_type": pattern_type,
                "patterns_found": len(all_patterns),
                "patterns": all_patterns[:20],  # Limit to top 20
            }

            logger.info(
                "MCP find_patterns tool executed",
                repository_id=repository_id,
                pattern_type=pattern_type,
                patterns_found=len(all_patterns),
            )

            return result

        except Exception as e:
            logger.error(
                "MCP find_patterns tool failed",
                repository_id=repository_id,
                error=str(e),
            )
            return {
                "tool": "find_patterns",
                "error": str(e),
                "repository_id": repository_id,
                "pattern_type": pattern_type,
            }

    def _generate_repository_insights(
        self, hits: List[Dict], facets: Dict
    ) -> List[str]:
        """Generate insights from repository analysis"""
        insights = []

        total_entities = len(hits)
        if total_entities == 0:
            return ["No code entities found in this repository"]

        # Language insights
        languages = facets.get("language", {})
        if languages:
            primary_language = max(languages, key=languages.get)
            insights.append(
                f"Primary language: {primary_language} ({languages[primary_language]} entities)"
            )

        # Entity type insights
        entity_types = facets.get("type", {})
        if entity_types:
            most_common_type = max(entity_types, key=entity_types.get)
            insights.append(
                f"Most common entity type: {most_common_type} ({entity_types[most_common_type]} occurrences)"
            )

        # Complexity insights
        complexity_data = facets.get("complexity", {})
        if complexity_data:
            high_complexity = sum(
                count
                for level, count in complexity_data.items()
                if level and int(level) > 7
            )
            if high_complexity > 0:
                insights.append(f"{high_complexity} entities have high complexity (>7)")

        # Tag insights
        tags = facets.get("tags", {})
        if tags:
            common_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append(
                f"Common tags: {', '.join([tag for tag, _ in common_tags])}"
            )

        return insights
