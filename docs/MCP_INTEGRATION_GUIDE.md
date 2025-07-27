# CodeSage - MCP-First Code Discovery: MCP Integration Guide

A comprehensive guide for setting up a clean, reliable integration of **CodeSage - MCP-First Code Discovery** MCP Server with Claude Desktop.

## 🎯 Overview

This guide provides a complete, foolproof setup process for integrating the **CodeSage - MCP-First Code Discovery** MCP (Model Context Protocol) server with Claude Desktop. The integration enables Claude to directly access your codebase through natural language queries, code analysis, and intelligent search capabilities - all through our unique MCP-first architecture.

## 📚 Documentation Structure

We have two complementary documentation files:

| Document                                        | Purpose                                                                       | When to Use                                               |
| ----------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------- |
| **`docs/MCP_INTEGRATION_GUIDE.md`** (This file) | 📖 **Complete reference guide** - Step-by-step setup, troubleshooting, testing | ✅ **First-time setup, troubleshooting, reference**        |
| **`MCP_INTEGRATION_SUMMARY.md`**                | 📋 **Problem & solution summary** - What was fixed, improvements made          | ✅ **Understanding what was improved, technical overview** |

### Why Two Documents?

#### `MCP_INTEGRATION_GUIDE.md` (This Document)

**Focus:** "How to set up and use the integration"

**Content:**

- ✅ Step-by-step setup instructions
- ✅ Prerequisites and requirements  
- ✅ Troubleshooting common issues
- ✅ Testing procedures
- ✅ Configuration details
- ✅ Security and performance features
- ✅ Maintenance and updates

#### `MCP_INTEGRATION_SUMMARY.md`

**Focus:** "What problems were solved and how"

**Content:**

- ✅ Technical improvements made
- ✅ Reliability features added (circuit breaker, retry logic)
- ✅ Before/after comparison
- ✅ Architecture enhancements
- ✅ Problem resolution details
- ✅ Benefits achieved

**Use both together:**

1. **Read the Summary** to understand what was improved
2. **Follow this Guide** for actual setup and usage

## ✨ Features

- **🔍 Natural Language Code Search**: Search your codebase using plain English
- **📊 Repository Analysis**: Get insights into code structure, patterns, and complexity
- **🔧 Function Explorer**: Discover and understand functions, classes, and variables
- **📖 Code Explanation**: Get detailed explanations of code snippets
- **🎯 Pattern Detection**: Find code patterns, anti-patterns, and security issues

## 🚀 Quick Setup

### Prerequisites

