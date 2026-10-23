from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.mcp_server import MCPServerService
from app.services.security_service import rate_limit_ai, rate_limit_default

logger = structlog.get_logger()
router = APIRouter()


# Request/Response Models for MCP protocol
class MCPToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the MCP tool to execute")
    arguments: dict[str, Any] = Field(..., description="Arguments for the MCP tool")


class MCPToolCallResponse(BaseModel):
    result: dict[str, Any] = Field(..., description="Tool execution result")
    status: str = Field(..., description="Success or error status")


# Search suggestions endpoint
@router.get(
    "/search/suggestions",
    summary="Get Search Suggestions",
    description="Get search suggestions based on a query for auto-complete",
)
@rate_limit_default
async def get_search_suggestions(
    query: str = Query(..., description="Query string to get suggestions for"),
    limit: int = Query(default=10, le=20, description="Maximum number of suggestions"),
    repository_id: int | None = Query(None, description="Optional repository ID filter"),
    db: Session = Depends(get_db),
):
    """Get search suggestions for auto-complete"""
    try:
        if len(query.strip()) < 2:
            return {"suggestions": []}

        # Use MCP tools to get suggestions based on code entities
        mcp_server = MCPServerService(db)
        
        # Search for matching entities to generate suggestions
        search_result = await mcp_server.call_tool(
            "explore_functions",
            {
                "entity_name": query,
                "repository": str(repository_id) if repository_id else None,
                "similarity_search": True,
            }
        )
        
        suggestions = []
        if search_result.get("status") == "success":
            entities = search_result.get("data", {}).get("entities", [])
            
            # Generate suggestions from entity names and common patterns
            for entity in entities[:limit//2]:
                entity_name = entity.get("entity_name", "")
                entity_type = entity.get("entity_type", "")
                
                if entity_name and query.lower() in entity_name.lower():
                    # Add direct entity matches
                    suggestions.append(f"How does {entity_name} work?")
                    if entity_type == "function":
                        suggestions.append(f"What parameters does {entity_name} take?")
                    elif entity_type == "class":
                        suggestions.append(f"What methods does {entity_name} have?")
            
            # Add common search patterns
            common_patterns = [
                f"Show me functions related to {query}",
                f"Find classes containing {query}",
                f"What is {query} used for?",
                f"How to use {query}?",
                f"Examples of {query}",
            ]
            
            for pattern in common_patterns:
                if len(suggestions) < limit:
                    suggestions.append(pattern)
        
        # Fallback generic suggestions if no specific entities found
        if not suggestions:
            generic_suggestions = [
                f"How does {query} work?",
                f"Find functions related to {query}",
                f"Show me {query} implementation",
                f"What is {query}?",
                f"Examples using {query}",
            ]
            suggestions = generic_suggestions[:limit]
        
        # Remove duplicates and limit
        unique_suggestions = list(dict.fromkeys(suggestions))[:limit]
        
        logger.info("Search suggestions generated", 
                   query=query, 
                   count=len(unique_suggestions),
                   repository_id=repository_id)
        
        return {"suggestions": unique_suggestions}
        
    except Exception as e:
        logger.error("Failed to get search suggestions", query=query, error=str(e))
        # Return fallback suggestions on error
        fallback_suggestions = [
            f"How does {query} work?",
            f"Find functions related to {query}",
            f"Show me {query} implementation",
        ]
        return {"suggestions": fallback_suggestions[:limit]}


# Core MCP Protocol Endpoints
@router.get(
    "/mcp",
    summary="MCP Server Information",
    description="Get information about available MCP endpoints and capabilities",
)
async def mcp_server_info():
    """Get MCP server information and available endpoints"""
    return {
        "server": "CodeSage MCP Server",
        "version": "1.0.0",
        "description": "AI-powered code discovery through natural language",
        "protocol": "Model Context Protocol (MCP)",
        "endpoints": {
            "capabilities": "/api/v1/ai/mcp/capabilities",
            "tools": "/api/v1/ai/mcp/tools",
            "tool_call": "/api/v1/ai/mcp/tools/call",
            "resources": "/api/v1/ai/mcp/resources/read",
        },
        "status": "operational",
    }


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
            result=result,
            status="success",
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
    "/mcp/tools/call",
    summary="Tool Call Usage Instructions",
    description="This endpoint only accepts POST requests. Returns usage instructions.",
)
async def tool_call_info():
    """GET handler for tool call endpoint - provides usage instructions"""
    return {
        "error": "Method Not Allowed",
        "message": "This endpoint only accepts POST requests",
        "usage": {
            "method": "POST",
            "endpoint": "/api/v1/ai/mcp/tools/call",
            "content_type": "application/json",
            "body_example": {
                "tool_name": "search_code",
                "arguments": {"query": "function definition"},
            },
        },
        "curl_example": 'curl -X POST http://localhost:8001/api/v1/ai/mcp/tools/call -H "Content-Type: application/json" -d \'{"tool_name": "search_code", "arguments": {"query": "function"}}\'',
    }


@router.get(
    "/mcp/resources/read",
    summary="Read MCP Resource",
    description="Read the content of a specific MCP resource. Requires 'uri' query parameter.",
)
@rate_limit_default
async def read_mcp_resource(
    uri: str = Query(
        None, description="Resource URI to read (e.g., 'codesage://repositories')"
    ),
    db: Session = Depends(get_db),
):
    """Read an MCP resource - MCP Protocol Endpoint"""
    try:
        # Check if uri is provided
        if not uri:
            return {
                "error": "Missing required parameter",
                "message": "The 'uri' query parameter is required",
                "usage": {
                    "endpoint": "/api/v1/ai/mcp/resources/read?uri=<resource_uri>",
                    "available_uris": [
                        "codesage://repositories",
                        "codesage://files?repository_id=1",
                    ],
                },
                "examples": [
                    "/api/v1/ai/mcp/resources/read?uri=codesage://repositories",
                    "/api/v1/ai/mcp/resources/read?uri=codesage://files?repository_id=1",
                ],
            }

        # Validate URI format
        if not uri.startswith("codesage://"):
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
