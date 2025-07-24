# CodeSage - MCP-First Code Discovery

🚀 **AI-powered code discovery through natural language** - Built entirely around the **Model Context Protocol (MCP)** for seamless integration with Claude Desktop and other AI clients.

**Built for the [Algolia MCP Server Challenge](https://dev.to/challenges/algolia-2025-07-09)** 🏆

> Competing in the **Backend Data Optimization** and **Ultimate User Experience** categories with our innovative MCP-first approach to code discovery.

## 🎯 What is CodeSage?

CodeSage transforms GitHub repositories into **AI-searchable knowledge bases**. Submit a repository URL, and within minutes your AI assistant can discover functions, understand architecture, and answer complex questions about the codebase through natural language.

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

### 🔧 **MCP-First Architecture**

- Built entirely around **Model Context Protocol**
- Works with **Claude Desktop** and any MCP-compatible AI client
- **No direct AI API calls** - all intelligence through MCP

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

### Prerequisites

- Python 3.8+
- Node.js 18+
- Algolia account ([sign up free](https://www.algolia.com/))

### Setup

```bash
# 1. Clone and configure
git clone https://github.com/yourusername/codesage-algolia-challenge
cd codesage-algolia-challenge
cp .env.example .env

# 2. Add your Algolia credentials to .env
ALGOLIA_APP_ID=your_app_id_here
ALGOLIA_ADMIN_API_KEY=your_admin_key_here

# 3. Start backend
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001

# 4. Start frontend (optional)
cd ../frontend
npm install
npm run dev
```

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

### MCP Integration

- **Model Context Protocol** - AI integration standard
- **Claude Desktop** - Primary AI client
- **Tool-based architecture** - Extensible AI capabilities

## 📚 Documentation

- [`docs/architecture.md`](docs/architecture.md) - Technical architecture and implementation details
- [`.env.example`](.env.example) - Environment configuration template
