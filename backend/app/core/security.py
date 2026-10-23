"""API-key authentication and rate limiting."""

import secrets

from fastapi import Header, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

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
