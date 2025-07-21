# CodeSage - AI-Powered Code Discovery Platform

🚀 **Algolia MCP Server Challenge Entry** - An intelligent, conversational code discovery platform built around **Algolia MCP Server** that revolutionizes how developers explore and understand codebases through natural language conversations.

## 🎯 Project Overview

**⚠️ IMPORTANT: This application is built around ALGOLIA MCP SERVER as the core architecture. All AI capabilities come through the Model Context Protocol, not direct API calls.**

CodeSage transforms code exploration from a tedious search process into an intelligent conversation powered by **Algolia MCP Server**. Users interact with AI models (like Claude Desktop) that connect to our MCP server to search and understand code through natural language.

**Architecture Philosophy:**

```arch
User ↔ AI Model (Claude/GPT) ↔ MCP Client ↔ CodeSage MCP Server ↔ Algolia Search ↔ Code Data
```

### 🏆 Challenge Categories

- **Backend Data Optimization Prize**: Advanced MCP server integration with semantic code analysis and real-time indexing via Algolia
- **Ultimate User Experience Prize**: Natural language code discovery through MCP protocol
- **Overall Winner Prize**: Revolutionary MCP-first approach to developer productivity

## ✨ Standout Features

### 🔄 **MCP-First Architecture**

- Built entirely around Algolia MCP Server protocol
- No direct AI API calls - all intelligence through MCP
- Works with any MCP-compatible AI client (Claude Desktop, custom clients)

### 🤖 **Natural Language Code Discovery**

- Ask questions like "How does authentication work?" through MCP clients
- AI models use our MCP server to search and understand code
- Contextual, conversational code exploration

### 🔍 **Advanced Code Indexing**

- Semantic code analysis and indexing to Algolia
- Multi-language code parsing with tree-sitter
- Real-time repository processing and updates

### 👥 **Real-time Collaboration Through MCP**

- Multiple developers can explore code together via MCP protocol
- Shared context and collaborative discovery sessions

## 🛠 Technology Stack

### **MCP-First Backend**

- **Algolia MCP Server** - Core intelligence and search capabilities
- **FastAPI** - MCP server integration and data processing
- **PostgreSQL** - Repository and metadata storage
- **tree-sitter** - Multi-language code parsing
- **Algolia Search** - Advanced search and indexing

### **No Direct AI Dependencies**

- ✅ All AI through MCP protocol
- ✅ Works with any MCP client
- ❌ No OpenAI API calls
- ❌ No direct LLM integration  

### Frontend Implementation

- **React 18 + TypeScript + Vite** - Modern frontend stack with type safety
- **shadcn/ui + TailwindCSS** - Beautiful, accessible component library
- **React Query (TanStack Query)** - Server state management and caching
- **React Hook Form + Zod** - Form validation and type-safe schemas
- **WebSocket Integration** - Real-time repository processing updates
- **Monaco Editor** - VS Code-quality code viewing (optional)

**Frontend Features:**

- **GitHub URL Submission** - Clean interface for repository input with validation
- **Real-time Processing Dashboard** - Live status updates via WebSocket
- **AI-Powered Q&A Interface** - Chat-style interface for MCP tool interactions
- **Responsive Design** - Mobile-first approach with modern UI/UX

## 🚀 Quick Start with MCP

### Prerequisites

- Docker & Docker Compose
- **Algolia account** (app ID + API keys)
- **MCP Client** (Claude Desktop recommended)

### 1. Setup Environment

```bash
# Clone the repository
git clone <repository-url>
cd codesage-algolia-challenge

# Setup development environment
make setup

# Edit .env file with your Algolia keys (NO OpenAI needed!)
nano .env
```

### 2. Required API Keys (MCP-First)

Add these to your `.env` file:

```bash
# MINIMAL REQUIRED CONFIGURATION
SECRET_KEY=your-secure-secret-key-here
ALGOLIA_APP_ID=your-algolia-app-id
ALGOLIA_ADMIN_API_KEY=your-algolia-admin-api-key

# DEVELOPMENT SETTINGS  
ENVIRONMENT=development
DEBUG=true

# Docker defaults work for local development (uncomment if needed)
# DATABASE_URL=postgresql://codesage:codesage123@postgres:5432/codesage
# REDIS_URL=redis://redis:6379/0
```

**That's it!** Only 3 variables are required:

- ✅ `SECRET_KEY` - For application security
- ✅ `ALGOLIA_APP_ID` - For MCP server search functionality  
- ✅ `ALGOLIA_ADMIN_API_KEY` - For MCP server search functionality (admin access required)

