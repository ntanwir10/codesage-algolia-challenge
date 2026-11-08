"""MCP over streamable HTTP at /mcp, for clients that connect to a URL (ChatGPT, remote IDE agents).

The same server as the stdio bridge (codesage_mcp.server.build_server), but its tools run in this
process instead of over HTTP. Each request gets its own stateless session manager, so nothing
depends on the app's lifespan, which serverless hosts may never run.
"""

import json
from typing import Any

import mcp_types as types
import structlog
from limits import parse
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import api_key_is_valid, limiter
from app.services import mcp_tools
from app.services.mcp_tools import ToolError
from codesage_mcp.server import build_server

logger = structlog.get_logger()
# Shown instead of an unexpected error's text, which can carry SQL and file contents
INTERNAL_ERROR = "CodeSage hit an internal error; try again later."


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(text=message)], is_error=True)


class LocalBackend:
    """The bridge's three backend calls, answered from this process's database and Algolia"""

    async def call_tool(self, name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
        available = mcp_tools.available_tools()
        if name not in available:
            return _error(f"Unknown tool '{name}'. Available tools: {', '.join(available)}")
        with SessionLocal() as db:
            try:
                result = await mcp_tools.call_tool(db, name, arguments or {})
            except ValidationError as exc:
                problems = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()
                )
                return _error(f"Invalid arguments for '{name}': {problems}")
            except ToolError as exc:
                return _error(str(exc))
            except Exception:
                logger.exception("MCP tool failed", tool=name)
                return _error(INTERNAL_ERROR)
        # The same JSON as text too, for clients that predate structuredContent
        text = json.dumps(result, indent=2, default=str)
        return types.CallToolResult(content=[types.TextContent(text=text)], structured_content=result)

    async def list_resources(self) -> types.ListResourcesResult:
        return types.ListResourcesResult(
            resources=[
                types.Resource(uri=r["uri"], name=r["name"], description=r["description"], mime_type=r["mimeType"])
                for r in mcp_tools.list_resources()
            ]
        )

    async def read_resource(self, uri: str) -> types.ReadResourceResult:
        with SessionLocal() as db:
            try:
                body = await mcp_tools.read_resource(db, str(uri))
            except ToolError as exc:
                raise MCPError(types.INVALID_PARAMS, str(exc)) from exc
            except Exception as exc:
                logger.exception("MCP resource read failed", uri=str(uri))
                raise MCPError(types.INTERNAL_ERROR, INTERNAL_ERROR) from exc
        text = json.dumps(body["content"], indent=2, default=str)
        return types.ReadResourceResult(
            contents=[types.TextResourceContents(uri=body["uri"], mime_type=body["mimeType"], text=text)]
        )


server = build_server(backend=LocalBackend(), tool_names=mcp_tools.available_tools)


def _api_key(request: Request) -> str | None:
    """X-API-Key, as the REST API takes it, or a bearer token, which URL-based clients send"""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return request.headers.get("x-api-key") or (token.strip() if scheme.lower() == "bearer" else None)


class MCPEndpoint:
    """ASGI app for /mcp. FastAPI's route dependencies and slowapi don't run for a raw ASGI
    route, so the key and rate-limit checks the REST tool endpoint has are made here"""

    async def __call__(self, scope, receive, send):
        request = Request(scope)
        if not api_key_is_valid(_api_key(request)):
            response = JSONResponse(
                {"detail": "Invalid or missing API key"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return
        rate = parse(get_settings().rate_limit_ai)
        if limiter.enabled and not limiter.limiter.hit(rate, "mcp", get_remote_address(request)):
            seconds = rate.get_expiry()
            response = JSONResponse(
                {"detail": f"Too many requests; try again in {seconds} seconds."},
                status_code=429,
                headers={"Retry-After": str(seconds)},
            )
            await response(scope, receive, send)
            return
        # run() can be entered once per manager, so each request gets its own (stateless: no session to keep)
        manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True)
        async with manager.run():
            await manager.handle_request(scope, receive, send)
