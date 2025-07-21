from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
import structlog
import asyncio

from app.core.config import get_settings
from app.services.ai_service import MCPToolsService
from app.services.algolia_service import AlgoliaService
from app.models.repository import Repository
from app.models.code_file import CodeFile
from app.models.code_entity import CodeEntity

logger = structlog.get_logger()
settings = get_settings()


class MCPResourcesService:
    """Service for MCP Resources - provides data sources to MCP clients"""

    def __init__(self, db: Session):
        self.db = db
        self.algolia_service = AlgoliaService()

    async def get_repositories(self) -> List[Dict[str, Any]]:
        """MCP Resource: Available code repositories"""
        try:
            repositories = self.db.query(Repository).all()
            return [
                {
                    "id": str(repo.id),
                    "name": repo.name,
                    "description": repo.description,
                    "language": repo.language,
                    "status": repo.status,
                    "total_files": repo.total_files,
                    "mcp_indexed": getattr(repo, "mcp_indexed", False),
                }
                for repo in repositories
            ]
        except Exception as e:
            logger.error("Failed to get repositories resource", error=str(e))
            return []

    async def get_files(
        self, repository_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """MCP Resource: Code files within repositories"""
        try:
            query = self.db.query(CodeFile)
            if repository_id:
                query = query.filter(CodeFile.repository_id == repository_id)

            files = query.limit(100).all()  # Limit for performance
            return [
                {
                    "id": str(file.id),
                    "repository_id": str(file.repository_id),
                    "file_path": file.file_path,
                    "language": file.language,
                    "size_bytes": file.size_bytes,
                    "mcp_accessible": getattr(file, "mcp_accessible", False),
                }
                for file in files
            ]
        except Exception as e:
            logger.error(
                "Failed to get files resource",
                repository_id=repository_id,
                error=str(e),
            )
            return []

    async def get_entities(
        self, repository_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """MCP Resource: Functions, classes, variables"""
        try:
            query = self.db.query(CodeEntity).join(CodeFile)
            if repository_id:
                query = query.filter(CodeFile.repository_id == repository_id)

            entities = query.limit(200).all()  # Limit for performance
            return [
                {
                    "id": str(entity.id),
                    "name": entity.name,
                    "type": entity.entity_type,
                    "file_path": entity.code_file.file_path,
                    "repository_id": str(entity.code_file.repository_id),
                    "line_range": f"{entity.start_line}-{entity.end_line}",
                    "mcp_accessible": getattr(entity, "mcp_tool_accessible", False),
                }
                for entity in entities
            ]
        except Exception as e:
            logger.error(
                "Failed to get entities resource",
                repository_id=repository_id,
                error=str(e),
            )
            return []

    async def get_search_indexes(self) -> List[Dict[str, Any]]:
        """MCP Resource: Algolia search indices status"""
        try:
            if not self.algolia_service.is_available():
                return [
                    {
                        "status": "unavailable",
                        "message": "Algolia service not configured",
                    }
                ]

            # Get index statistics
            index_stats = {
                "index_name": settings.ALGOLIA_INDEX_NAME,
                "status": "available",
                "algolia_app_id": settings.ALGOLIA_APP_ID,
                "mcp_ready": True,
            }

            try:
                # Try to get some basic stats from Algolia
                response = await self.algolia_service.search(query="*", per_page=0)
                index_stats["total_records"] = response.get("nbHits", 0)
                index_stats["last_updated"] = "dynamic"
            except Exception:
                index_stats["total_records"] = "unknown"
                index_stats["last_updated"] = "unknown"

            return [index_stats]

        except Exception as e:
            logger.error("Failed to get search indexes resource", error=str(e))
            return [{"status": "error", "message": str(e)}]


class MCPServerService:
    """Main MCP Server implementation following Model Context Protocol specification"""

    def __init__(self, db: Session):
        self.db = db
        self.tools_service = MCPToolsService()
        self.resources_service = MCPResourcesService(db)
        self.config = settings.MCP_SERVER_CONFIG

    async def get_capabilities(self) -> Dict[str, Any]:
        """Return MCP server capabilities"""
        return {
            "implementation": {
                "name": self.config["name"],
                "version": self.config["version"],
            },
            "capabilities": {
                "tools": self.config["capabilities"]["tools"],
                "resources": self.config["capabilities"]["resources"],
                "prompts": self.config["capabilities"]["prompts"],
            },
            "server_info": {
                "name": self.config["name"],
                "version": self.config["version"],
                "description": self.config["description"],
                "author": "CodeSage Team",
            },
        }

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available MCP tools"""
        tools = []

        if "search_code" in self.config["tools_enabled"]:
            tools.append(
                {
                    "name": "search_code",
                    "description": "Search code using natural language queries",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural language search query",
                            },
                            "repository": {
                                "type": "string",
                                "description": "Optional repository filter",
                            },
                            "language": {
                                "type": "string",
                                "description": "Optional programming language filter",
                            },
                            "entity_type": {
                                "type": "string",
                                "description": "Optional entity type filter (function, class, file)",
                            },
                        },
                        "required": ["query"],
                    },
                }
            )

        if "analyze_repository" in self.config["tools_enabled"]:
            tools.append(
                {
                    "name": "analyze_repository",
                    "description": "Analyze repository structure and patterns",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "repository_id": {
                                "type": "string",
                                "description": "Repository ID to analyze",
                            },
                            "analysis_type": {
                                "type": "string",
                                "description": "Type of analysis (overview, security, complexity, patterns)",
                            },
                        },
                        "required": ["repository_id"],
                    },
                }
            )

        if "explore_functions" in self.config["tools_enabled"]:
            tools.append(
                {
                    "name": "explore_functions",
                    "description": "Explore functions and classes in codebase",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "entity_name": {
                                "type": "string",
                                "description": "Optional specific entity name to search for",
                            },
                            "repository": {
                                "type": "string",
                                "description": "Optional repository filter",
                            },
                            "similarity_search": {
                                "type": "boolean",
                                "description": "Whether to find similar entities",
                            },
                        },
                    },
                }
            )

        if "explain_code" in self.config["tools_enabled"]:
            tools.append(
                {
                    "name": "explain_code",
                    "description": "Explain code snippets and patterns",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "code_snippet": {
                                "type": "string",
                                "description": "Code snippet to explain",
                            },
                            "context": {
                                "type": "string",
                                "description": "Optional context information",
                            },
                            "detail_level": {
                                "type": "string",
                                "description": "Level of detail (brief, detailed)",
                            },
                        },
                        "required": ["code_snippet"],
                    },
                }
            )

        if "find_patterns" in self.config["tools_enabled"]:
            tools.append(
                {
                    "name": "find_patterns",
                    "description": "Find code patterns and anti-patterns",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "repository_id": {
                                "type": "string",
                                "description": "Repository ID to search in",
                            },
                            "pattern_type": {
                                "type": "string",
                                "description": "Type of patterns to find (security, performance, architecture)",
                            },
                        },
                        "required": ["repository_id"],
                    },
                }
            )

        return tools

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an MCP tool call"""
        try:
            if tool_name == "search_code":
                return await self.tools_service.search_code(
                    query=arguments["query"],
                    repository=arguments.get("repository"),
                    language=arguments.get("language"),
                    entity_type=arguments.get("entity_type"),
                )

            elif tool_name == "analyze_repository":
                return await self.tools_service.analyze_repository(
                    repository_id=arguments["repository_id"],
                    analysis_type=arguments.get("analysis_type", "overview"),
                )

            elif tool_name == "explore_functions":
                return await self.tools_service.explore_functions(
                    entity_name=arguments.get("entity_name"),
                    repository=arguments.get("repository"),
                    similarity_search=arguments.get("similarity_search", False),
                )

            elif tool_name == "explain_code":
                return await self.tools_service.explain_code(
                    code_snippet=arguments["code_snippet"],
                    context=arguments.get("context"),
                    detail_level=arguments.get("detail_level", "brief"),
                )

            elif tool_name == "find_patterns":
                return await self.tools_service.find_patterns(
                    repository_id=arguments["repository_id"],
                    pattern_type=arguments.get("pattern_type", "security"),
                )

            else:
                return {
                    "error": f"Unknown tool: {tool_name}",
                    "available_tools": self.config["tools_enabled"],
                }

        except Exception as e:
            logger.error("MCP tool call failed", tool_name=tool_name, error=str(e))
            return {"error": f"Tool execution failed: {str(e)}", "tool": tool_name}

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List available MCP resources"""
        resources = []

        if "repositories" in self.config["resources_enabled"]:
            resources.append(
                {
                    "uri": "codesage://repositories",
                    "name": "Repositories",
                    "description": "Available code repositories",
                }
            )

        if "files" in self.config["resources_enabled"]:
            resources.append(
                {
                    "uri": "codesage://files",
                    "name": "Files",
                    "description": "Code files within repositories",
                }
            )

        if "entities" in self.config["resources_enabled"]:
            resources.append(
                {
                    "uri": "codesage://entities",
                    "name": "Entities",
                    "description": "Functions, classes, variables",
                }
            )

        if "search_indexes" in self.config["resources_enabled"]:
            resources.append(
                {
                    "uri": "codesage://search_indexes",
                    "name": "Search Indexes",
                    "description": "Algolia search indices status",
                }
            )

        return resources

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read an MCP resource"""
        try:
            if uri == "codesage://repositories":
                data = await self.resources_service.get_repositories()
                return {"uri": uri, "data": data, "mimeType": "application/json"}

            elif uri.startswith("codesage://files"):
                # Support filtering: codesage://files?repository_id=123
                repository_id = None
                if "?" in uri:
                    query_part = uri.split("?", 1)[1]
                    if "repository_id=" in query_part:
                        repository_id = query_part.split("repository_id=", 1)[1].split(
                            "&"
                        )[0]

                data = await self.resources_service.get_files(repository_id)
                return {"uri": uri, "data": data, "mimeType": "application/json"}

            elif uri.startswith("codesage://entities"):
                # Support filtering: codesage://entities?repository_id=123
                repository_id = None
                if "?" in uri:
                    query_part = uri.split("?", 1)[1]
                    if "repository_id=" in query_part:
                        repository_id = query_part.split("repository_id=", 1)[1].split(
                            "&"
                        )[0]

                data = await self.resources_service.get_entities(repository_id)
                return {"uri": uri, "data": data, "mimeType": "application/json"}

            elif uri == "codesage://search_indexes":
                data = await self.resources_service.get_search_indexes()
                return {"uri": uri, "data": data, "mimeType": "application/json"}

            else:
                return {
                    "error": f"Unknown resource URI: {uri}",
                    "available_resources": [
                        "codesage://repositories",
                        "codesage://files",
                        "codesage://entities",
                        "codesage://search_indexes",
                    ],
                }

        except Exception as e:
            logger.error("MCP resource read failed", uri=uri, error=str(e))
            return {"error": f"Resource read failed: {str(e)}", "uri": uri}
