"""Tool names, descriptions and argument models for the CodeSage MCP tools.

This module is imported by both the backend and the standalone MCP server, so
it must stay free of app, database, Algolia and settings imports.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["function", "class", "import", "doc_section", "terraform_block"]

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


class AddRepositoryArgs(_Args):
    url: str = Field(
        description=(
            "https URL of the git repository to index. Accepts GitHub, GitLab, Bitbucket and "
            "self-hosted git servers, e.g. 'https://gitlab.com/group/project'. Branch URLs "
            "such as '.../tree/dev' are understood. Private repositories work only on GitHub, "
            "and only when the CodeSage server's token has access; elsewhere the repository "
            "must be public."
        ),
        min_length=1,
    )
    branch: str | None = Field(default=None, description="Branch to index. Omit for the default branch.")
    description: str | None = Field(default=None, description="Optional note describing the repository")


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
                "Full-text search over indexed functions, classes, imports, doc sections and "
                "Terraform blocks. Returns ranked hits with file locations, snippets and links to "
                "the source on GitHub, GitLab or Bitbucket."
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
            description=(
                "List functions, classes, imports, doc sections and Terraform blocks defined in a "
                "repository, ordered by file and line."
            ),
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
        ToolSpec(
            name="add_repository",
            description=(
                "Add a git repository to CodeSage and start indexing it. Works with GitHub, "
                "GitLab, Bitbucket and self-hosted https URLs. Indexing runs in the background; "
                "use list_repositories to follow progress, and search it once it is completed."
            ),
            args_model=AddRepositoryArgs,
        ),
    ]
}


def input_schema(name: str) -> dict:
    """JSON Schema for a tool's arguments"""
    return TOOLS[name].args_model.model_json_schema()
