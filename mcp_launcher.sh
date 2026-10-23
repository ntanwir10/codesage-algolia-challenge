#!/usr/bin/env bash
# Starts the CodeSage MCP stdio server for Claude Desktop.
# Configuration (MCP_SERVER_URL, CODESAGE_API_KEY) comes from the environment,
# which Claude Desktop sets from the "env" block of its config.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$REPO/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "CodeSage: $PYTHON not found. Create the virtualenv first (see README)." >&2
  exit 1
fi

cd "$REPO/backend" && exec "$PYTHON" -m codesage_mcp