❌ **No OpenAI API key needed** - AI comes through MCP clients!

### 3. Start MCP Server

```bash
# Build and start the CodeSage MCP server
make dev

# The MCP server will be available for AI clients to connect
```

### 4. Connect AI Client (Claude Desktop)

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "codesage": {
      "command": "python",
      "args": ["-m", "codesage_mcp_server", "--host", "localhost", "--port", "8000"],
      "env": {
        "ALGOLIA_APP_ID": "your-app-id",
        "ALGOLIA_API_KEY": "your-api-key"
      }
    }
  }
}
```

### 5. Start Conversational Code Discovery

Open Claude Desktop and start asking about your code:

```text
"How does user authentication work in this repository?"
"Show me all security vulnerabilities"
"What are the most complex functions?"
"Explain the database schema"
```

### 6. Frontend Setup (Optional)

For the web interface, set up the React frontend:

```bash
# Create React frontend project
npm create vite@latest codesage-frontend -- --template react-ts
cd codesage-frontend

# Install dependencies
npm install @tanstack/react-query @hookform/react-hook-form zod
npm install @radix-ui/react-slot class-variance-authority clsx tailwind-merge
npm install lucide-react framer-motion

# Setup shadcn/ui
npx shadcn-ui@latest init

# Configure environment
echo "VITE_API_BASE_URL=http://localhost:8000" > .env

# Start development server
npm run dev
```

The frontend will provide:

- **GitHub URL submission interface** with validation
- **Real-time repository processing dashboard**
- **AI-powered chat interface** for code questions
- **Rich code display** with syntax highlighting

## 📖 Documentation

For comprehensive documentation, see the **[docs/](./docs/)** folder:

- **[Architecture Overview](./docs/architecture.md)** - Simplified MCP-first system design
- **[Frontend Implementation Plan](./docs/frontend_plan.md)** - Complete React frontend strategy and technical details
- **[MCP-First Reference](./docs/MCP-FIRST-ARCHITECTURE.md)** - Critical MCP protocol compliance guide  
- **[Deployment Strategy](./docs/deployment-and-costs.md)** - Complete deployment and cost analysis
- **[Project Plan](./docs/plan.md)** - Original project planning document

## 🏗 MCP-First Architecture Overview

### Complete User Flow (Frontend + Backend)

**Repository Submission Flow:**

```arch
Frontend GitHub URL Input → Repository Creation API → Backend Processing → Algolia Indexing → Ready for Questions
           ↓                          ↓                       ↓                  ↓
    Real-time Status ← WebSocket Updates ← Processing Pipeline ← Code Analysis
```

**AI Question & Answer Flow:**

```arch
Frontend Chat Interface → MCP Tool Call → CodeSage MCP Server → Algolia Search → AI Response
         ↓                     ↓                ↓                    ↓            ↓
    User sees results ← Formatted Response ← Search Results ← Code Analysis ← Indexed Data
```

### MCP Protocol Data Flow

```arch
User Query → AI Model → MCP Client → CodeSage MCP Server → Algolia Search → Results → AI Response
     ↓              ↓               ↓                     ↓              ↓
