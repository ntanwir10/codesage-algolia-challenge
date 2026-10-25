"""Stdio MCP server that exposes CodeSage tools by calling the backend over HTTP.

Configuration comes from the environment only:
    MCP_SERVER_URL    backend base URL (default http://127.0.0.1:8001)
    CODESAGE_API_KEY  sent as X-API-Key when set
    CODESAGE_BASIC_AUTH_USER / CODESAGE_BASIC_AUTH_PASSWORD
                      login for a basic-auth proxy (the prod nginx); the launcher
                      reads the password from the macOS Keychain
    CODESAGE_ALLOW_INSECURE_AUTH=1
                      allow the key or login over plain http to a non-loopback host

Tool schemas are single-sourced from ``codesage_mcp.schemas``, so ``tools/list``
works even when the backend is down. stdout carries protocol messages only;
all logging goes to stderr.
"""

import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx
import mcp_types as types
from mcp.server import Server
from mcp.server.context import ServerRequestContext
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from codesage_mcp.schemas import TOOLS, input_schema

logger = logging.getLogger("codesage_mcp")

DEFAULT_SERVER_URL = "http://127.0.0.1:8001"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
API_PREFIX = "/api/v1/ai"
REQUEST_TIMEOUT = 30.0
SERVER_NAME = "codesage"
SERVER_VERSION = "1.0.0"


@dataclass(frozen=True)
class Config:
    server_url: str = DEFAULT_SERVER_URL
    api_key: str | None = None
    basic_user: str | None = None
    basic_password: str | None = None
    allow_insecure_auth: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        env = os.environ
        url = env.get("MCP_SERVER_URL", "").strip() or DEFAULT_SERVER_URL
        return cls(
            server_url=url.rstrip("/"),
            api_key=env.get("CODESAGE_API_KEY", "").strip() or None,
            basic_user=env.get("CODESAGE_BASIC_AUTH_USER", "").strip() or None,
            basic_password=env.get("CODESAGE_BASIC_AUTH_PASSWORD") or None,
            allow_insecure_auth=env.get("CODESAGE_ALLOW_INSECURE_AUTH") == "1",
        )

    @property
    def auth(self) -> tuple[str, str] | None:
        return (self.basic_user, self.basic_password or "") if self.basic_user else None

    @property
    def insecure_auth_problem(self) -> str | None:
        """Why the key or login must not be sent: over plain http it's readable on the network"""
        parts = urlsplit(self.server_url)
        has_secret = bool(self.api_key or self.basic_user or parts.username)
        if not has_secret or self.allow_insecure_auth or parts.scheme == "https":
            return None
        if parts.hostname in LOOPBACK_HOSTS:
            return None
        return (
            f"Refusing to send the CodeSage key or login over plain http to {parts.hostname}; "
            "use an https:// MCP_SERVER_URL, or set CODESAGE_ALLOW_INSECURE_AUTH=1 on a trusted network"
        )

    @property
    def base_url(self) -> str:
        return self.server_url + API_PREFIX

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key} if self.api_key else {}


ClientFactory = Callable[[Config], httpx.AsyncClient]


def default_client_factory(config: Config) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=config.base_url, headers=config.headers, auth=config.auth, timeout=REQUEST_TIMEOUT
    )


class BackendUnreachable(Exception):
    pass


