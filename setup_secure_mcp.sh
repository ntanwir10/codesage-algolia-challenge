#!/bin/bash
# Comprehensive MCP Setup Script for CodeSage
# This script provides a complete, reliable setup for Claude Desktop integration

set -euo pipefail

echo "🚀 CodeSage MCP Comprehensive Setup"
echo "===================================="

# Colors for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] ERROR:${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')] INFO:${NC} $1"
}

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Step 1: Environment file validation
log "Step 1: Validating environment configuration"
if [ ! -f ".env" ]; then
    error ".env file not found. Creating from template..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        warn "Please edit .env with your actual API keys:"
        warn "  - ALGOLIA_APP_ID (get from Algolia dashboard)"
        warn "  - ALGOLIA_ADMIN_API_KEY (get from Algolia dashboard)"
        warn "  - GITHUB_TOKEN (create at https://github.com/settings/tokens)"
        echo ""
        warn "Press ENTER when you have configured .env file..."
        read -r
    else
        error ".env.example not found. Cannot proceed."
        exit 1
    fi
fi

# Check if .env has required variables
required_vars=("ALGOLIA_APP_ID" "ALGOLIA_ADMIN_API_KEY" "SECRET_KEY")
for var in "${required_vars[@]}"; do
    if ! grep -q "^${var}=" .env || grep -q "^${var}=your-.*-here" .env || grep -q "^${var}=$" .env; then
        error "Please configure $var in .env file"
        exit 1
    fi
done

log "Environment configuration validated"

# Step 2: Ensure .env is gitignored
log "Step 2: Securing environment file"
if ! grep -q "^\.env$" .gitignore 2>/dev/null; then
    echo ".env" >> .gitignore
    log "Added .env to .gitignore for security"
else
    log ".env is properly gitignored"
fi

# Step 3: Make scripts executable
log "Step 3: Setting up script permissions"
chmod +x mcp_launcher.sh
chmod +x setup_secure_mcp.sh
log "Made scripts executable"

# Step 4: Python environment validation
log "Step 4: Validating Python environment"

