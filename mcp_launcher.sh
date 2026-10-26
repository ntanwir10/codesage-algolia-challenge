#!/usr/bin/env bash
# Starts the CodeSage MCP stdio server for Claude Desktop.
# Configuration (MCP_SERVER_URL, CODESAGE_API_KEY) comes from the environment,
# which Claude Desktop sets from the "env" block of its config.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$REPO/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "CodeSage: $PYTHON not found. Run \`make setup\` in $REPO to create the virtualenv." >&2
  exit 1
fi

if ! (cd "$REPO/backend" && "$PYTHON" -c 'import codesage_mcp, mcp'); then
  echo "CodeSage: the Python dependencies are missing in $REPO/.venv. Run \`make setup\` in $REPO." >&2
  exit 1
fi

# A basic-auth password lives in the macOS Keychain, not in the Claude Desktop config
if [ -n "${CODESAGE_BASIC_AUTH_USER:-}" ] && [ -z "${CODESAGE_BASIC_AUTH_PASSWORD:-}" ] \
    && command -v security >/dev/null; then
  CODESAGE_BASIC_AUTH_PASSWORD="$(security find-generic-password -s codesage-mcp \
    -a "$CODESAGE_BASIC_AUTH_USER" -w 2>/dev/null || true)"
  export CODESAGE_BASIC_AUTH_PASSWORD
  if [ -z "$CODESAGE_BASIC_AUTH_PASSWORD" ]; then
    echo "CodeSage: no Keychain password found for $CODESAGE_BASIC_AUTH_USER (service codesage-mcp); continuing with an empty password." >&2
  fi
fi

cd "$REPO/backend" && exec "$PYTHON" -m codesage_mcp
