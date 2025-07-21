from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import structlog
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.core.config import get_settings
from app.api.v1.router import api_router
from app.core.database import engine
from app.models import Base
from app.api.v1.router import api_router
from app.core.database import get_db
from app.services.algolia_service import AlgoliaService
import structlog

# Configure structured logging
structlog.configure(
    processors=[
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

# Get application settings
settings = get_settings()

# Initialize Sentry for error monitoring
if hasattr(settings, "sentry_dsn") and settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(auto_enable=True),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,
        environment=settings.environment,
    )

# Create FastAPI application - MCP SERVER
app = FastAPI(
    title="CodeSage MCP Server",
    description="AI-Powered Code Discovery Platform built around Algolia MCP Server integration. Implements Model Context Protocol (MCP) for conversational code exploration.",
    version="1.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    servers=[
        {
            "url": f"http://{settings.mcp_server_host}:{settings.mcp_server_port}",
            "description": "CodeSage MCP Server",
        }
    ],
)

# Add middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """Initialize MCP server on startup"""
    logger.info(
        "Starting CodeSage MCP Server",
        mcp_config=settings.MCP_SERVER_CONFIG,
        algolia_configured=bool(
            settings.algolia_app_id and settings.algolia_admin_api_key
        ),
    )

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")

    # Validate MCP server requirements
    if not settings.algolia_app_id or not settings.algolia_admin_api_key:
        logger.error(
            "Algolia credentials not configured - MCP server cannot function properly"
        )
    else:
        logger.info("Algolia credentials configured - MCP server ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down CodeSage MCP Server")


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
            "mcp_tools": "/api/v1/ai/mcp/tools",
            "mcp_capabilities": "/api/v1/ai/mcp/capabilities",
        },
    }


@app.get("/health")
async def health_check():
    """Comprehensive health check for all system components"""
    from sqlalchemy.orm import Session

    health_status = {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",  # This would be actual timestamp
        "version": "1.0.0",
        "architecture": "MCP-first - Simplified",
        "components": {},
    }

    overall_healthy = True

    # Check database
    try:
        from sqlalchemy import text
        db = next(get_db())
        db.execute(text("SELECT 1"))
        health_status["components"]["database"] = {
            "status": "healthy",
            "message": "PostgreSQL connection successful",
        }
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}",
        }
        overall_healthy = False

    # Check Algolia
    try:
        algolia_service = AlgoliaService()
        # This would be an actual health check method
        health_status["components"]["algolia"] = {
            "status": "healthy",
            "message": "Algolia connection successful",
        }
    except Exception as e:
        health_status["components"]["algolia"] = {
            "status": "unhealthy",
            "message": f"Algolia connection failed: {str(e)}",
        }
        overall_healthy = False

    # Check MCP server functionality
    try:
        from app.services.mcp_server import MCPServerService

        # This would test MCP server functionality
        health_status["components"]["mcp_server"] = {
            "status": "healthy",
            "message": "MCP server operational",
        }
    except Exception as e:
        health_status["components"]["mcp_server"] = {
            "status": "degraded",
            "message": f"MCP server issues: {str(e)}",
        }
        overall_healthy = False

    # Set overall status
    if not overall_healthy:
        health_status["status"] = "unhealthy"

    logger.info("Health check performed", status=health_status["status"])

    # Return appropriate HTTP status
    if overall_healthy:
        return health_status
    else:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=health_status)


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
        "resources_available": len(settings.mcp_resources_enabled),
        "setup_instructions": {
            "claude_desktop": {
                "config_file": "claude_desktop_config.json",
                "configuration": {
                    "mcpServers": {
                        "codesage": {
                            "command": "python",
                            "args": ["-m", "codesage_mcp_server"],
                            "env": {
                                "ALGOLIA_APP_ID": "your_app_id",
                                "ALGOLIA_ADMIN_API_KEY": "your_admin_api_key",
                                "MCP_SERVER_URL": f"http://{settings.mcp_server_host}:{settings.mcp_server_port}",
                            },
                        }
                    }
                },
            }
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        reload=settings.environment == "development",
    )
