"""Run the CodeSage MCP server over stdio: ``python -m codesage_mcp``."""

import anyio

from codesage_mcp.server import run_stdio


def main() -> None:
    try:
        anyio.run(run_stdio)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
