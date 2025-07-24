import os
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core FastAPI Settings
    app_name: str = "CodeSage MCP Server"
    debug: bool = False
    environment: str = "development"
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for authentication",
    )

    # Database Settings
    database_url: str = Field(
        default="postgresql://codesage:codesage123@localhost:5432/codesage",
        description="PostgreSQL database URL",
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # MCP Server Settings
    mcp_server_name: str = Field(
        default="codesage", description="MCP server identifier"
    )
    mcp_server_version: str = Field(default="1.0.0", description="MCP server version")
    mcp_server_description: str = Field(
        default="AI-powered code discovery through natural language",
        description="MCP server description",
    )
    mcp_server_host: str = Field(default="0.0.0.0", description="MCP server host")
    mcp_server_port: int = Field(default=8001, description="MCP server port")

    # Algolia Settings (Primary Search Engine)
    algolia_app_id: Optional[str] = Field(
        default=None, description="Algolia application ID"
    )
    algolia_admin_api_key: Optional[str] = Field(
        default=None, description="Algolia admin API key (required for indexing)"
    )
    algolia_index_name: str = Field(
        default="codesage_code_entities",
        description="Algolia index name for code entities",
    )

    # API Settings
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    allowed_hosts: List[str] = ["localhost", "127.0.0.1"]

    # Rate Limiting (Essential only)
    enable_rate_limiting: bool = True
    rate_limit_default: str = "100/minute"
    rate_limit_ai: str = "30/minute"  # For MCP tool endpoints

    # Logging Settings
    log_level: str = "INFO"
    log_format: str = "json"

    # MCP Tools Configuration
    mcp_tools_enabled: List[str] = [
        "search_code",
        "analyze_repository",
        "explore_functions",
        "explain_code",
        "find_patterns",
    ]

    # Supported Programming Languages
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

    # MCP Response timeout for fast AI interactions
    mcp_response_timeout_seconds: int = 30

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
            "tools_enabled": self.mcp_tools_enabled,
        }

    class Config:
        env_file = "../.env"  # Load from project root
        case_sensitive = False
        extra = "ignore"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get application settings (singleton pattern)"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
