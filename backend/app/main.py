import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog

# Load environment variables from .env file
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

load_dotenv()

from app.api.v1.router import api_router
from app.core.config import get_settings, validate_runtime_settings
from app.core.database import SessionLocal, engine
from app.core.migrations import upgrade_database
from app.core.security import limiter
from app.models import code_entity, code_file, repository  # noqa: F401  registers tables
from app.services.algolia_service import AlgoliaService
from app.services.repository_service import recover_interrupted_jobs

# Get application settings
settings = get_settings()

# Configure structured logging once
logging.basicConfig(level=settings.log_level.upper(), format="%(message)s")
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the MCP server on startup and log shutdown"""
    validate_runtime_settings(settings)
    logger.info(
        "Starting CodeSage MCP Server",
        mcp_config=settings.MCP_SERVER_CONFIG,
        algolia_configured=bool(
            settings.algolia_app_id and settings.algolia_admin_api_key
        ),
    )

    # Bring the schema to the latest migration; a pre-Alembic database is stamped first
    upgrade_database(engine)
    logger.info("Database schema up to date")

    # Jobs run in-process, so any run a previous process left open died with it
    with SessionLocal() as db:
        recover_interrupted_jobs(db)

    # Validate MCP server requirements
    if not settings.algolia_app_id or not settings.algolia_admin_api_key:
        logger.error(
            "Algolia credentials not configured - MCP server cannot function properly"
        )
    else:
        logger.info("Algolia credentials configured - MCP server ready")

    # Log WebSocket configuration
    logger.info("WebSocket endpoint configured at /ws for real-time updates")

    yield

    logger.info("Shutting down CodeSage MCP Server")


# Create FastAPI application - CodeSage - MCP-First Code Discovery Server
app = FastAPI(
    title="CodeSage - MCP-First Code Discovery",
    description="AI-Powered Code Discovery Platform built entirely around the Model Context Protocol (MCP) for seamless integration with Claude Desktop and other AI clients. The only code discovery tool with MCP-first architecture.",
    version="1.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    lifespan=lifespan,
    servers=[
        {
            "url": f"http://{settings.mcp_server_host}:{settings.mcp_server_port}",
            "description": "CodeSage - MCP-First Code Discovery Server",
        }
    ],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

logger.info(
    "CodeSage MCP Server configured",
    environment=settings.environment,
    rate_limiting=settings.enable_rate_limiting,
)



@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Reuse an incoming X-Request-ID or generate one, and echo it back"""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the real error with the request ID; never leak it to the client"""
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unhandled exception",
        request_id=request_id,
        path=request.url.path,
        exc_info=exc,
    )
    headers = {"X-Request-ID": request_id} if request_id else {}
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers=headers,
    )


# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Add WebSocket endpoints directly to main app
from app.services.websocket_service import repository_status_websocket, websocket_health

app.add_api_websocket_route("/ws", repository_status_websocket)
app.add_api_route("/api/v1/ws/health", websocket_health, methods=["GET"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with MCP server information"""
    return {
        "message": "CodeSage MCP Server",
        "version": "1.0.0",
        "architecture": "MCP-first - Simplified",
        "description": "AI-powered code discovery through the Model Context Protocol",
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "websocket": "/ws",
            "mcp_tools": "/api/v1/ai/mcp/tools",
            "mcp_capabilities": "/api/v1/ai/mcp/capabilities",
        },
        "realtime_features": {
            "websocket_url": "/ws",
            "health_check": "/api/v1/ws/health",
            "supported_events": [
                "repository_status",
                "processing_complete",
                "processing_failed",
            ],
        },
    }


_ALGOLIA_CHECK_TTL = 30.0
_algolia_check: tuple[float, dict] | None = None


async def _check_algolia() -> dict:
    """Probe Algolia, caching the result for 30 seconds"""
    global _algolia_check
    now = time.monotonic()
    if _algolia_check and now - _algolia_check[0] < _ALGOLIA_CHECK_TTL:
        return _algolia_check[1]

    client = AlgoliaService().client
    if client is None:
        result = {"status": "not_configured"}
    else:
        try:
            await asyncio.wait_for(asyncio.to_thread(client.list_indices), 5)
            result = {"status": "healthy"}
        except Exception as e:
            logger.warning("Algolia health check failed", error=str(e))
            result = {"status": "degraded", "message": "Algolia is unreachable"}
    _algolia_check = (now, result)
    return result


@app.get("/health")
async def health_check():
    """Health check: the database decides 200 vs 503, Algolia only degrades"""
    components: dict[str, dict] = {}

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        components["database"] = {"status": "healthy"}
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        components["database"] = {"status": "unhealthy"}

    components["algolia"] = await _check_algolia()

    if components["database"]["status"] != "healthy":
        overall = "unhealthy"
    elif components["algolia"]["status"] == "degraded":
        overall = "degraded"
    else:
        overall = "healthy"

    body = {
        "status": overall,
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "1.0.0",
        "components": components,
    }
    return JSONResponse(body, status_code=503 if overall == "unhealthy" else 200)


@app.get("/mcp")
async def mcp_info():
    """MCP server information endpoint"""
    return {
        "server": "CodeSage MCP Server",
        "protocol": "Model Context Protocol (MCP)",
        "version": settings.MCP_SERVER_CONFIG["version"],
        "description": settings.MCP_SERVER_CONFIG["description"],
        "capabilities": settings.MCP_SERVER_CONFIG["capabilities"],
        "tools_available": len(settings.mcp_tools_enabled),
        "realtime_features": {
            "websocket_endpoint": "/ws",
            "real_time_processing": True,
            "status_broadcasting": True,
            "supported_events": [
                "repository_status",
                "processing_complete",
                "processing_failed",
            ],
        },
        "setup_instructions": "See docs/MCP_INTEGRATION_GUIDE.md",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        reload=settings.environment == "development",
    )
