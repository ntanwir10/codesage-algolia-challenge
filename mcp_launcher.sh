#!/bin/bash
# Secure MCP Launcher for CodeSage
# This script loads environment variables and launches the MCP wrapper with robust error handling

# Enable strict error handling
set -euo pipefail

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Setup logging
LOG_FILE="$SCRIPT_DIR/mcp_launcher.log"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Function to cleanup on exit
cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log_message "ERROR: MCP launcher exited with code $exit_code"
    fi
    exit $exit_code
}

# Set up trap for cleanup
trap cleanup EXIT

log_message "INFO: Starting MCP launcher"

# Load environment variables from .env file if it exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    # Source the file safely, ignoring comments and empty lines
    set -a  # automatically export all variables
    source <(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^$')
    set +a
    log_message "INFO: Loaded environment variables from .env"
else
    log_message "WARNING: No .env file found at $SCRIPT_DIR/.env"
fi

# Set default MCP server URL if not set
export MCP_SERVER_URL="${MCP_SERVER_URL:-http://127.0.0.1:8001}"
log_message "INFO: Using MCP server URL: $MCP_SERVER_URL"

# Health check: Verify backend server is running
check_backend() {
    local max_retries=3
    local retry_delay=1
    
    for i in $(seq 1 $max_retries); do
        if curl -s --connect-timeout 5 --max-time 10 "$MCP_SERVER_URL/health" > /dev/null 2>&1; then
            log_message "INFO: Backend server is healthy"
            return 0
        fi
        
        if [ $i -lt $max_retries ]; then
            log_message "WARNING: Backend health check failed, retry $i/$max_retries in ${retry_delay}s"
            sleep $retry_delay
            retry_delay=$((retry_delay * 2))
        fi
    done
    
    log_message "ERROR: Backend server health check failed after $max_retries attempts"
    echo '{"jsonrpc": "2.0", "error": {"code": -32000, "message": "Backend server unavailable"}}' >&2
    return 1
}

# Check if backend is healthy before starting
if ! check_backend; then
    exit 1
fi

# Find Python executable with better detection
find_python() {
    # Try common Python paths in order of preference
    local python_candidates=(
        "python3"
        "/usr/bin/python3"
        "/usr/local/bin/python3"
        "/opt/homebrew/bin/python3"
        "$HOME/.pyenv/shims/python3"
    )
    
    for python_path in "${python_candidates[@]}"; do
        if command -v "$python_path" > /dev/null 2>&1; then
            # Verify it's Python 3.8+
            if "$python_path" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
                echo "$python_path"
                return 0
            fi
        fi
    done
    
    log_message "ERROR: No suitable Python 3.8+ interpreter found"
    echo '{"jsonrpc": "2.0", "error": {"code": -32001, "message": "No suitable Python interpreter found"}}' >&2
    return 1
}

# Get Python path
PYTHON_PATH=$(find_python) || exit 1
log_message "INFO: Using Python interpreter: $PYTHON_PATH"

# Verify Python dependencies
if ! "$PYTHON_PATH" -c "import aiohttp, asyncio" 2>/dev/null; then
    log_message "ERROR: Required Python dependencies not found (aiohttp, asyncio)"
    echo '{"jsonrpc": "2.0", "error": {"code": -32002, "message": "Missing Python dependencies"}}' >&2
    exit 1
fi

# Verify wrapper script exists
if [ ! -f "$SCRIPT_DIR/mcp_wrapper.py" ]; then
    log_message "ERROR: MCP wrapper script not found at $SCRIPT_DIR/mcp_wrapper.py"
    echo '{"jsonrpc": "2.0", "error": {"code": -32003, "message": "MCP wrapper script not found"}}' >&2
    exit 1
fi

log_message "INFO: Launching MCP wrapper with arguments: $*"

# Launch the MCP wrapper with the correct Python
exec "$PYTHON_PATH" "$SCRIPT_DIR/mcp_wrapper.py" "$@" 2>> "$LOG_FILE" 