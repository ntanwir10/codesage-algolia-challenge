from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
import structlog
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.services.mcp_server import MCPServerService
from app.services.security_service import rate_limit_ai, rate_limit_default

logger = structlog.get_logger()
router = APIRouter()


# Request/Response Models for MCP protocol
class MCPToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the MCP tool to execute")
    arguments: Dict[str, Any] = Field(..., description="Arguments for the MCP tool")


class MCPToolCallResponse(BaseModel):
    tool: str = Field(..., description="Name of the executed tool")
    result: Dict[str, Any] = Field(..., description="Tool execution result")
    success: bool = Field(..., description="Whether the tool executed successfully")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")


# Core MCP Protocol Endpoints
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
