"""MCP tool endpoints served to MCP clients (through the bridge) and the web UI."""

import asyncio
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import limiter, require_api_key
from app.services import algolia_service, embeddings, mcp_tools
from app.services.mcp_tools import ToolError
from codesage_mcp import schemas

logger = structlog.get_logger()
router = APIRouter()
settings = get_settings()


class MCPToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the MCP tool to execute")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")


# Searches every repository, like the search_code tool, so it takes the same key
@router.get(
    "/search/suggestions",
    summary="Get Search Suggestions",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(lambda: settings.rate_limit_default)
async def get_search_suggestions(
    request: Request,  # slowapi needs the request under this name
    query: str = Query(..., description="Query string to get suggestions for"),
    limit: int = Query(default=10, ge=1, le=20, description="Maximum number of suggestions"),
    repository_id: int | None = Query(None, description="Optional repository ID filter"),
    mode: Literal["keyword", "semantic"] = Query(
        "keyword", description="semantic: names of the definitions closest in meaning (needs EMBEDDING_API_KEY)"
    ),
    db: Session = Depends(get_db),
):
    """Distinct entity names matching the query, for auto-complete"""
    # Punctuation alone would match every record once Algolia drops it
    if len(query.strip()) < 2 or not any(c.isalnum() for c in query):
        return {"suggestions": []}
    if mode == "semantic":
        return {"suggestions": await _semantic_suggestions(db, query, limit, repository_id)}
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


async def _semantic_suggestions(db: Session, query: str, limit: int, repository_id: int | None) -> list[str]:
    """Names of the definitions closest in meaning; nothing on any failure, like the keyword path"""
    if not embeddings.is_configured():
        return []
    try:
        [blob] = await embeddings.embed([query], kind="query")
        scored = await asyncio.to_thread(mcp_tools.rank_definitions, db, embeddings.unpack(blob), repository_id)
    except Exception as exc:
        logger.warning("Semantic suggestions unavailable", error=str(exc))
        return []
    names: list[str] = []
    for _, entity, _, _ in scored:
        if entity.entity_name not in names:
            names.append(entity.entity_name)
            if len(names) == limit:
                break
    return names


@router.get("/mcp/capabilities", summary="MCP Capabilities")
async def get_mcp_capabilities():
    config = settings.MCP_SERVER_CONFIG
    return {
        "name": config["name"],
        "version": config["version"],
        "capabilities": config["capabilities"],
        "tools": list(schemas.TOOLS),
        # Lets the dashboard offer search by meaning only when the server can do it
        "semantic_search": embeddings.is_configured(),
    }


@router.get("/mcp/tools", summary="List MCP Tools")
async def list_mcp_tools():
    tools = [
        {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": schemas.input_schema(spec.name),
            "outputSchema": schemas.output_schema(spec.name),
        }
        for spec in schemas.TOOLS.values()
    ]
    return {"tools": tools, "count": len(tools)}


@router.post(
    "/mcp/tools/call",
    summary="Call MCP Tool",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(lambda: settings.rate_limit_ai)
async def call_mcp_tool(
    request: Request,  # slowapi needs the request under this name
    payload: MCPToolCallRequest = Body(...),
    db: Session = Depends(get_db),
):
    if payload.tool_name not in schemas.TOOLS:
        raise HTTPException(status_code=404, detail=f"Unknown tool '{payload.tool_name}'")
    try:
        result = await mcp_tools.call_tool(db, payload.tool_name, payload.arguments)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=jsonable_encoder(exc.errors(include_url=False, include_context=False))
        ) from exc
    except ToolError as exc:
        return {"tool": payload.tool_name, "result": None, "is_error": True, "error": str(exc)}
    return {"tool": payload.tool_name, "result": result, "is_error": False, "error": None}


@router.get("/mcp/resources", summary="List MCP Resources")
async def list_mcp_resources():
    resources = mcp_tools.list_resources()
    return {"resources": resources, "count": len(resources)}


# Lists a repository's file paths, which no public GET shows, so it takes the key like the tools
@router.get(
    "/mcp/resources/read",
    summary="Read MCP Resource",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(lambda: settings.rate_limit_ai)
async def read_mcp_resource(
    request: Request,  # slowapi needs the request under this name
    uri: str = Query(..., description="Resource URI"),
    db: Session = Depends(get_db),
):
    try:
        return await mcp_tools.read_resource(db, uri)
    except ToolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
