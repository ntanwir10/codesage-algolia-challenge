# CodeSage - MCP-First Code Discovery

🚀 **AI-powered code discovery through natural language** - Built entirely around the **Model Context Protocol (MCP)** for seamless integration with Claude Desktop and other AI clients.

> **CodeSage - MCP-First Code Discovery** - The only code discovery tool built entirely around the Model Context Protocol for seamless AI integration.

**Built for the [Algolia MCP Server Challenge](https://dev.to/challenges/algolia-2025-07-09)** 🏆

> Competing in the **Backend Data Optimization** and **Ultimate User Experience** categories with our innovative MCP-first approach to code discovery.

## 🎯 What is CodeSage?

**CodeSage - MCP-First Code Discovery** transforms GitHub repositories into **AI-searchable knowledge bases** through the Model Context Protocol. Submit a repository URL, and within minutes your AI assistant can discover functions, understand architecture, and answer complex questions about the codebase through natural language - all via MCP integration.

### **🎯 Final User Experience**

```text
1. User submits: github.com/facebook/react
2. System processes: GitHub → Parser → Algolia
3. User opens Claude Desktop  
4. User asks: "Show me React's rendering lifecycle"
5. Claude uses MCP tools to search and analyze
6. User gets AI-powered code insights
```

## 📊 Data Flow Architecture

```arch_flow
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Frontend  │───▶│   Backend    │───▶│   Algolia   │
│   (Simple)  │    │ (Processing) │    │  (Search)   │
└─────────────┘    └──────────────┘    └─────────────┘
                            │
                            ▼
                   ┌──────────────┐    ┌─────────────┐
                   │     MCP      │───▶│   Claude    │
                   │   Protocol   │    │  Desktop    │
                   └──────────────┘    └─────────────┘
```

### **Key Flows:**

- **Repository Management**: Frontend ↔ Backend
- **Code Discovery**: Claude Desktop ↔ MCP ↔ Backend ↔ Algolia
- **No Direct Integration**: Frontend never talks to Algolia or MCP

## ✨ Core Features

### 🔧 **MCP-First Architecture** - Our Unique Differentiator

- Built entirely around **Model Context Protocol** - the only code discovery tool with this architecture
- Works with **Claude Desktop** and any MCP-compatible AI client
- **No direct AI API calls** - all intelligence through MCP integration
- **Seamless AI Integration** - designed specifically for MCP-based AI workflows

### 🔍 **GitHub Repository Processing**

- **Automatic ingestion** from GitHub repository URLs
- **Code parsing** for functions, classes, imports across multiple languages
- **Algolia indexing** for fast, semantic code search

### 🤖 **Natural Language Code Discovery**

- Ask questions like *"How does authentication work?"*
- AI models search and analyze through MCP tools
- **Contextual, conversational** code exploration

### 🎯 **Simple Repository Management**

- Submit repository URLs for processing
- Track processing status (pending → processing → completed)
- Manage repository lifecycle (create, list, delete)

## 🚀 Quick Start

### Setup Prerequisites

- Python 3.9+ with virtual environment
- Node.js 18+ and npm
- Algolia account (App ID + Admin API Key)

### 1. **Development Mode (Recommended)**

```bash
# Setup environment
make setup
# Edit .env with your Algolia credentials

# Start backend + frontend together
make start

# Or start individually:
make start-backend    # Backend on :8001
make start-frontend   # Frontend on :5173
```

### **Manual Development Setup**

If you prefer to run servers manually without Make commands:

#### **Backend Server:**

```bash
# Navigate to project root
cd /Users/ntanwir/Developer/codesage-algolia-challenge

# Activate virtual environment
source .venv/bin/activate

# Go to backend directory  
cd backend

# Start FastAPI server
python -m uvicorn app.main:app --reload --port 8001
```

#### **Frontend Server** (in separate terminal)

```bash
# Navigate to project root
cd /Users/ntanwir/Developer/codesage-algolia-challenge

# Go to frontend directory
cd frontend

# Install dependencies (first time only)
npm install

# Start React development server
npm run dev
```

#### **What to Expect:**

**Backend Server (Terminal 1):**

```text
INFO:     Uvicorn running on http://127.0.0.1:8001 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using WatchFiles
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

✅ **Backend ready:** `http://localhost:8001`

- API Docs: `http://localhost:8001/docs`
- Health Check: `http://localhost:8001/health`

**Frontend Server (Terminal 2):**

```text
  Local:   http://localhost:5173/
  Network: use --host to expose
  press h + enter to show help
```

✅ **Frontend ready:** `http://localhost:5173`

#### **Quick Test:**

```bash
# Test backend health (in Terminal 3)
curl http://localhost:8001/health

# Test MCP endpoints
curl http://localhost:8001/api/v1/ai/mcp
```

### 2. **Docker Mode**

```bash
# For container-based development
make build
make up               # Both services via Docker

# Check status
make health
make logs
```

### 3. **Which approach to use?**

**✅ Use Development Mode when:**

- Actively developing/debugging code
- Need fast reload/hot-swapping
- Working on frontend styling
- Debugging MCP integration

**✅ Use Docker Mode when:**

- Testing production-like environment
- Demonstrating to others
- CI/CD pipeline
- Consistent environment across team

### **Environment Configuration**

Create `.env` file with your Algolia credentials:

```bash
ALGOLIA_APP_ID=your_app_id
ALGOLIA_ADMIN_API_KEY=your_admin_key
SECRET_KEY=your-secret-key-here
```

### **Testing MCP Endpoints**

Once your backend is running on `:8001`, test these endpoints:

```bash
# 1. MCP Server Information (NEW!)
curl http://localhost:8001/api/v1/ai/mcp

# 2. MCP Capabilities  
curl http://localhost:8001/api/v1/ai/mcp/capabilities

# 3. Available MCP Tools
curl http://localhost:8001/api/v1/ai/mcp/tools

# 4. Tool Call Instructions (if you try GET - shows how to use POST)
curl http://localhost:8001/api/v1/ai/mcp/tools/call

# 5. MCP Resources (with required uri parameter)
curl "http://localhost:8001/api/v1/ai/mcp/resources/read?uri=codesage://repositories"

# 6. Resources without uri (shows usage instructions)
curl http://localhost:8001/api/v1/ai/mcp/resources/read

# 7. Execute Tool (POST request - the correct way)
curl -X POST http://localhost:8001/api/v1/ai/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "search_code", "arguments": {"query": "function"}}'
```

**💡 Common Errors Fixed:**

- ❌ `GET /mcp/tools/call` → ✅ Now shows usage instructions
- ❌ `GET /mcp/resources/read` (no uri) → ✅ Now shows required parameters
- ✅ All endpoints now provide helpful error messages

**💡 Tip:** Visit `http://localhost:8001/docs` for interactive API documentation!

### Usage with Claude Desktop

1. **Submit repository**: POST to `/api/v1/repositories/` with GitHub URL
2. **Wait for processing**: Repository status becomes "completed"
3. **Connect Claude Desktop**: Configure MCP connection to `http://localhost:8001`
4. **Ask questions**: Use natural language to explore the codebase

## 🛠 API Endpoints

### Repository Management

```API
GET    /api/v1/repositories/        # List repositories
POST   /api/v1/repositories/        # Create repository  
GET    /api/v1/repositories/{id}    # Get repository
DELETE /api/v1/repositories/{id}    # Delete repository
```

### MCP Protocol

```API
GET    /api/v1/ai/mcp/capabilities     # MCP server capabilities
GET    /api/v1/ai/mcp/tools           # List MCP tools
POST   /api/v1/ai/mcp/tools/call      # Execute MCP tool
GET    /api/v1/ai/mcp/resources/read  # Read MCP resource
```

## 📦 MCP Tools Available

- **`search_code`** - Natural language code search across repositories
- **`analyze_repository`** - Repository overview and architectural insights
- **`explore_functions`** - Function discovery and relationship mapping
- **`explain_code`** - Detailed code explanations and documentation
- **`find_patterns`** - Pattern detection for security, performance, architecture

## 🔧 Technical Stack

### Backend

- **FastAPI** - Modern Python web framework
- **SQLAlchemy** - Database ORM with PostgreSQL/SQLite
- **Algolia** - Search and indexing engine
- **Pydantic** - Data validation and settings

### Frontend (Optional)

- **React 18** - Modern UI framework
- **TypeScript** - Type safety
- **TailwindCSS** - Utility-first styling
- **Vite** - Fast development and building

### MCP Integration - Our Core Innovation

- **Model Context Protocol** - AI integration standard (our primary differentiator)
- **Claude Desktop** - Primary AI client with seamless MCP integration
- **Tool-based architecture** - Extensible AI capabilities through MCP tools
- **MCP-First Design** - Every feature built around MCP protocol standards

## 📚 Documentation

- [`docs/architecture.md`](docs/architecture.md) - Technical architecture and implementation details
- [`.env.example`](.env.example) - Environment configuration template

## 📁 Project Structure

```tree
codesage-algolia-challenge/
├── backend/                    # FastAPI MCP Server
│   ├── app/
│   │   ├── api/v1/endpoints/  # API endpoints (repositories, ai, performance)
│   │   ├── core/              # Configuration and database
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── services/          # Business logic services
│   │   └── main.py           # FastAPI application
│   ├── requirements.txt       # Python dependencies
│   └── Dockerfile            # Container configuration
├── frontend/                  # React TypeScript UI
│   ├── src/
│   │   ├── components/       # Reusable UI components
│   │   ├── pages/           # Application pages
│   │   ├── services/        # API client and WebSocket
│   │   └── types/           # TypeScript definitions
│   └── package.json         # Node.js dependencies
├── deployment/              # Infrastructure & deployment
│   ├── docker-compose.yml   # Development setup
│   ├── docker-compose.prod.yml # Production setup
│   ├── nginx.conf          # Reverse proxy config
│   └── DOCKER.md           # Docker documentation
├── tests/                   # Organized test suites
│   ├── api/                # API endpoint tests
│   ├── mcp/                # MCP protocol tests
│   └── postman/            # Postman collection
├── docs/                   # Technical documentation
└── README.md              # Project overview
```
