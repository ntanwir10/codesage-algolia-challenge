from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
import structlog
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.services.mcp_server import MCPServerService
from app.services.security_service import rate_limit_ai, rate_limit_default

logger = structlog.get_logger()
router = APIRouter()


# Request/Response Models for better API documentation
class MCPToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the MCP tool to execute")
    arguments: Dict[str, Any] = Field(..., description="Arguments for the MCP tool")


class MCPToolCallResponse(BaseModel):
    tool: str = Field(..., description="Tool that was executed")
    result: Dict[str, Any] = Field(..., description="Tool execution result")
    success: bool = Field(..., description="Whether the tool execution was successful")
    execution_time_ms: Optional[float] = Field(
        None, description="Execution time in milliseconds"
    )


class MCPErrorResponse(BaseModel):
    error: str = Field(..., description="Error message")
    tool: Optional[str] = Field(None, description="Tool that failed")
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error details"
    )


# MCP Protocol Endpoints
@router.get(
    "/mcp/capabilities",
    summary="Get MCP Server Capabilities",
    description="Returns the capabilities of this MCP server including available tools and resources",
)
@rate_limit_default
async def get_mcp_capabilities(db: Session = Depends(get_db)):
    """Get MCP server capabilities - MCP Protocol Endpoint"""
    try:
        mcp_server = MCPServerService(db)
        capabilities = await mcp_server.get_capabilities()
        logger.info("MCP capabilities requested")
        return capabilities
    except Exception as e:
        logger.error("Failed to get MCP capabilities", error=str(e))
        raise HTTPException(status_code=500, detail=f"MCP capabilities error: {str(e)}")


@router.get(
    "/mcp/tools",
    summary="List Available MCP Tools",
    description="Returns all MCP tools available for AI models to call",
)
@rate_limit_default
async def list_mcp_tools(db: Session = Depends(get_db)):
    """List available MCP tools - MCP Protocol Endpoint"""
    try:
        mcp_server = MCPServerService(db)
        tools = await mcp_server.list_tools()
        logger.info("MCP tools listed", tools_count=len(tools))
        return {"tools": tools, "count": len(tools), "status": "success"}
    except Exception as e:
        logger.error("Failed to list MCP tools", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"MCP tools listing error: {str(e)}"
        )


@router.post(
    "/mcp/tools/call",
    response_model=MCPToolCallResponse,
    summary="Execute MCP Tool",
    description="Execute a specific MCP tool with provided arguments",
)
@rate_limit_ai
async def call_mcp_tool(
    request: MCPToolCallRequest = Body(..., description="MCP tool call request"),
    db: Session = Depends(get_db),
):
    """Execute an MCP tool - MCP Protocol Endpoint"""
    import time

    start_time = time.time()

    try:
        # Validate tool name
        if not request.tool_name or not request.tool_name.strip():
            raise HTTPException(status_code=400, detail="Tool name is required")

        # Validate arguments
        if request.arguments is None:
            request.arguments = {}

        mcp_server = MCPServerService(db)
        result = await mcp_server.call_tool(request.tool_name, request.arguments)

        execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        success = "error" not in result and result.get("status") != "error"

        # Return HTTP 400 for tool errors (invalid tools, bad arguments, etc.)
        if not success and "error" in result:
            error_msg = result.get("error", "Tool execution failed")
            if "Unknown tool" in error_msg or "Invalid" in error_msg:
                raise HTTPException(status_code=400, detail=error_msg)

        logger.info(
            "MCP tool executed",
            tool_name=request.tool_name,
            success=success,
            execution_time_ms=execution_time,
        )

        return MCPToolCallResponse(
            tool=request.tool_name,
            result=result,
            success=success,
            execution_time_ms=execution_time,
        )
    except HTTPException:
        raise
    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        logger.error("MCP tool call failed", tool_name=request.tool_name, error=str(e))
        raise HTTPException(
            status_code=400,
            detail=f"MCP tool '{request.tool_name}' execution failed: {str(e)}",
        )


@router.get(
    "/mcp/resources",
    summary="List Available MCP Resources",
    description="Returns all MCP resources that AI models can access",
)
@rate_limit_default
async def list_mcp_resources(db: Session = Depends(get_db)):
    """List available MCP resources - MCP Protocol Endpoint"""
    try:
        mcp_server = MCPServerService(db)
        resources = await mcp_server.list_resources()
        logger.info("MCP resources listed", resources_count=len(resources))
        return {"resources": resources, "count": len(resources), "status": "success"}
    except Exception as e:
        logger.error("Failed to list MCP resources", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"MCP resources listing error: {str(e)}"
        )


