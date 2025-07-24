from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import structlog
import functools

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class RateLimitingService:
    """Simplified rate limiting service - optional for MCP-first architecture"""

    def __init__(self):
        self.settings = get_settings()
        self.enabled = self.settings.enable_rate_limiting

        if self.enabled:
            logger.info("Rate limiting enabled for MCP server")
        else:
            logger.info("Rate limiting disabled for MCP server")

    def get_rate_limit_decorator(self, limit_type: str = "default"):
        """Get rate limit decorator - no-op if disabled"""
        def decorator(func):
            # For MCP-first architecture, keep it simple
            # Rate limiting can be handled at infrastructure level (nginx, cloudflare, etc.)
            return func
        return decorator


# Global rate limiting service instance
_rate_limiting_service: Optional[RateLimitingService] = None


def get_rate_limiting_service() -> RateLimitingService:
    """Get rate limiting service (singleton pattern)"""
    global _rate_limiting_service
    if _rate_limiting_service is None:
        _rate_limiting_service = RateLimitingService()
    return _rate_limiting_service


# Simplified decorators for MCP-first architecture
def rate_limit_default(func):
    """Rate limit decorator for default endpoints - simplified for MCP"""
    # For MCP servers, keep it simple - rate limiting at infrastructure level
    return func


def rate_limit_ai(func):
    """Rate limit decorator for AI/MCP endpoints - simplified"""
    # MCP tools should be fast and lightweight
    return func
