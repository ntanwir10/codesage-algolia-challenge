"""
CodeSage - MCP-First Code Discovery: Configuration

This module provides configuration management for CodeSage - the only code discovery
tool built entirely around the Model Context Protocol (MCP) for seamless AI integration.

The configuration includes MCP server settings, Algolia search integration,
and all necessary parameters for MCP-first code discovery architecture.
"""

# Load environment variables from .env file
import structlog
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

logger = structlog.get_logger()


class Settings(BaseSettings):
    # Core FastAPI Settings
    app_name: str = "CodeSage - MCP-First Code Discovery"
    debug: bool = False
    environment: str = "development"

    # Database Settings
    database_url: str = Field(
        default="sqlite:///./codesage.db",
        description="Database URL (SQLite by default)",
    )
    sql_echo: bool = Field(default=False, description="Log every SQL statement")

    # MCP Server Settings
    mcp_server_name: str = Field(
        default="codesage", description="MCP server identifier"
    )
    mcp_server_version: str = Field(default="1.0.0", description="MCP server version")
    mcp_server_description: str = Field(
        default="AI-powered code discovery through natural language - MCP-First Architecture",
        description="MCP server description",
    )
    mcp_server_host: str = Field(default="127.0.0.1", description="MCP server host")
    mcp_server_port: int = Field(default=8001, description="MCP server port")

    # Algolia Settings (Primary Search Engine)
    algolia_app_id: str | None = Field(
        default=None, description="Algolia application ID"
    )
    algolia_admin_api_key: str | None = Field(
        default=None, description="Algolia admin API key (required for indexing)"
    )
    algolia_index_name: str = Field(
        default="codesage_code_entities",
        description="Algolia index name for code entities",
    )

    # GitHub Settings
    github_token: str | None = Field(
        default=None, description="GitHub personal access token for API access"
    )

    # Security
    codesage_api_key: str | None = Field(
        default=None,
        description="API key required on write endpoints (X-API-Key header)",
    )

    # API Settings
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://localhost:5174",
        description="Comma-separated list of CORS origins",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Convert CORS origins string to list"""
        if not self.cors_origins:
            return []
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    # Rate Limiting (Essential only)
    enable_rate_limiting: bool = True
    rate_limit_default: str = "100/minute"
    rate_limit_ai: str = "30/minute"  # For MCP tool endpoints

    # Logging Settings
    log_level: str = "INFO"

    @property
    def MCP_SERVER_CONFIG(self) -> dict:
        """MCP server configuration for protocol compliance"""
        return {
            "name": self.mcp_server_name,
            "version": self.mcp_server_version,
            "description": self.mcp_server_description,
            "capabilities": {
                "tools": True,
                "resources": True,
                "prompts": False,
            },
        }

    # Load from the backend directory's .env (load_dotenv() above also searches upward)
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def validate_runtime_settings(settings: Settings) -> None:
    """Refuse to start with an unsafe configuration; warn about a soft one."""
    if "*" in settings.cors_origins_list:
        raise RuntimeError(
            "CORS_ORIGINS must not contain '*' because credentials are allowed; "
            "list the allowed origins explicitly"
        )
    loopback = settings.mcp_server_host in LOOPBACK_HOSTS
    if not settings.codesage_api_key:
        if not loopback:
            raise RuntimeError(
                "CODESAGE_API_KEY is required when MCP_SERVER_HOST is not a "
                f"loopback address (host is {settings.mcp_server_host!r})"
            )
        logger.warning(
            "CODESAGE_API_KEY is not set; write endpoints are unauthenticated "
            "(acceptable on loopback only)"
        )


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get application settings (singleton pattern)"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