class CodeSageBridge:
    """Translates MCP requests into CodeSage backend HTTP calls."""

    def __init__(self, config: Config, client_factory: ClientFactory = default_client_factory):
        self.config = config
        self._client_factory = client_factory

    def not_reachable_message(self) -> str:
        return f"CodeSage backend not reachable at {self.config.server_url}; start it with `make start-backend`"

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """One request with a single retry on connection failure."""
        last: Exception | None = None
        for attempt in range(2):
            try:
                async with self._client_factory(self.config) as client:
                    return await client.request(method, path, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last = exc
                logger.warning("backend connection failed (attempt %d): %s", attempt + 1, exc)
        raise BackendUnreachable from last

    @staticmethod
    def _error(message: str) -> types.CallToolResult:
        return types.CallToolResult(content=[types.TextContent(text=message)], is_error=True)

    @staticmethod
    def _detail(response: httpx.Response) -> Any:
        try:
            body = response.json()
        except ValueError:
            return response.text[:500]
        return body.get("detail", body) if isinstance(body, dict) else body

    def _http_error(self, response: httpx.Response, tool: str) -> types.CallToolResult:
        status = response.status_code
        detail = self._detail(response)
        if status == 401 and "basic" in response.headers.get("www-authenticate", "").lower():
            # Only a basic-auth proxy (the prod nginx) asks for a login; the backend never does
            msg = (
                "The proxy in front of CodeSage rejected the login (401); check the user and "
                "password (CODESAGE_BASIC_AUTH_USER and its Keychain entry)"
            )
        elif status == 401:
            msg = "CodeSage backend rejected the API key (401); check CODESAGE_API_KEY in the MCP server config"
        elif status == 404:
            msg = f"Unknown tool '{tool}' (404): {detail}"
        elif status == 422:
            msg = f"Invalid arguments for '{tool}' (422): {json.dumps(detail, indent=2)}"
        elif status == 429:
            msg = "CodeSage backend rate limit exceeded (429); wait a moment and retry"
        elif status >= 500:
            msg = f"CodeSage backend error ({status}): {detail}"
        else:
            msg = f"Unexpected response from CodeSage backend ({status}): {detail}"
        return self._error(msg)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
        spec = TOOLS.get(name)
        if spec is None:
            return self._error(f"Unknown tool '{name}'. Available tools: {', '.join(TOOLS)}")
        if problem := self.config.insecure_auth_problem:
            return self._error(problem)
        try:
            args = spec.args_model.model_validate(arguments or {})
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
                for e in exc.errors()
            )
            return self._error(f"Invalid arguments for '{name}': {problems}")

        payload = {"tool_name": name, "arguments": args.model_dump(exclude_none=True)}
        try:
            response = await self._request("POST", "/mcp/tools/call", json=payload)
        except BackendUnreachable:
            return self._error(self.not_reachable_message())
        except httpx.HTTPError as exc:
            return self._error(f"CodeSage backend request failed: {type(exc).__name__}: {exc}")

        if response.status_code != 200:
            return self._http_error(response, name)
        try:
            body = response.json()
        except ValueError:
            return self._error("CodeSage backend returned a non-JSON response")
        if body.get("is_error"):
            return self._error(str(body.get("error") or "Tool failed"))
        text = json.dumps(body.get("result"), indent=2, default=str)
        return types.CallToolResult(content=[types.TextContent(text=text)])

    async def list_resources(self) -> types.ListResourcesResult:
        response = await self._resource_request("/mcp/resources")
        resources = [
            types.Resource(
                uri=r["uri"],
                name=r.get("name") or r["uri"],
                description=r.get("description"),
                mime_type=r.get("mimeType"),
            )
            for r in response.json().get("resources", [])
        ]
        return types.ListResourcesResult(resources=resources)

    async def read_resource(self, uri: str) -> types.ReadResourceResult:
        response = await self._resource_request("/mcp/resources/read", params={"uri": uri})
        body = response.json()
        content = body.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, indent=2, default=str)
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=body.get("uri", uri), mime_type=body.get("mimeType"), text=content
                )
            ]
        )

    async def _resource_request(self, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._request("GET", path, **kwargs)
        except BackendUnreachable:
            raise MCPError(types.INTERNAL_ERROR, self.not_reachable_message()) from None
        except httpx.HTTPError as exc:
            raise MCPError(types.INTERNAL_ERROR, f"CodeSage backend request failed: {exc}") from exc
        if response.status_code == 200:
            return response
        detail = self._detail(response)
        if response.status_code == 404:
            raise MCPError(types.INVALID_PARAMS, f"Resource not found: {detail}")
        if response.status_code == 401:
            raise MCPError(
                types.INTERNAL_ERROR,
                "CodeSage backend rejected the API key; check CODESAGE_API_KEY",
            )
        raise MCPError(
            types.INTERNAL_ERROR, f"CodeSage backend error ({response.status_code}): {detail}"
        )


def build_server(
    config: Config | None = None, client_factory: ClientFactory = default_client_factory
) -> Server:
    bridge = CodeSageBridge(config or Config.from_env(), client_factory)

    async def on_list_tools(
        ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=s.name, description=s.description, input_schema=input_schema(s.name)
                )
                for s in TOOLS.values()
            ]
        )

    async def on_call_tool(
        ctx: ServerRequestContext, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        return await bridge.call_tool(params.name, params.arguments)

    async def on_list_resources(
        ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListResourcesResult:
        return await bridge.list_resources()

    async def on_read_resource(
        ctx: ServerRequestContext, params: types.ReadResourceRequestParams
    ) -> types.ReadResourceResult:
        return await bridge.read_resource(params.uri)

    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        instructions="Search and inspect code repositories indexed by CodeSage.",
        get_tool_input_schema=lambda name: input_schema(name) if name in TOOLS else None,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
        on_list_resources=on_list_resources,
        on_read_resource=on_read_resource,
    )


async def run_stdio() -> None:
    from mcp.server.stdio import stdio_server

    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("CODESAGE_MCP_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    config = Config.from_env()
    logger.info(
        "CodeSage MCP bridge starting; backend=%s api_key=%s",
        config.server_url,
        bool(config.api_key),
    )
    server = build_server(config)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