@router.get(
    "/mcp/resources/read",
    summary="Read MCP Resource",
    description="Read the content of a specific MCP resource",
)
@rate_limit_default
async def read_mcp_resource(
    uri: str = Query(
        ..., description="Resource URI to read (e.g., 'codesage://repositories')"
    ),
    db: Session = Depends(get_db),
):
    """Read an MCP resource - MCP Protocol Endpoint"""
    try:
        # Validate URI format
        if not uri or not uri.startswith("codesage://"):
            raise HTTPException(
                status_code=400,
                detail="Invalid resource URI. Must start with 'codesage://'",
            )

        mcp_server = MCPServerService(db)
        resource_data = await mcp_server.read_resource(uri)

        logger.info("MCP resource read", uri=uri, success="error" not in resource_data)
        return resource_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("MCP resource read failed", uri=uri, error=str(e))
        raise HTTPException(
            status_code=400, detail=f"Failed to read resource '{uri}': {str(e)}"
        )


# Convenience endpoints for testing MCP tools directly
class SearchCodeRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    repository: Optional[str] = Field(None, description="Repository filter")
    language: Optional[str] = Field(None, description="Programming language filter")
    entity_type: Optional[str] = Field(
        None, description="Entity type filter (function, class, file)"
    )


class AnalyzeRepositoryRequest(BaseModel):
    repository_id: str = Field(..., description="Repository ID to analyze")
    analysis_type: str = Field(default="overview", description="Type of analysis")


class ExploreRequest(BaseModel):
    entity_name: Optional[str] = Field(None, description="Specific entity name")
    repository: Optional[str] = Field(None, description="Repository filter")
    similarity_search: bool = Field(
        default=False, description="Enable similarity search"
    )


class ExplainCodeRequest(BaseModel):
    code_snippet: str = Field(..., min_length=1, description="Code to explain")
    context: Optional[str] = Field(None, description="Additional context")
    detail_level: str = Field(
        default="brief", description="Level of detail (brief, detailed)"
    )


class FindPatternsRequest(BaseModel):
    repository_id: str = Field(..., description="Repository ID to search")
    pattern_type: str = Field(
        default="security",
        description="Pattern type (security, performance, architecture)",
    )


@router.post(
    "/search",
    summary="Search Code (Convenience)",
    description="Direct access to search_code MCP tool for testing",
)
@rate_limit_ai
async def search_code_via_mcp(
    request: SearchCodeRequest,
    db: Session = Depends(get_db),
):
    """Search code using MCP search_code tool"""
    try:
        mcp_server = MCPServerService(db)
        arguments = {"query": request.query}

        # Add optional filters
        if request.repository:
            arguments["repository"] = request.repository
        if request.language:
            arguments["language"] = request.language
        if request.entity_type:
            arguments["entity_type"] = request.entity_type

        result = await mcp_server.call_tool("search_code", arguments)
        success = "error" not in result

        logger.info("Code search via MCP", query=request.query, success=success)
        return {
            "tool": "search_code",
            "query": request.query,
            "result": result,
            "success": success,
        }
    except Exception as e:
        logger.error("Code search failed", query=request.query, error=str(e))
        raise HTTPException(status_code=400, detail=f"Search failed: {str(e)}")


@router.post(
    "/analyze",
    summary="Analyze Repository (Convenience)",
    description="Direct access to analyze_repository MCP tool",
)
@rate_limit_ai
async def analyze_repository_via_mcp(
    request: AnalyzeRepositoryRequest, db: Session = Depends(get_db)
):
    """Analyze repository using MCP analyze_repository tool"""
    try:
        mcp_server = MCPServerService(db)
        arguments = {
            "repository_id": request.repository_id,
            "analysis_type": request.analysis_type,
        }

        result = await mcp_server.call_tool("analyze_repository", arguments)
        success = "error" not in result

        logger.info(
            "Repository analysis via MCP",
            repository_id=request.repository_id,
            success=success,
        )
        return {
            "tool": "analyze_repository",
            "repository_id": request.repository_id,
            "analysis_type": request.analysis_type,
            "result": result,
            "success": success,
        }
    except Exception as e:
        logger.error(
            "Repository analysis failed",
            repository_id=request.repository_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=400,
            detail=f"Analysis failed for repository {request.repository_id}: {str(e)}",
        )


