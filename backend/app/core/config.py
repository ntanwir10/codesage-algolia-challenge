"""
CodeSage configuration.

Settings are read from environment variables (and a .env file) into a single
cached Settings object: database, Algolia, GitHub, API key, CORS, rate limits
and the MCP server description.
"""

import re
from functools import lru_cache
from urllib.parse import urlsplit

# Load environment variables from .env file
import structlog
from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

logger = structlog.get_logger()

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def host_without_port(host: str) -> str:
    """A Host header (or ALLOWED_HOSTS entry) without its port. Parsed by hand: urlsplit would
    also accept userinfo or a fragment, so 'evil.com@localhost' would read as localhost"""
    host = host.strip().lower()
    if host.startswith("["):  # [IPv6]:port
        return host[1 : host.find("]")] if "]" in host else ""
    return host.rpartition(":")[0] if host.count(":") == 1 else host


def host_is_allowed(hostname: str, allowed: tuple[str, ...]) -> bool:
    """Exact match, '*.example.com' for any subdomain of example.com, or '*' for any host"""
    if "*" in allowed or hostname in allowed:
        return True
    return any(entry.startswith("*.") and hostname.endswith(entry[1:]) for entry in allowed)


@lru_cache(maxsize=8)
def _allowed_hosts(cors_origins: str, allowed_hosts: str) -> tuple[str, ...]:
    # Keyed on the raw settings, so it is parsed once per value, not on every request
    origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    hosts = [*LOOPBACK_HOSTS]
    hosts += [urlsplit(origin).hostname or "" for origin in origins]
    hosts += [host_without_port(h) for h in allowed_hosts.split(",") if h.strip()]
    return tuple(h for h in dict.fromkeys(hosts) if h)


class Settings(BaseSettings):
    # Core FastAPI Settings
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

    @field_validator("algolia_app_id", "algolia_admin_api_key", "github_token", mode="before")
    @classmethod
    def _placeholder_is_unset(cls, value):
        """An .env copied from the old example still holds 'your-...-here'; that means not configured"""
        if isinstance(value, str) and re.fullmatch(r"your-.*-here", value.strip()):
            return None
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        """Convert CORS origins string to list"""
        if not self.cors_origins:
            return []
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    allowed_hosts: str = Field(
        default="",
        description=(
            "Comma-separated extra hostnames the API answers to, on top of loopback and "
            "the CORS_ORIGINS hosts; '*.example.com' allows its subdomains, and '*' allows "
            "any host (and so allows DNS rebinding)"
        ),
    )

    @property
    def allowed_hosts_list(self) -> tuple[str, ...]:
        """Hostnames (no port) a request's Host may name when a key is configured"""
        return _allowed_hosts(self.cors_origins, self.allowed_hosts)

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


def validate_runtime_settings(settings: Settings) -> None:
    """Refuse to start with an unsafe configuration; warn about a soft one."""
    if "*" in settings.cors_origins_list:
        raise RuntimeError(
            "CORS_ORIGINS must not contain '*' because credentials are allowed; "
            "list the allowed origins explicitly"
        )
    if settings.codesage_api_key and "*" in settings.allowed_hosts_list:
        logger.warning("ALLOWED_HOSTS contains '*'; any Host is served, so DNS rebinding is not blocked")
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