- **macOS with Claude Desktop** installed
- **Python 3.8+** with `aiohttp` package
- **API Keys**:
  - Algolia App ID and Admin API Key ([Get from Algolia Dashboard](https://www.algolia.com/))
  - GitHub Personal Access Token ([Create Here](https://github.com/settings/tokens))

### One-Command Setup

```bash
# Run the comprehensive setup script
./setup_secure_mcp.sh
```

The setup script will:

1. ✅ Validate environment configuration
2. 🔐 Secure your API keys
3. 🐍 Check Python environment
4. 🏥 Verify backend server health
5. 🧪 Test MCP integration
6. ⚙️ Install Claude Desktop configuration
7. 🎉 Complete end-to-end validation

## 📋 Manual Setup (If Needed)

### Step 1: Environment Configuration

1. **Create Environment File**:

   ```bash
   cp .env.example .env
   ```

2. **Configure API Keys** in `.env`:

   ```env
   # Algolia Configuration
   ALGOLIA_APP_ID=your-algolia-app-id-here
   ALGOLIA_ADMIN_API_KEY=your-algolia-admin-api-key-here
   ALGOLIA_INDEX_NAME=codesage_code_entities

   # GitHub Configuration  
   GITHUB_TOKEN=your-github-personal-access-token-here

   # Security
   SECRET_KEY=your-secret-key-here-change-this-in-production
   ```

### Step 2: Start Backend Server

```bash
# Navigate to backend directory
cd backend

# Start the server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Verify health (in another terminal)
curl http://127.0.0.1:8001/health
```

### Step 3: Install Claude Desktop Configuration

```bash
# Copy configuration to Claude Desktop
cp claude_desktop_config.json "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
```

### Step 4: Restart Claude Desktop

1. **Quit Claude Desktop** completely (`Cmd+Q`)
2. **Reopen Claude Desktop**
3. **Check Settings** → Developer → Local MCP servers
4. **Verify** 'codesage' shows as 'running'

## 🧪 Testing the Integration

### Basic Tests

```bash
# Test MCP launcher
echo '{"jsonrpc": "2.0", "method": "initialize", "id": 1}' | ./mcp_launcher.sh

# Test tools listing
echo '{"jsonrpc": "2.0", "method": "tools/list", "id": 2}' | ./mcp_launcher.sh

# Test backend health
curl http://127.0.0.1:8001/health
```

### Claude Desktop Tests

Start a new conversation in Claude Desktop and try:

```text
What CodeSage tools are available?
```

```text
Search for functions related to user authentication
```

```text
Analyze the structure of this repository
```

## 🔧 Troubleshooting

### Common Issues

#### 1. "MCP server not responding"

**Symptoms**: Claude Desktop shows 'codesage' as not running

**Solutions**:

```bash
# Check if backend is running
curl http://127.0.0.1:8001/health

# Check MCP launcher
echo '{"jsonrpc": "2.0", "method": "initialize", "id": 1}' | ./mcp_launcher.sh

# Check logs
tail -f mcp_launcher.log
tail -f mcp_wrapper.log
```

#### 2. "Backend server not responding"

**Symptoms**: Health check fails, connection refused

**Solutions**:

```bash
# Check if server is running
ps aux | grep uvicorn

# Start backend server
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Check for port conflicts
lsof -i :8001
```

#### 3. "Python dependencies missing"

**Symptoms**: Import errors for aiohttp, asyncio

**Solutions**:

```bash
# Install dependencies
python3 -m pip install aiohttp

# Or use requirements file
cd backend
pip install -r requirements.txt
```

#### 4. "API keys not configured"

**Symptoms**: Algolia or GitHub API errors

**Solutions**:

```bash
# Check .env file exists and has values
cat .env | grep -E "(ALGOLIA|GITHUB)"

# Update .env with your actual API keys
vim .env
```

### Advanced Debugging

#### Enable Debug Logging

Edit `claude_desktop_config.json`:

```json
{
  "global": {
    "logging": {
      "level": "debug"
    }
  }
}
```

#### View Detailed Logs

```bash
# MCP Launcher logs
tail -f mcp_launcher.log

# MCP Wrapper logs  
tail -f mcp_wrapper.log

# Backend logs (if started manually)
tail -f backend.log
```

#### Test Individual Components

```bash
# Test Python environment
python3 -c "import aiohttp, asyncio; print('Dependencies OK')"

# Test backend directly
curl -X POST http://127.0.0.1:8001/api/v1/ai/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "search_code", "arguments": {"query": "test"}}'

# Test MCP wrapper directly
python3 mcp_wrapper.py
```

## 📁 Script Purpose & File Structure

### Setup Scripts

| Script                        | Purpose                                                                         | When to Use                                               |
| ----------------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------- |
| **`setup_secure_mcp.sh`**     | 🎯 **Main setup script** - Comprehensive, production-ready setup with validation | ✅ **Use this 99% of the time** - Complete automated setup |
| **`setup_claude_desktop.sh`** | 🔧 **Simple setup** - Basic Claude Desktop configuration only                    | ✅ **Backup option** if comprehensive setup fails          |
| **`mcp_launcher.sh`**         | 🚀 **Runtime launcher** - Called automatically by Claude Desktop                 | ❌ **Never run manually** - Claude Desktop executes this   |

### Setup Script Details

#### `setup_secure_mcp.sh` (Recommended)

**Purpose:** Complete, bulletproof setup with enterprise-grade reliability

**What it does:**

- ✅ Validates environment configuration (`.env` file)
- ✅ Checks Python dependencies and interpreter
- ✅ Verifies backend server health
- ✅ Tests MCP integration end-to-end
- ✅ Sets up Claude Desktop configuration
- ✅ Provides comprehensive troubleshooting info
- ✅ Security validation (ensures `.env` is gitignored)

**Usage:**

```bash
./setup_secure_mcp.sh  # Use this for normal setup
```

#### `setup_claude_desktop.sh` (Legacy/Backup)

**Purpose:** Simple, manual-control setup for custom scenarios

**What it does:**

- ✅ Loads environment variables from `.env`
- ✅ Creates Claude Desktop configuration
- ✅ Basic validation only

**When to use:**

- If comprehensive setup fails
- For custom deployment scenarios
- When you need manual control over configuration

**Usage:**

```bash
./setup_claude_desktop.sh  # Only if main setup fails
```

#### `mcp_launcher.sh` (Runtime Component)

**Purpose:** Bridge between Claude Desktop and your backend server

**What it does:**

- ✅ Loads environment variables securely
- ✅ Performs backend health checks
- ✅ Finds correct Python interpreter
- ✅ Launches `mcp_wrapper.py` with error handling
- ✅ Provides logging and troubleshooting info

**When it's executed:**

- ✅ **Automatically by Claude Desktop** when you use MCP tools
- ✅ **For manual testing:** `echo '{"jsonrpc":"2.0","method":"initialize","id":1}' | ./mcp_launcher.sh`
- ❌ **NOT during setup** - it's a runtime component

### File Structure

```tree
codesage-algolia-challenge/
├── setup_secure_mcp.sh          # 🎯 Main setup (use this)
├── setup_claude_desktop.sh      # 🔧 Simple setup (backup)
├── mcp_launcher.sh              # 🚀 Runtime launcher (Claude calls this)
├── mcp_wrapper.py               # Enhanced MCP wrapper with logging
├── claude_desktop_config.json   # Claude Desktop configuration
├── .env                         # Environment variables (gitignored)
├── .env.example                 # Environment template
├── MCP_INTEGRATION_SUMMARY.md   # Summary of improvements made
└── docs/
    └── MCP_INTEGRATION_GUIDE.md # This comprehensive guide
```

## 🔐 Security Features

- **Environment Variables**: All API keys stored in `.env` (gitignored)
- **Local Communication**: All traffic stays on `127.0.0.1`
- **No Hardcoded Secrets**: Configuration uses environment variables only
- **Access Control**: MCP server only accessible locally

## 🚀 Performance Optimizations

- **Connection Pooling**: Reuses HTTP connections for better performance
- **Tool Caching**: Caches tool definitions for 5 minutes
- **Retry Logic**: Automatic retry for transient network issues
- **Timeout Handling**: Prevents hanging requests

## 🔄 Updates and Maintenance

### Updating Configuration

```bash
# Re-run setup script after changes
./setup_secure_mcp.sh

# Or manually update Claude Desktop config
cp claude_desktop_config.json "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
```

### Monitoring Health

```bash
# Check system health
curl http://127.0.0.1:8001/health

# View recent logs
tail -20 mcp_launcher.log
tail -20 mcp_wrapper.log
```

## 🆘 Getting Help

### Log Files Location

- `mcp_launcher.log` - Launcher script logs
- `mcp_wrapper.log` - MCP wrapper logs  
- `backend.log` - Backend server logs (if started by script)

### Health Check Commands

```bash
# Backend health
curl http://127.0.0.1:8001/health

# MCP initialization
echo '{"jsonrpc": "2.0", "method": "initialize", "id": 1}' | ./mcp_launcher.sh

# Tools availability  
echo '{"jsonrpc": "2.0", "method": "tools/list", "id": 2}' | ./mcp_launcher.sh
```

### Reset Everything

```bash
# Stop all processes
pkill -f uvicorn
pkill -f mcp_wrapper

# Clean logs
rm -f *.log

# Re-run setup
./setup_secure_mcp.sh
```

## ✅ Success Indicators

You know the integration is working when:

1. ✅ `curl http://127.0.0.1:8001/health` returns healthy status
2. ✅ Claude Desktop shows 'codesage' as 'running' in MCP servers
3. ✅ Claude responds to "What CodeSage tools are available?"
4. ✅ You can search your codebase through Claude
5. ✅ No errors in `mcp_launcher.log` or `mcp_wrapper.log`

## 🎯 Next Steps

After successful setup:

1. **Index Your Repositories**: Add your code repositories through the web interface
2. **Explore Tools**: Try different CodeSage tools in Claude Desktop
3. **Customize Configuration**: Adjust settings in `.env` as needed
4. **Monitor Performance**: Keep an eye on logs and health status

---

**Need help?** Check the logs first, then refer to the troubleshooting section above. The setup script provides detailed error messages and suggestions for common issues. 