Real-time Updates ← Background Jobs ← Code Analysis ← Repository Upload ← Developer
```

### Core Components

1. **CodeSage MCP Server**
   - Implements Model Context Protocol specification
   - Bridges AI models with Algolia search
   - Handles natural language to search translation

2. **Code Processing Pipeline**
   - AST parsing with tree-sitter
   - Semantic analysis and entity extraction
   - Real-time indexing to Algolia

3. **MCP Protocol Integration**
   - Session management and context preservation
   - Tool definitions for code search and analysis
   - Resource management for repositories and files

## 📊 Project Status

### ✅ Completed (MCP Foundation)

- [x] **MCP-first architecture design**
- [x] Backend infrastructure with FastAPI
- [x] Database models for repositories, files, entities
- [x] Algolia service integration foundation
- [x] Docker development environment
- [x] **Frontend implementation plan** - Comprehensive React + TypeScript strategy

### 🔄 In Progress (MCP Implementation)

- [ ] **Algolia MCP Server implementation**
- [ ] **MCP protocol tool definitions**
- [ ] **Code processing pipeline to Algolia**
- [ ] **MCP client integration testing**

### 📅 Next Steps (Frontend & MCP Completion)

- [ ] Frontend core setup + GitHub integration
- [ ] Real-time processing dashboard with WebSocket
- [ ] MCP-powered Q&A interface
- [ ] Performance optimization and production deployment

### 🎯 Frontend Implementation Phases

Core Setup & GitHub Integration

- Project setup with Vite + React + TypeScript
- GitHub URL submission form with validation
- Repository creation API integration

Processing Dashboard & Real-time Updates  

- Repository status dashboard with WebSocket updates
- Processing progress visualization
- Error handling and retry mechanisms

MCP-Powered Q&A Interface

- Chat-style interface for natural language questions
- Integration with all 5 MCP tools
- Rich code display and search results

Polish & Optimization

- Performance optimization and testing
- Responsive design refinements
- Production deployment preparation

## 🔧 MCP Integration

### Available MCP Tools

The CodeSage MCP server exposes these tools to AI models:

```typescript
// search_code: Natural language code search
// analyze_repository: Repository analysis and insights  
// explore_functions: Function and class exploration
// explain_code: Code explanation and documentation
// find_patterns: Pattern detection across codebases
```

### MCP Resources

```typescript
// repositories: Available code repositories
// files: Code files within repositories  
// entities: Functions, classes, variables
// search_indexes: Algolia search indices
```

## 📈 Performance & Scaling (MCP-Optimized)

- **MCP Protocol**: Efficient context management and tool calling
- **Algolia Search**: Millisecond response times for code queries
- **Background Processing**: Celery workers for heavy code analysis
- **Caching**: Redis for session and search result caching

## 🔒 Security (MCP-First)

- **MCP Protocol Security**: Secure tool and resource access
- **API Key Management**: Algolia credentials securely managed
- **No AI API Keys**: All AI capabilities through MCP clients
- **Input Validation**: Pydantic models for all data

## 📄 License

This project is part of the Algolia MCP Server Challenge. All rights reserved.

## 🚨 **REMEMBER: MCP-FIRST ARCHITECTURE**

**This application is built around Algolia MCP Server. All AI capabilities come through the Model Context Protocol, not direct API calls. Always refer to this when developing features.**

## 🚀 Quick Usage Guide (MCP)

```bash
# Start the MCP server
make dev

# Test MCP server connectivity
curl http://localhost:8000/mcp/capabilities

# Connect with Claude Desktop or other MCP clients
# Ask natural language questions about your code!
```

## 🧪 **Testing**

Comprehensive test suite available in the `tests/` directory:

```bash
# Run all tests
cd tests/
python3 test_endpoints.py          # Complete API test suite
python3 test_mcp_protocol.py       # MCP protocol compliance
python3 test_repository_endpoints.py  # Repository management
python3 test_search_endpoints.py   # Advanced search features
python3 test_file_endpoints.py     # File operations

# See tests/README.md for detailed testing documentation
```

## 🎉 **API Endpoints**

### **API Structure Overview:**

```tree
CodeSage MCP Server API
├── /health                          # System health check
├── /docs                           # Interactive API documentation
├── /api/v1/ai/mcp/                # Core MCP Protocol
│   ├── capabilities               # MCP server capabilities
│   ├── tools                      # List/execute MCP tools
│   └── resources                  # MCP resource management
├── /api/v1/ai/                    # Convenience MCP Tools
│   ├── search                     # Code search
│   ├── analyze                    # Repository analysis
│   ├── explore                    # Function exploration
│   ├── explain                    # Code explanation
│   ├── patterns                   # Pattern detection
│   └── status                     # MCP server status
├── /api/v1/repositories/          # Repository Management
│   ├── /                          # CRUD operations
│   ├── {id}/upload               # File uploads
│   ├── {id}/process              # Processing trigger
│   ├── {id}/status               # Processing status
│   └── {id}/stats                # Detailed statistics
├── /api/v1/search/                # Advanced Search
│   ├── /                          # Main search
│   ├── suggestions               # Search suggestions
│   ├── voice                     # Voice search
│   ├── similar                   # Similarity search
│   ├── trending                  # Trending queries
│   ├── analytics                 # Search analytics
│   └── health                    # Search service health
└── /api/v1/files/                 # File Operations
    ├── repositories/{id}         # List repository files
    ├── {id}                      # File content & metadata
    ├── {id}/entities             # Code entities
    ├── {id}/summary              # AI-generated summary
    ├── {id}/analyze              # Individual analysis
    ├── analyze/bulk              # Bulk analysis
    └── stats/repository/{id}     # Repository file stats
```