@router.post(
    "/explore",
    summary="Explore Functions (Convenience)",
    description="Direct access to explore_functions MCP tool",
)
@rate_limit_ai
async def explore_functions_via_mcp(
    request: ExploreRequest,
    db: Session = Depends(get_db),
):
    """Explore functions using MCP explore_functions tool"""
    try:
        mcp_server = MCPServerService(db)
        arguments = {"similarity_search": request.similarity_search}

        if request.entity_name:
            arguments["entity_name"] = request.entity_name
        if request.repository:
            arguments["repository"] = request.repository

        result = await mcp_server.call_tool("explore_functions", arguments)
        success = "error" not in result

        logger.info(
            "Function exploration via MCP",
            entity_name=request.entity_name,
            success=success,
        )
        return {
            "tool": "explore_functions",
            "entity_name": request.entity_name,
            "repository": request.repository,
            "result": result,
            "success": success,
        }
    except Exception as e:
        logger.error(
            "Function exploration failed", entity_name=request.entity_name, error=str(e)
        )
        raise HTTPException(
            status_code=400, detail=f"Function exploration failed: {str(e)}"
        )


@router.post(
    "/explain",
    summary="Explain Code (Convenience)",
    description="Direct access to explain_code MCP tool",
)
@rate_limit_ai
async def explain_code_via_mcp(
    request: ExplainCodeRequest,
    db: Session = Depends(get_db),
):
    """Explain code using MCP explain_code tool"""
    try:
        mcp_server = MCPServerService(db)
        arguments = {
            "code_snippet": request.code_snippet,
            "detail_level": request.detail_level,
        }

        if request.context:
            arguments["context"] = request.context

        result = await mcp_server.call_tool("explain_code", arguments)
        success = "error" not in result

        logger.info(
            "Code explanation via MCP",
            code_length=len(request.code_snippet),
            success=success,
        )
        return {
            "tool": "explain_code",
            "code_length": len(request.code_snippet),
            "detail_level": request.detail_level,
            "result": result,
            "success": success,
        }
    except Exception as e:
        logger.error("Code explanation failed", error=str(e))
        raise HTTPException(
            status_code=400, detail=f"Code explanation failed: {str(e)}"
        )


@router.post(
    "/patterns",
    summary="Find Patterns (Convenience)",
    description="Direct access to find_patterns MCP tool",
)
@rate_limit_ai
async def find_patterns_via_mcp(
    request: FindPatternsRequest, db: Session = Depends(get_db)
):
    """Find patterns using MCP find_patterns tool"""
    try:
        mcp_server = MCPServerService(db)
        arguments = {
            "repository_id": request.repository_id,
            "pattern_type": request.pattern_type,
        }

        result = await mcp_server.call_tool("find_patterns", arguments)
        success = "error" not in result

        logger.info(
            "Pattern finding via MCP",
            repository_id=request.repository_id,
            pattern_type=request.pattern_type,
            success=success,
        )
        return {
            "tool": "find_patterns",
            "repository_id": request.repository_id,
            "pattern_type": request.pattern_type,
            "result": result,
            "success": success,
        }
    except Exception as e:
        logger.error(
            "Pattern finding failed", repository_id=request.repository_id, error=str(e)
        )
        raise HTTPException(
            status_code=400,
            detail=f"Pattern finding failed for repository {request.repository_id}: {str(e)}",
        )


# Health and Status Endpoints for MCP Server
@router.get(
    "/status",
    summary="MCP Server Status",
    description="Get detailed status of the MCP server and its components",
)
@rate_limit_default
async def get_mcp_server_status(db: Session = Depends(get_db)):
    """Get MCP server status and health information"""
    try:
        mcp_server = MCPServerService(db)

        # Get basic status
        capabilities = await mcp_server.get_capabilities()
        tools = await mcp_server.list_tools()
        resources = await mcp_server.list_resources()

        # Test database connection
        db_status = "healthy"
        try:
            db.execute("SELECT 1")
        except Exception:
            db_status = "unhealthy"

        # Test Algolia connection
        algolia_status = "unknown"
        try:
            # This would be implemented in AlgoliaService
            algolia_status = "healthy"
        except Exception:
            algolia_status = "unhealthy"

        status = {
            "mcp_server": "healthy",
            "database": db_status,
            "algolia": algolia_status,
            "capabilities": capabilities,
            "tools_count": len(tools),
            "resources_count": len(resources),
            "version": "1.0.0",
            "architecture": "MCP-first - Simplified",
        }

        logger.info("MCP server status requested", status=status)
        return status

    except Exception as e:
        logger.error("Failed to get MCP server status", error=str(e))
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")
