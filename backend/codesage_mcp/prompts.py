"""MCP prompts: ready-made questions that steer Claude through the CodeSage tools.

They are plain text built here, so prompts/list and prompts/get work even when the backend is down.
"""

from dataclasses import dataclass

import mcp_types as types
from mcp.shared.exceptions import MCPError


@dataclass(frozen=True)
class PromptSpec:
    prompt: types.Prompt
    template: str


REPOSITORY = types.PromptArgument(
    name="repository",
    description="Repository ID or name, as list_repositories shows it",
    required=True,
)

PROMPTS: dict[str, PromptSpec] = {
    spec.prompt.name: spec
    for spec in [
        PromptSpec(
            types.Prompt(
                name="explain_repository",
                title="Explain this repository",
                description="Walk through what a repository does, how it is laid out and where to start reading.",
                arguments=[REPOSITORY],
            ),
            "Explain the repository '{repository}', indexed in CodeSage, to someone new to it.\n\n"
            "1. Call analyze_repository with repository '{repository}' for its languages, top "
            "directories and largest files.\n"
            "2. Call list_definitions for it to find the main modules, classes and entry points. "
            "Use path_prefix to focus on the main directories, and entity_type 'doc_section' for "
            "its documentation.\n"
            "3. Read the README and one or two central files with get_file.\n\n"
            "Then say what the repository does, how it is laid out, what its main parts are and how "
            "they fit together, and where to start reading. Cite file paths with line numbers, and "
            "say what you could not confirm from the code.",
        ),
        PromptSpec(
            types.Prompt(
                name="find_implementation",
                title="Where is this implemented?",
                description="Find the code that implements a feature, with file paths and line numbers.",
                arguments=[
                    types.PromptArgument(
                        name="feature",
                        description="What to find, e.g. 'retrying failed requests'",
                        required=True,
                    ),
                    types.PromptArgument(
                        name="repository",
                        description="Repository ID or name; leave empty to search every repository",
                        required=False,
                    ),
                ],
            ),
            "Find where {feature} is implemented{scope}.\n\n"
            "1. Call search_code with a short query that names it{search_scope}. If the first "
            "results miss, try another wording or an entity_type filter.\n"
            "2. Call list_definitions with name or path_prefix to see what surrounds the best hits, "
            "and find_references on a key function or class to see where it is used.\n"
            "3. Open the most likely candidates with get_file at the reported lines to confirm.\n\n"
            "Answer with the files and line ranges that implement it, how they connect, and the "
            "source links from the search results. If nothing matches, say so instead of guessing.",
        ),
    ]
}


def get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
    spec = PROMPTS.get(name)
    if spec is None:
        raise MCPError(types.INVALID_PARAMS, f"Unknown prompt '{name}'. Available prompts: {', '.join(PROMPTS)}")
    values = {k: v.strip() for k, v in (arguments or {}).items() if isinstance(v, str) and v.strip()}
    for argument in spec.prompt.arguments or []:
        if argument.required and argument.name not in values:
            raise MCPError(types.INVALID_PARAMS, f"Prompt '{name}' needs the '{argument.name}' argument")
    repository = values.get("repository")
    text = spec.template.format(
        repository=repository,
        feature=values.get("feature"),
        scope=f" in the repository '{repository}'" if repository else " across every indexed repository",
        search_scope=f", with repository '{repository}'" if repository else ", without a repository",
    )
    return types.GetPromptResult(
        description=spec.prompt.description,
        messages=[types.PromptMessage(role="user", content=types.TextContent(text=text))],
    )
