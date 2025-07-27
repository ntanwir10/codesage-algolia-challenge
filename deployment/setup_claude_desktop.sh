#!/bin/bash

# Setup script for Claude Desktop integration with CodeSage
# This script sets up environment variables and copies configuration

echo "🔧 Setting up Claude Desktop for CodeSage..."

# Load environment variables from backend/.env
if [ -f ".env" ]; then
    echo "📄 Loading environment variables from .env..."
    source .env
    export ALGOLIA_APP_ID
    export ALGOLIA_ADMIN_API_KEY
    export GITHUB_TOKEN
    export DATABASE_URL
else
    echo "❌ .env file not found in backend directory"
    exit 1
fi

# Check if Claude Desktop directory exists
CLAUDE_DIR="$HOME/Library/Application Support/Claude"
if [ ! -d "$CLAUDE_DIR" ]; then
    echo "📁 Creating Claude Desktop directory..."
    mkdir -p "$CLAUDE_DIR"
fi

# Create the configuration with environment variables resolved
echo "📝 Creating Claude Desktop configuration..."
cat > "$CLAUDE_DIR/claude_desktop_config.json" << EOF
{
  "mcpServers": {
    "codesage": {
      "command": "python3",
      "args": ["$(pwd)/mcp_wrapper.py"],
      "env": {
        "MCP_SERVER_URL": "http://127.0.0.1:8001",
        "ALGOLIA_APP_ID": "$ALGOLIA_APP_ID",
        "ALGOLIA_ADMIN_API_KEY": "$ALGOLIA_ADMIN_API_KEY",
        "GITHUB_TOKEN": "$GITHUB_TOKEN",
        "DATABASE_URL": "$DATABASE_URL"
      }
    }
  },
  "global": {
    "allowAllServers": true
  }
}
EOF

echo "✅ Claude Desktop configuration created successfully!"
echo "📍 Configuration saved to: $CLAUDE_DIR/claude_desktop_config.json"
echo ""
echo "🚀 Next steps:"
echo "1. Start CodeSage backend server:"
echo "   python -m uvicorn app.main:app --host 127.0.0.1 --port 8001"
echo ""
echo "2. Restart Claude Desktop application"
echo ""
echo "3. Test in Claude Desktop by asking:"
echo "   'Search for functions in my code'"
echo ""
echo "📋 MCP Server will be available as 'codesage' in Claude Desktop" 