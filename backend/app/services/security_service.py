from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
import structlog
import functools

from app.schemas.ai import SecurityAnalysisResponse
from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class SecurityService:
    """Service for security analysis and vulnerability detection"""

    def __init__(self, db: Session):
        self.db = db

    async def scan_repository(
        self, repository_id: int, file_path: str = None
    ) -> SecurityAnalysisResponse:
        """Scan repository for security vulnerabilities (stub implementation)"""
        # TODO: Implement AI-powered security analysis
        return SecurityAnalysisResponse(
            repository_id=repository_id,
            file_path=file_path,
            security_score=85,
            risk_level="medium",
            issues=[],
            recommendations=[],
            scan_timestamp="2024-01-01T00:00:00Z",
        )


class RateLimitingService:
    """Rate limiting service using slowapi"""

    def __init__(self):
        self.settings = get_settings()

        # Initialize limiter based on configuration
        if self.settings.rate_limit_storage_uri:
            # Use Redis for distributed rate limiting
            self.limiter = Limiter(
                key_func=self._get_rate_limit_key,
                storage_uri=self.settings.rate_limit_storage_uri,
                enabled=self.settings.enable_rate_limiting,
            )
        else:
            # Use in-memory storage for single instance
            self.limiter = Limiter(
                key_func=self._get_rate_limit_key,
                enabled=self.settings.enable_rate_limiting,
            )

        logger.info(
            "Rate limiting service initialized",
            enabled=self.settings.enable_rate_limiting,
            storage="redis" if self.settings.rate_limit_storage_uri else "memory",
            default_limit=self.settings.rate_limit_default,
        )

    def _get_rate_limit_key(self, request: Request) -> str:
        """Get the key for rate limiting - can be IP, user ID, API key, etc."""
        # For now, use IP address
        # In future, could use authenticated user ID for more sophisticated limiting
        ip = get_remote_address(request)

        # You could extend this to include user authentication
        # user_id = getattr(request.state, 'user_id', None)
        # if user_id:
        #     return f"user:{user_id}"

        return f"ip:{ip}"

    def get_rate_limit_decorator(self, limit_type: str = "default"):
        """Get rate limit decorator for different endpoint types"""

        # Map limit types to actual limits
        limit_mapping = {
            "default": self.settings.rate_limit_default,
            "search": self.settings.rate_limit_search,
            "upload": self.settings.rate_limit_upload,
            "ai": self.settings.rate_limit_ai,
        }

        limit = limit_mapping.get(limit_type, self.settings.rate_limit_default)

        def decorator(func):
            # For FastAPI endpoints, we need to properly handle the request parameter
            import inspect

            sig = inspect.signature(func)

            # Check if the function already has a request parameter
            has_request = any(
                param.name in ["request", "websocket"]
                for param in sig.parameters.values()
            )

            if has_request:
                # Function already has request parameter, apply limiter directly
                return self.limiter.limit(limit)(func)
            else:
                # Add request dependency for rate limiting
                from functools import wraps

                @wraps(func)
                async def wrapper(
                    *args, request: Request = Depends(lambda: None), **kwargs
                ):
                    # Apply rate limiting by calling the limiter manually
                    await self.limiter.check_request_limit(request, limit)
                    return await func(*args, **kwargs)

                return wrapper

        return decorator

    def create_rate_limit_handler(self):
        """Create custom rate limit exceeded handler"""

        async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
            """Custom handler for rate limit exceeded"""
            logger.warning(
                "Rate limit exceeded",
                ip=get_remote_address(request),
                path=request.url.path,
                method=request.method,
                retry_after=exc.retry_after,
            )

            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Try again in {exc.retry_after} seconds.",
                    "retry_after": exc.retry_after,
                    "limit": str(exc.detail).split(":")[0] if exc.detail else "Unknown",
                },
                headers={"Retry-After": str(exc.retry_after)},
            )

        return rate_limit_handler


# Global rate limiting service instance
_rate_limiting_service: Optional[RateLimitingService] = None


def get_rate_limiting_service() -> RateLimitingService:
    """Get the global rate limiting service instance"""
    global _rate_limiting_service
    if _rate_limiting_service is None:
        _rate_limiting_service = RateLimitingService()
    return _rate_limiting_service


# Convenience decorators for different endpoint types (temporarily disabled)
def rate_limit_default(func):
    """Apply default rate limiting to endpoint (temporarily disabled)"""
    # TODO: Fix rate limiting implementation
    return func


def rate_limit_search(func):
    """Apply search-specific rate limiting to endpoint (temporarily disabled)"""
    # TODO: Fix rate limiting implementation
    return func


def rate_limit_upload(func):
    """Apply upload-specific rate limiting to endpoint (temporarily disabled)"""
    # TODO: Fix rate limiting implementation
    return func


def rate_limit_ai(func):
    """Apply AI/MCP-specific rate limiting to endpoint (temporarily disabled)"""
    # TODO: Fix rate limiting implementation
    return func
