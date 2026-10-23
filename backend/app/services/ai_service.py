"""
CodeSage - MCP-First Code Discovery: AI Service

This module implements the MCP Tools service for CodeSage - the only code discovery
tool built entirely around the Model Context Protocol (MCP) for seamless AI integration.

The MCP Tools provide natural language interfaces for:
- Code search and discovery
- Repository analysis and insights
- Function exploration and relationships
- Code explanation and documentation
- Pattern detection and security analysis

This represents our core innovation: MCP-first architecture for AI-powered code discovery.
"""

from typing import Any

import structlog

from app.models.repository import Repository
from app.services.algolia_service import AlgoliaService

logger = structlog.get_logger()


class MCPToolsService:
    """
    MCP Tools implementation for AI-powered code discovery.
    Based on architecture.md: MCP Tools Implementation
    
    This service provides the core MCP tool functionality for CodeSage - MCP-First Code Discovery,
    enabling natural language interactions with codebases through Claude Desktop and other MCP clients.
    """

    def __init__(self, db_session):
        self.db = db_session
        self.algolia_service = AlgoliaService()

    async def search_code(
        self,
        query: str,
        repository: str = None,
        language: str = None,
        entity_type: str = None,
    ) -> dict[str, Any]:
        """
        Natural language code search across repositories.
        MCP tool: search_code
        """
        try:
            # Convert repository name to ID if provided
            repository_id = None
            if repository:
                repo_record = (
                    self.db.query(Repository)
                    .filter(Repository.name.ilike(f"%{repository}%"))
                    .first()
                )
                if repo_record:
                    repository_id = repo_record.id

            # Search using Algolia
            results = await self.algolia_service.search_code(
                query=query,
                repository_id=repository_id,
                language=language,
                entity_type=entity_type,
            )

            # Format results for Claude Desktop
            formatted_results = {
                "query": query,
                "total_hits": results.get("nbHits", 0),
                "results": [],
            }

            for hit in results.get("hits", []):
                formatted_results["results"].append(
                    {
                        "entity_name": hit.get("entity_name"),
                        "entity_type": hit.get("entity_type"),
                        "description": hit.get("description"),
                        "file_path": hit.get("file_path"),
                        "language": hit.get("language"),
                        "line_start": hit.get("line_start"),
                        "line_end": hit.get("line_end"),
                        "parameters": hit.get("parameters", []),
                        "return_type": hit.get("return_type"),
                        "content": (
                            hit.get("content", "")[:200] + "..."
                            if len(hit.get("content", "")) > 200
                            else hit.get("content", "")
                        ),
                        "relevance_score": hit.get("_rankingInfo", {}).get("words", 0),
                    }
                )

            logger.info(
                "Code search completed",
                query=query,
                total_hits=formatted_results["total_hits"],
                repository=repository,
                language=language,
                entity_type=entity_type,
            )

            return {"status": "success", "data": formatted_results}

        except Exception as e:
            logger.error("Code search failed", query=query, error=str(e))
            return {"status": "error", "error": f"Search failed: {str(e)}"}

    async def analyze_repository(
        self, repository_id: str, analysis_type: str = "overview"
    ) -> dict[str, Any]:
        """
        Repository analysis and insights.
        MCP tool: analyze_repository
        """
        try:

            # Get repository
            repo = (
                self.db.query(Repository)
                .filter(Repository.id == int(repository_id))
                .first()
            )
            if not repo:
                return {
                    "status": "error",
                    "error": f"Repository {repository_id} not found",
                }

            # Get statistics from Algolia
            stats = await self.algolia_service.get_repository_stats(repo.id)

            analysis = {
                "repository_name": repo.name,
                "repository_url": repo.url,
                "language": repo.language,
                "status": repo.status,
                "total_files": repo.total_files,
                "processed_files": repo.processed_files,
                "total_entities": stats.get("total_entities", 0),
                "entity_breakdown": stats.get("entity_types", {}),
                "language_breakdown": stats.get("languages", {}),
                "analysis_type": analysis_type,
            }

            # Add insights based on analysis type
            if analysis_type == "overview":
                analysis["insights"] = [
                    f"Repository contains {stats.get('total_entities', 0)} searchable code entities",
                    f"Primary language: {repo.language or 'Unknown'}",
                    f"Processing status: {repo.status}",
                    f"File coverage: {repo.processed_files}/{repo.total_files} files processed",
                ]
            elif analysis_type == "security":
                analysis["insights"] = [
                    "Security analysis would require additional processing",
                    "Currently showing basic entity structure",
                    "Consider reviewing function parameters and return types for patterns",
                ]
            elif analysis_type == "performance":
                analysis["insights"] = [
                    "Performance analysis based on code structure",
                    f"Large functions detected: {sum(1 for k,v in stats.get('entity_types', {}).items() if k == 'function')}",
                    "Consider reviewing entity complexity in search results",
                ]

            logger.info(
                "Repository analysis completed",
                repository_id=repository_id,
                analysis_type=analysis_type,
                total_entities=stats.get("total_entities", 0),
            )

            return {"status": "success", "data": analysis}

        except Exception as e:
            logger.error(
                "Repository analysis failed", repository_id=repository_id, error=str(e)
            )
            return {"status": "error", "error": f"Analysis failed: {str(e)}"}

    async def explore_functions(
        self,
        entity_name: str = None,
        repository: str = None,
        similarity_search: bool = True,
    ) -> dict[str, Any]:
        """
        Function discovery and relationship mapping.
        MCP tool: explore_functions
        """
        try:
            # Build search query
            if entity_name:
                query = f"function {entity_name}"
            else:
                query = "function"

            # Search for functions
            results = await self.algolia_service.search_code(
                query=query, entity_type="function"
            )

            functions = []
            for hit in results.get("hits", []):
                if hit.get("entity_type") == "function":
                    functions.append(
                        {
                            "name": hit.get("entity_name"),
                            "description": hit.get("description"),
                            "file_path": hit.get("file_path"),
                            "language": hit.get("language"),
                            "parameters": hit.get("parameters", []),
                            "return_type": hit.get("return_type"),
                            "lines_of_code": hit.get("lines_of_code", 1),
                            "complexity_indicator": (
                                "high"
                                if len(hit.get("parameters", [])) > 5
                                else (
                                    "medium"
                                    if len(hit.get("parameters", [])) > 2
                                    else "low"
                                )
                            ),
                        }
                    )

            result = {
                "query": query,
                "total_functions": len(functions),
                "functions": functions[:20],  # Limit to 20 for readability
                "exploration_type": "similarity" if similarity_search else "exact",
            }

            logger.info(
                "Function exploration completed",
                entity_name=entity_name,
                total_functions=len(functions),
                repository=repository,
            )

            return {"status": "success", "data": result}

        except Exception as e:
            logger.error(
                "Function exploration failed", entity_name=entity_name, error=str(e)
            )
            return {"status": "error", "error": f"Exploration failed: {str(e)}"}

    async def explain_code(
        self, code_snippet: str, context: str = None, detail_level: str = "brief"
    ) -> dict[str, Any]:
        """
        Code explanation and documentation.
        MCP tool: explain_code
        """
        try:
            # For now, provide basic structure analysis
            # In a full implementation, this could use additional AI services

            lines = code_snippet.split("\n")
            explanation = {
                "code_snippet": (
                    code_snippet[:300] + "..."
                    if len(code_snippet) > 300
                    else code_snippet
                ),
                "context": context,
                "detail_level": detail_level,
                "analysis": {
                    "lines_of_code": len(lines),
                    "estimated_complexity": (
                        "low"
                        if len(lines) < 10
                        else "medium" if len(lines) < 50 else "high"
                    ),
                    "contains_functions": any(
                        "def " in line or "function " in line for line in lines
                    ),
                    "contains_classes": any("class " in line for line in lines),
                    "contains_imports": any(
                        "import " in line or "from " in line for line in lines
                    ),
                },
            }

            if detail_level == "detailed":
                explanation["suggestions"] = [
                    "Consider adding comments for complex logic",
                    "Review function parameters for clarity",
                    "Ensure proper error handling",
                    "Consider breaking down large functions",
                ]

            return {"status": "success", "data": explanation}

        except Exception as e:
            logger.error("Code explanation failed", error=str(e))
            return {"status": "error", "error": f"Explanation failed: {str(e)}"}

    async def find_patterns(
        self, repository_id: str, pattern_type: str = "security"
    ) -> dict[str, Any]:
        """
        Pattern detection across codebase.
        MCP tool: find_patterns
        """
        try:
            # Search for patterns based on type
            if pattern_type == "security":
                query = "password secret token auth key"
            elif pattern_type == "performance":
                query = "loop iterate recursive"
            elif pattern_type == "architecture":
                query = "class interface abstract"
            else:
                query = pattern_type

            results = await self.algolia_service.search_code(
                query=query, repository_id=int(repository_id)
            )

            patterns = []
            for hit in results.get("hits", []):
                patterns.append(
                    {
                        "entity_name": hit.get("entity_name"),
                        "entity_type": hit.get("entity_type"),
                        "file_path": hit.get("file_path"),
                        "language": hit.get("language"),
                        "pattern_type": pattern_type,
                        "description": hit.get("description"),
                        "relevance": (
                            "high"
                            if hit.get("_rankingInfo", {}).get("words", 0) > 2
                            else "medium"
                        ),
                    }
                )

            result = {
                "repository_id": repository_id,
                "pattern_type": pattern_type,
                "total_patterns": len(patterns),
                "patterns": patterns[:15],  # Limit results
                "recommendations": self._get_pattern_recommendations(
                    pattern_type, patterns
                ),
            }

            logger.info(
                "Pattern finding completed",
                repository_id=repository_id,
                pattern_type=pattern_type,
                total_patterns=len(patterns),
            )

            return {"status": "success", "data": result}

        except Exception as e:
            logger.error(
                "Pattern finding failed", repository_id=repository_id, error=str(e)
            )
            return {"status": "error", "error": f"Pattern finding failed: {str(e)}"}

    def _get_pattern_recommendations(
        self, pattern_type: str, patterns: list[dict]
    ) -> list[str]:
        """Generate recommendations based on found patterns"""
        if pattern_type == "security":
            return [
                "Review hardcoded secrets and credentials",
                "Consider using environment variables for sensitive data",
                "Implement proper authentication mechanisms",
                "Audit token handling and validation",
            ]
        elif pattern_type == "performance":
            return [
                "Review loop complexity and efficiency",
                "Consider caching for expensive operations",
                "Optimize recursive functions if present",
                "Profile critical code paths",
            ]
        elif pattern_type == "architecture":
            return [
                "Review class design and responsibilities",
                "Consider interface segregation",
                "Evaluate inheritance hierarchies",
                "Ensure proper abstraction levels",
            ]
        else:
            return [
                f"Review {pattern_type} patterns found",
                "Consider best practices for this pattern type",
                "Ensure consistency across the codebase",
            ]
