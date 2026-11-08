"""API-key authentication, browser request checks and rate limiting."""

import ipaddress
import secrets

from fastapi import Header, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.core.config import LOOPBACK_HOSTS, get_settings, host_is_allowed, host_without_port

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, enabled=settings.enable_rate_limiting)


def api_key_is_valid(key: str | None) -> bool:
    """True when no key is configured, or `key` matches the configured one."""
    expected = get_settings().codesage_api_key
    if not expected:
        return True
    if not key:
        return False
    return secrets.compare_digest(key.encode(), expected.encode())


async def require_api_key(x_api_key: str | None = Header(None)) -> None:
    """FastAPI dependency guarding write endpoints."""
    if not api_key_is_valid(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


READ_ONLY_MESSAGE = "This CodeSage is read-only: repositories can't be added, reprocessed or deleted here"


async def require_writable() -> None:
    """FastAPI dependency refusing every write on a read-only server, whatever the key."""
    if get_settings().read_only:
        raise HTTPException(status_code=403, detail=READ_ONLY_MESSAGE)


def failure_message(error: Exception) -> str:
    """What a failed run records and broadcasts; the full error goes to the log only"""
    # A SQLAlchemy error's text carries the SQL and its parameters, which include file contents
    if isinstance(error, SQLAlchemyError):
        return "Database error while storing the repository"
    # These errors' messages are already written for the person reading them
    if getattr(error, "user_facing", False):
        return str(error)[:500]
    return f"{type(error).__name__}: {error}"[:500]


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _is_loopback_peer(client) -> bool:
    try:
        return ipaddress.ip_address(client[0]).is_loopback
    except (TypeError, IndexError, ValueError):  # no peer (unix socket) or not an IP
        return False


def request_refusal(scope) -> str | None:
    """Why a request a browser may have been tricked into sending must be refused.

    The key alone can't tell: prod nginx adds it to every request carrying the
    browser's cached login, and with no key configured there is nothing to check.
    """
    settings = get_settings()
    headers = Headers(scope=scope)
    host = headers.get("host", "")
    # DNS rebinding: a hostile page re-pointed at this server is same-origin but keeps its own Host.
    # With a key set it still matters: the dev bundle embeds the key, and such a page could read it
    # /health is exempt: it reveals nothing, and load balancers often address it by IP. With a key, a
    # request with no Host at all (HTTP/1.0) is not a browser's, since browsers always send one
    # Read-only serves the public like a keyed server: nothing it answers can change anything
    public = bool(settings.codesage_api_key) or settings.read_only
    allowed = settings.allowed_hosts_list if public else LOOPBACK_HOSTS
    checked = bool(host) or not public
    if checked and not host_is_allowed(host_without_port(host), allowed) and scope.get("path") != "/health":
        return "Host not allowed"
    if not public:
        # Bound to 0.0.0.0 by hand (MCP_SERVER_HOST unset), a LAN client could send Host: localhost,
        # but not a loopback address
        if not _is_loopback_peer(scope.get("client")):
            return "Only local clients are served without an API key"
    if scope["type"] == "http" and scope["method"] not in UNSAFE_METHODS:
        return None
    # Browsers always send Origin on cross-site writes and WebSocket handshakes; other clients may not
    origin = headers.get("origin")
    # The scheme counts too (http://host is another origin than https://host). It comes from the
    # connection, which uvicorn rewrites only for proxies it trusts (prod: nginx, which sets it)
    scheme = {"ws": "http", "wss": "https"}.get(scope.get("scheme", "http"), scope.get("scheme", "http"))
    if origin is None or origin in settings.cors_origins_list or (host and origin == f"{scheme}://{host}"):
        return None
    return "Cross-origin request refused"


class BrowserRequestGuard:
    """ASGI middleware applying request_refusal to HTTP requests and WebSocket handshakes"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and (problem := request_refusal(scope)):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse({"detail": problem}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