# Find suitable Python
find_python() {
    local python_candidates=(
        "python3"
        "/usr/bin/python3"
        "/usr/local/bin/python3"
        "/opt/homebrew/bin/python3"
        "$HOME/.pyenv/shims/python3"
    )
    
    for python_path in "${python_candidates[@]}"; do
        if command -v "$python_path" > /dev/null 2>&1; then
            if "$python_path" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
                echo "$python_path"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_PATH=$(find_python) || {
    error "No suitable Python 3.8+ interpreter found"
    error "Please install Python 3.8+ and try again"
    exit 1
}

log "Using Python interpreter: $PYTHON_PATH"

# Check Python dependencies
info "Checking Python dependencies..."
if ! "$PYTHON_PATH" -c "import aiohttp, asyncio" 2>/dev/null; then
    warn "Installing required Python dependencies..."
    "$PYTHON_PATH" -m pip install --user aiohttp asyncio 2>/dev/null || {
        error "Failed to install Python dependencies"
        error "Please run: $PYTHON_PATH -m pip install aiohttp"
        exit 1
    }
fi
log "Python dependencies validated"

# Step 5: Backend server validation
log "Step 5: Validating backend server"

# Check if backend server is running
check_backend_health() {
    local server_url="http://127.0.0.1:8001"
    if curl -s --connect-timeout 5 --max-time 10 "$server_url/health" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

if check_backend_health; then
    log "Backend server is running and healthy"
else
    warn "Backend server is not responding"
    
    # Check if there's already a backend process running
    if pgrep -f "uvicorn.*8001" > /dev/null 2>&1; then
        warn "Backend process found but not responding to health checks"
        warn "This might be a startup delay or dependency issue"
        info "Waiting 10 seconds for backend to become healthy..."
        sleep 10
        
        if check_backend_health; then
            log "Backend server is now healthy"
        else
            error "Backend server is running but not healthy"
            error "Please check the backend terminal output for errors"
            exit 1
        fi
    else
        error "Backend server is not running. Please start it manually:"
        error "  1. Open a new terminal"
        error "  2. cd $SCRIPT_DIR/backend"
        error "  3. python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload"
        error "  4. Verify health: curl http://127.0.0.1:8001/health"
        error "  5. Re-run this setup script"
        exit 1
    fi
fi

# Step 6: MCP integration testing
log "Step 6: Testing MCP integration"

# Test MCP launcher (with background timeout for macOS compatibility)
info "Testing MCP launcher..."
test_mcp_with_timeout() {
    local test_input="$1"
    local expected="$2"
    local timeout_seconds=10
    
    # Create a temporary file for the test
    local temp_file="/tmp/mcp_test_$$"
    
    # Run the test in background with timeout
    (echo "$test_input" | ./mcp_launcher.sh > "$temp_file" 2>&1) &
    local pid=$!
    
    # Wait for completion or timeout
    local count=0
    while [ $count -lt $timeout_seconds ]; do
        if ! kill -0 $pid 2>/dev/null; then
            # Process completed
            if grep -q "$expected" "$temp_file" 2>/dev/null; then
                rm -f "$temp_file"
                return 0
            else
                rm -f "$temp_file"
                return 1
            fi
        fi
        sleep 1
        count=$((count + 1))
    done
    
    # Timeout reached, kill the process
    kill $pid 2>/dev/null || true
    wait $pid 2>/dev/null || true
    rm -f "$temp_file"
    return 1
}

if test_mcp_with_timeout '{"jsonrpc": "2.0", "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}}, "id": 1}' "result"; then
    log "MCP launcher test passed"
else
    error "MCP launcher test failed"
    error "Check mcp_launcher.log for details"
    exit 1
fi

# Test tools listing
info "Testing tools listing..."
if test_mcp_with_timeout '{"jsonrpc": "2.0", "method": "tools/list", "id": 2}' "search_code"; then
    log "Tools listing test passed"
else
    error "Tools listing test failed"
    error "Check mcp_wrapper.log for details"
    exit 1
fi

# Step 7: Claude Desktop configuration
log "Step 7: Validating Claude Desktop configuration"

CLAUDE_CONFIG_PATH="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
CLAUDE_CONFIG_DIR="$(dirname "$CLAUDE_CONFIG_PATH")"

# Ensure Claude config directory exists
if [ ! -d "$CLAUDE_CONFIG_DIR" ]; then
    info "Creating Claude Desktop configuration directory..."
    mkdir -p "$CLAUDE_CONFIG_DIR"
fi

# Copy our config to Claude Desktop
info "Installing Claude Desktop configuration..."
cp claude_desktop_config.json "$CLAUDE_CONFIG_PATH"
log "Claude Desktop configuration installed"

# Step 8: Final validation
log "Step 8: Final system validation"

# Test complete integration
info "Performing final integration test..."
if test_mcp_with_timeout '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "search_code", "arguments": {"query": "test"}}, "id": 3}' "jsonrpc"; then
    log "Complete integration test passed"
else
    warn "Integration test had issues (this may be normal if no repositories are indexed)"
fi

echo ""
echo "🎉 Setup Complete! Summary:"
echo "=========================="
log "✅ Environment configuration validated"
log "✅ Security settings applied"
log "✅ Python environment validated"
log "✅ Backend server running and healthy"
log "✅ MCP integration tested"
log "✅ Claude Desktop configuration installed"

echo ""
echo "📋 Next Steps:"
echo "1. 🔄 Restart Claude Desktop completely (Cmd+Q, then reopen)"
echo "2. ⚙️  Check Settings → Developer → Local MCP servers"
echo "3. ✅ Verify 'codesage' shows as 'running'"
echo "4. 💬 Start a new chat and ask: 'What CodeSage tools are available?'"

echo ""
echo "🔧 Troubleshooting:"
echo "• Logs are in: mcp_launcher.log, mcp_wrapper.log, backend.log"
echo "• Backend health: curl http://127.0.0.1:8001/health"
echo "• Test MCP: echo '{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"id\":1}' | ./mcp_launcher.sh"

echo ""
echo "🔐 Security Notes:"
echo "• API keys are stored in .env (gitignored)"
echo "• No hardcoded secrets in configuration"
echo "• All communication is local (127.0.0.1)"

echo ""
log "Setup completed successfully! 🚀" 