"""API-key authentication, browser request checks and rate limiting."""

import secrets

from fastapi import Header, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.core.config import LOOPBACK_HOSTS, get_settings

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


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _hostname(host: str) -> str:
    """The Host header without its port. Parsed by hand: urlsplit would also accept
    userinfo or a fragment, so 'evil.com@localhost' would read as localhost"""
    host = host.lower()
    if host.startswith("["):  # [IPv6]:port
        return host[1 : host.find("]")] if "]" in host else ""
    return host.rpartition(":")[0] if host.count(":") == 1 else host


def request_refusal(scope) -> str | None:
    """Why a request a browser may have been tricked into sending must be refused.

    The key alone can't tell: prod nginx adds it to every request carrying the
    browser's cached login, and with no key configured there is nothing to check.
    """
    settings = get_settings()
    headers = Headers(scope=scope)
    host = headers.get("host", "")
    # DNS rebinding: a hostile page re-pointed at 127.0.0.1 is same-origin but keeps its own Host
    if not settings.codesage_api_key and _hostname(host) not in LOOPBACK_HOSTS:
        return "Host not allowed"
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
