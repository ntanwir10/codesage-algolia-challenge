"""Tool names, descriptions and argument models for the CodeSage MCP tools.

This module is imported by both the backend and the standalone MCP server, so
it must stay free of app, database, Algolia and settings imports.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["function", "class", "import", "doc_section"]

REPOSITORY_DESCRIPTION = (
    "Repository ID or name. Accepts the numeric ID, the name, or 'owner/name'. "
    "Use list_repositories to see what is available."
)


class _Args(BaseModel):
    # Unknown arguments are rejected so a typo can't silently widen a query
    model_config = ConfigDict(extra="forbid")


class ListRepositoriesArgs(_Args):
    pass


class SearchCodeArgs(_Args):
    query: str = Field(description="Search text matched against names, descriptions and code", min_length=1)
    repository: str | None = Field(
        default=None,
        description=REPOSITORY_DESCRIPTION + " Omit to search all indexed repositories.",
    )
    language: str | None = Field(default=None, description="Restrict to one language, e.g. 'python'")
    entity_type: EntityType | None = Field(default=None, description="Restrict to one kind of entity")
    limit: int = Field(default=10, ge=1, le=50, description="Results per page")
    page: int = Field(default=0, ge=0, description="Zero-based result page")


class GetFileArgs(_Args):
    repository: str = Field(description=REPOSITORY_DESCRIPTION)
    path: str = Field(description="Exact file path within the repository")
    start_line: int | None = Field(default=None, ge=1, description="First line to return (1-based)")
    end_line: int | None = Field(
        default=None, ge=1, description="Last line to return. At most 400 lines are returned per call"
    )


class ListDefinitionsArgs(_Args):
    repository: str = Field(description=REPOSITORY_DESCRIPTION)
    path_prefix: str | None = Field(default=None, description="Only files whose path starts with this")
    entity_type: EntityType | None = Field(default=None, description="Restrict to one kind of entity")
    name: str | None = Field(default=None, description="Substring of the entity name")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum definitions to return")


class AnalyzeRepositoryArgs(_Args):
    repository: str = Field(description=REPOSITORY_DESCRIPTION)


class FindPatternsArgs(_Args):
    repository: str = Field(description=REPOSITORY_DESCRIPTION)
    pattern: str = Field(min_length=1, max_length=200, description="Text or regular expression to find")
    regex: bool = Field(default=False, description="Treat pattern as a regular expression")
    path_glob: str | None = Field(default=None, description="Only search files matching this glob, e.g. 'src/*.py'")
    max_results: int = Field(default=100, ge=1, le=500, description="Maximum matches to return")


class ToolSpec(BaseModel):
    name: str
    description: str
    args_model: type[BaseModel]


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec(
            name="list_repositories",
            description="List the repositories indexed by CodeSage with their status and size.",
            args_model=ListRepositoriesArgs,
        ),
        ToolSpec(
            name="search_code",
            description=(
                "Full-text search over indexed functions, classes, imports and doc sections. "
                "Returns ranked hits with file locations, snippets and GitHub links."
            ),
            args_model=SearchCodeArgs,
        ),
        ToolSpec(
            name="get_file",
            description="Read a file from a repository with line numbers. Returns at most 400 lines per call.",
            args_model=GetFileArgs,
        ),
        ToolSpec(
            name="list_definitions",
            description="List functions, classes, imports and doc sections defined in a repository, ordered by file and line.",
            args_model=ListDefinitionsArgs,
        ),
        ToolSpec(
            name="analyze_repository",
            description=(
                "Return measured facts about a repository: file, line and entity counts, "
                "languages, top directories and the largest files."
            ),
            args_model=AnalyzeRepositoryArgs,
        ),
        ToolSpec(
            name="find_patterns",
            description="Find lines in a repository's files that match a literal string or a regular expression.",
            args_model=FindPatternsArgs,
        ),
    ]
}


def input_schema(name: str) -> dict:
    """JSON Schema for a tool's arguments"""
    return TOOLS[name].args_model.model_json_schema()
