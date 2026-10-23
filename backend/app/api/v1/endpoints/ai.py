"""MCP tool endpoints served to Claude Desktop and the web UI."""

from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services import algolia_service, mcp_tools
from app.services.mcp_tools import ToolError
from codesage_mcp import schemas

logger = structlog.get_logger()
router = APIRouter()
settings = get_settings()


class MCPToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the MCP tool to execute")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")


@router.get("/search/suggestions", summary="Get Search Suggestions")
async def get_search_suggestions(
    query: str = Query(..., description="Query string to get suggestions for"),
    limit: int = Query(default=10, ge=1, le=20, description="Maximum number of suggestions"),
    repository_id: int | None = Query(None, description="Optional repository ID filter"),
):
    """Distinct entity names matching the query, for auto-complete"""
    if len(query.strip()) < 2:
        return {"suggestions": []}
    try:
        response = await algolia_service.AlgoliaService().search_code(
            query, repository_id, hits_per_page=limit * 2
        )
    except Exception as exc:
        logger.warning("Suggestions unavailable", error=str(exc))
        return {"suggestions": []}

    names: list[str] = []
    for hit in response.get("hits", []):
        name = hit.get("entity_name")
        if name and name not in names:
            names.append(name)
    return {"suggestions": names[:limit]}


@router.get("/mcp/capabilities", summary="MCP Capabilities")
async def get_mcp_capabilities():
    config = settings.MCP_SERVER_CONFIG
    return {
        "name": config["name"],
        "version": config["version"],
        "capabilities": {"tools": True, "resources": True, "prompts": False},
        "tools": list(schemas.TOOLS),
    }


@router.get("/mcp/tools", summary="List MCP Tools")
async def list_mcp_tools():
    tools = [
        {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": schemas.input_schema(spec.name),
        }
        for spec in schemas.TOOLS.values()
    ]
    return {"tools": tools, "count": len(tools)}


# TODO(phase-2-merge): add the API-key dependency and the AI rate limit to this route
@router.post("/mcp/tools/call", summary="Call MCP Tool")
async def call_mcp_tool(
    request: MCPToolCallRequest = Body(...),
    db: Session = Depends(get_db),
):
    if request.tool_name not in schemas.TOOLS:
        raise HTTPException(status_code=404, detail=f"Unknown tool '{request.tool_name}'")
    try:
        result = await mcp_tools.call_tool(db, request.tool_name, request.arguments)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=jsonable_encoder(exc.errors(include_url=False, include_context=False))
        ) from exc
    except ToolError as exc:
        return {"tool": request.tool_name, "result": None, "is_error": True, "error": str(exc)}
    return {"tool": request.tool_name, "result": result, "is_error": False, "error": None}


@router.get("/mcp/resources", summary="List MCP Resources")
async def list_mcp_resources():
    resources = mcp_tools.list_resources()
    return {"resources": resources, "count": len(resources)}


@router.get("/mcp/resources/read", summary="Read MCP Resource")
async def read_mcp_resource(
    uri: str = Query(..., description="Resource URI"),
    db: Session = Depends(get_db),
):
    try:
        return await mcp_tools.read_resource(db, uri)
    except ToolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
