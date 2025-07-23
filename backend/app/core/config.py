import os
from typing import Optional, List, Union
from pydantic import field_validator, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core FastAPI Settings
    app_name: str = "CodeSage MCP Server"
    debug: bool = False
    environment: str = "development"
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for JWT encoding",
    )

    # Database Settings
    database_url: str = Field(
        default="postgresql://codesage:codesage123@localhost:5432/codesage",
        description="PostgreSQL database URL",
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Simplified architecture - no Redis/Celery needed for MCP server
    # MCP servers should be fast and lightweight

    # MCP SERVER SETTINGS (Core Architecture)
    mcp_server_name: str = Field(
        default="codesage", description="MCP server identifier"
    )
    mcp_server_version: str = Field(default="1.0.0", description="MCP server version")
    mcp_server_description: str = Field(
        default="AI-powered code discovery through natural language",
        description="MCP server description",
    )
    mcp_server_host: str = Field(default="0.0.0.0", description="MCP server host")
    mcp_server_port: int = Field(default=8000, description="MCP server port")

    # Algolia Settings (Primary Search Engine)
    algolia_app_id: Optional[str] = Field(
        default=None, description="Algolia application ID"
    )
    algolia_admin_api_key: Optional[str] = Field(
        default=None, description="Algolia admin API key (required for indexing)"
    )
    algolia_search_api_key: Optional[str] = Field(
        default=None, description="Algolia search-only API key"
    )
    algolia_index_name: str = Field(
        default="codesage_code_entities",
        description="Algolia index name for code entities",
    )

    # API Settings
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    max_upload_size: int = 100 * 1024 * 1024  # 100MB
    api_rate_limit: str = "100/minute"

    # Rate Limiting Settings
    enable_rate_limiting: bool = True
    rate_limit_default: str = "100/minute"  # Default rate limit for most endpoints
    rate_limit_search: str = (
        "50/minute"  # Lower limit for search endpoints (more expensive)
    )
    rate_limit_upload: str = "10/minute"  # Very low limit for upload endpoints
    rate_limit_ai: str = "30/minute"  # Moderate limit for AI/MCP endpoints
    rate_limit_storage_uri: Optional[str] = (
        None  # Redis URI for distributed rate limiting (None = in-memory)
    )

    # Security Settings
    allowed_hosts: List[str] = ["localhost", "127.0.0.1"]
    enable_metrics: bool = True

    # Logging Settings
    log_level: str = "INFO"
    log_format: str = "json"

    # Feature Flags (MCP-Focused)
    enable_mcp_tools: bool = True
    enable_mcp_resources: bool = True
    enable_code_analysis: bool = True
    enable_real_time_indexing: bool = True
    enable_collaboration: bool = True

    # File Processing Settings
    supported_languages: List[str] = [
        "python",
        "javascript",
        "typescript",
        "java",
        "go",
        "rust",
        "cpp",
        "c",
        "csharp",
        "php",
        "ruby",
    ]
    max_file_size: int = 10 * 1024 * 1024  # 10MB per file
    max_files_per_repository: int = 10000

    # Simplified processing - direct responses for MCP tools
    mcp_response_timeout_seconds: int = 30  # Fast responses for AI models

    # MCP Tool Configuration
    mcp_tools_enabled: List[str] = [
        "search_code",
        "analyze_repository",
        "explore_functions",
        "explain_code",
        "find_patterns",
    ]

    mcp_resources_enabled: List[str] = [
        "repositories",
        "files",
        "entities",
        "search_indexes",
    ]

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format"""
        if not v.startswith(("postgresql://", "postgresql+psycopg2://", "sqlite:///")):
            raise ValueError("Database URL must be a valid PostgreSQL or SQLite URL")
        return v

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: List[str]) -> List[str]:
        """Validate CORS origins format"""
        for origin in v:
            if not (
                origin.startswith("http://")
                or origin.startswith("https://")
                or origin == "*"
            ):
                raise ValueError("Invalid CORS origin format")
        return v

    @field_validator("algolia_app_id")
    @classmethod
    def validate_algolia_app_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate Algolia app ID is provided for MCP server"""
        if v is None or v == "your_algolia_app_id_here":
            # Allow None or placeholder values in development
            return v
        return v

    @field_validator("algolia_admin_api_key")
    @classmethod
    def validate_algolia_admin_api_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate Algolia admin API key is provided for MCP server"""
        if v is None or v == "your_algolia_admin_api_key_here":
            # Allow None or placeholder values in development
            return v
        return v

    @property
    def ALGOLIA_APP_ID(self) -> Optional[str]:
        """Get Algolia app ID with proper casing for compatibility"""
        return self.algolia_app_id

    @property
    def ALGOLIA_API_KEY(self) -> Optional[str]:
        """Get Algolia admin API key with proper casing for compatibility"""
        return self.algolia_admin_api_key

    @property
    def ALGOLIA_SEARCH_API_KEY(self) -> Optional[str]:
        """Get Algolia search API key with proper casing for compatibility"""
        return self.algolia_search_api_key

    @property
    def ALGOLIA_INDEX_NAME(self) -> str:
        """Get Algolia index name with proper casing for compatibility"""
        return self.algolia_index_name

    @property
    def MCP_SERVER_CONFIG(self) -> dict:
        """Get MCP server configuration for protocol implementation"""
        return {
            "name": self.mcp_server_name,
            "version": self.mcp_server_version,
            "description": self.mcp_server_description,
            "host": self.mcp_server_host,
            "port": self.mcp_server_port,
            "capabilities": {
                "tools": self.enable_mcp_tools,
                "resources": self.enable_mcp_resources,
                "prompts": False,
            },
            "tools_enabled": self.mcp_tools_enabled,
            "resources_enabled": self.mcp_resources_enabled,
        }

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get application settings (singleton pattern)"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
