# CodeSage Technical Architecture

**Built for the [Algolia MCP Server Challenge](https://dev.to/challenges/algolia-2025-07-09)** 🏆

## 🎯 System Overview

CodeSage is a **MCP-first code discovery platform** that transforms GitHub repositories into AI-searchable knowledge bases through the Model Context Protocol.

## 📊 Complete Data Flow Architecture

```arch_flow
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CODESAGE ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │   Frontend  │───▶│   Backend    │───▶│   Algolia   │    │   GitHub    │ │
│  │   (Simple)  │    │ (Processing) │    │  (Search)   │◀───│     API     │ │
│  └─────────────┘    └──────────────┘    └─────────────┘    └─────────────┘ │
│                              │                                             │
│                              ▼                                             │
│                     ┌──────────────┐    ┌─────────────┐                   │
│                     │     MCP      │───▶│   Claude    │                   │
│                     │   Protocol   │    │  Desktop    │                   │
│                     └──────────────┘    └─────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 🔄 Processing Pipeline

### 1. Repository Submission Flow

```flow
User Input → Frontend → POST /repositories/ → Backend
    ↓
Database Record (status: pending)
    ↓
Background Processing Triggered
    ↓
GitHub API Integration
    ↓
File Parsing & Analysis
    ↓
Algolia Indexing
    ↓
Status Update (status: completed)
```

### 2. Code Discovery Flow

```flow
Claude Desktop User Query
    ↓
MCP Protocol Call
    ↓
POST /api/v1/ai/mcp/tools/call
    ↓
MCP Tool Execution
    ↓
Algolia Search Query
    ↓
Search Results
    ↓
Formatted Response
    ↓
Claude Desktop Display
```

## 🏗 System Components

### Backend (FastAPI)

**Location**: `backend/app/`

**Core Services**:

- `repository_service.py` - Repository CRUD and processing logic
- `mcp_server.py` - MCP protocol implementation
- `ai_service.py` - MCP tools implementation
- `algolia_service.py` - Search indexing and querying
- `security_service.py` - Rate limiting and validation

**Database Models**:

- `Repository` - Repository metadata and status
- `CodeFile` - Individual file records
- `CodeEntity` - Functions, classes, imports extracted from files

**API Endpoints**:

```python
# Repository Management
GET    /api/v1/repositories/        # List repositories
POST   /api/v1/repositories/        # Create repository  
GET    /api/v1/repositories/{id}    # Get repository
DELETE /api/v1/repositories/{id}    # Delete repository

# MCP Protocol
GET    /api/v1/ai/mcp/capabilities     # MCP server capabilities
GET    /api/v1/ai/mcp/tools           # List MCP tools
POST   /api/v1/ai/mcp/tools/call      # Execute MCP tool
GET    /api/v1/ai/mcp/resources/read  # Read MCP resource
```

### Frontend (React + TypeScript)

**Location**: `frontend/src/`

**Purpose**: Simple repository management interface

- Repository submission form
- Repository list with status
- Basic CRUD operations
- **No complex search UI** - AI discovery happens through Claude Desktop

**Key Components**:

- Repository form with GitHub URL validation
- Status indicators (pending, processing, completed)
- Simple table view for repository management

### MCP Tools Implementation

**Location**: `backend/app/services/ai_service.py`

**Available Tools**:

1. **`search_code`**

   ```python
   # Natural language code search
   query: str = "React hooks"
   repository?: str = "react"
   language?: str = "typescript"
   entity_type?: str = "function"
   ```

2. **`analyze_repository`**

   ```python
   # Repository overview and insights
   repository_id: str = "123"
   analysis_type: str = "overview" | "security" | "performance"
   ```

3. **`explore_functions`**

   ```python
   # Function discovery and relationships
   entity_name?: str = "useState"
   repository?: str = "react"
   similarity_search: bool = true
   ```

4. **`explain_code`**

   ```python
   # Code explanation and documentation
   code_snippet: str = "function code here"
   context?: str = "additional context"
   detail_level: str = "brief" | "detailed"
   ```

5. **`find_patterns`**

   ```python
   # Pattern detection across codebase
   repository_id: str = "123"
   pattern_type: str = "security" | "performance" | "architecture"
   ```

## 🔍 Repository Processing Details

### GitHub Integration

```python
# Planned implementation in repository_service.py
async def process_repository_files(self, repository: Repository):
    # 1. GitHub API: Clone/download repository
    github_client = GitHubClient()
    files = await github_client.get_repository_files(repository.url)
    
    # 2. Parse code files
    parser = CodeParser()
    entities = []
    for file in files:
        if file.is_code_file():
            parsed = await parser.extract_entities(file)
            entities.extend(parsed)
    
    # 3. Index in Algolia
    algolia_service = AlgoliaService()
    await algolia_service.batch_index_entities(entities)
    
    # 4. Update repository status
    repository.status = "completed"
    repository.total_files = len(files)
    repository.processed_files = len(files)
```

### Code Entity Structure

```python
# Algolia document structure
{
    "objectID": "unique_entity_id",
    "repository_id": 123,
    "file_path": "src/components/Button.tsx",
    "entity_type": "function",
    "entity_name": "Button",
    "description": "React button component",
    "parameters": ["props: ButtonProps"],
    "return_type": "JSX.Element",
    "line_start": 45,
    "line_end": 78,
    "language": "typescript",
    "imports": ["React", "styled-components"],
    "content": "function Button(props: ButtonProps) { ... }"
}
```

## 🎯 MCP Protocol Implementation

### Server Configuration

```python
# backend/app/core/config.py
class Settings(BaseSettings):
    mcp_server_name: str = "codesage"
    mcp_server_version: str = "1.0.0"
    mcp_server_description: str = "AI-powered code discovery"
    
    mcp_tools_enabled: List[str] = [
        "search_code",
        "analyze_repository",
        "explore_functions", 
        "explain_code",
        "find_patterns",
    ]
```

### Tool Execution Flow

```python
# backend/app/services/mcp_server.py
async def call_tool(self, tool_name: str, arguments: dict):
    if tool_name == "search_code":
        query = arguments.get("query")
        results = await self.algolia_service.search(query)
        return self.format_search_results(results)
    
    elif tool_name == "analyze_repository":
        repo_id = arguments.get("repository_id")
        analysis = await self.ai_service.analyze_repository(repo_id)
        return analysis
    
    # ... other tools
```

## 🗄 Database Schema

### Repository Table

```sql
CREATE TABLE repositories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(500) NOT NULL UNIQUE,
    description TEXT,
    language VARCHAR(50),
    status VARCHAR(50) DEFAULT 'pending',
    total_files INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Code Files Table

```sql
CREATE TABLE code_files (
    id SERIAL PRIMARY KEY,
    repository_id INTEGER REFERENCES repositories(id),
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    language VARCHAR(50),
    content TEXT,
    line_count INTEGER,
    is_analyzed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Code Entities Table

```sql
CREATE TABLE code_entities (
    id SERIAL PRIMARY KEY,
    code_file_id INTEGER REFERENCES code_files(id),
    entity_type VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    line_start INTEGER,
    line_end INTEGER,
    parameters JSON,
    return_type VARCHAR(255),
    algolia_object_id VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 🔧 Configuration Management

### Single Environment File

**Location**: `.env` (project root)

```bash
# Essential variables only
SECRET_KEY=your-secret-key
ALGOLIA_APP_ID=your-app-id
ALGOLIA_ADMIN_API_KEY=your-admin-key
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=sqlite:///./codesage.db
```

### Backend Configuration Loading

```python
# backend/app/core/config.py
class Config:
    env_file = "../.env"  # Load from project root
    case_sensitive = False
    extra = "ignore"
```

## 🚀 Deployment Architecture

### Development

```bash
# Simple local development
cd backend && python -m uvicorn app.main:app --reload --port 8001
cd frontend && npm run dev
```

### Production (Planned)

```yaml
# docker-compose.prod.yml
services:
  backend:
    build: ./backend
    environment:
      - DATABASE_URL=postgresql://...
      - ALGOLIA_APP_ID=${ALGOLIA_APP_ID}
    
  frontend:
    build: ./frontend
    environment:
      - VITE_API_BASE_URL=https://api.codesage.com
    
  postgres:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

## 🔒 Security Considerations

### Rate Limiting

```python
# Simplified for MCP-first architecture
@rate_limit_default  # 100/minute for repository management
@rate_limit_ai       # 30/minute for MCP tool calls
```

### Input Validation

```python
# Pydantic schemas for all API inputs
class RepositoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., regex=r'^https://github\.com/.+')
    description: Optional[str] = None
```

### Environment Security

- API keys stored in environment variables
- No sensitive data in code
- Database credentials properly managed
- CORS configured for known origins

## 📈 Performance Characteristics

### Response Times (Target)

- Repository creation: < 100ms
- MCP tool calls: < 500ms
- Algolia search: < 50ms
- Repository processing: 1-5 minutes (background)

### Scaling Considerations

- Stateless FastAPI backend (horizontal scaling)
- Algolia handles search scaling
- Database connection pooling
- Async processing for repository analysis

## 🧪 Testing Strategy

### Unit Tests

- Individual service testing
- MCP tool functionality
- Database operations
- Algolia integration

### Integration Tests

- Complete repository processing flow
- MCP protocol compliance
- API endpoint testing
- Error handling scenarios

### Claude Desktop Testing

- Manual MCP connection testing
- Natural language query validation
- Tool response format verification
- End-to-end user experience testing

## 🔄 Future Enhancements

### Phase 2 (Post-MVP)

- Multiple repository support in single query
- Advanced code relationship mapping
- Custom MCP tool creation
- Performance analytics

### Phase 3 (Advanced)

- Real-time collaborative discovery
- Custom AI model integration
- Enterprise authentication
- Advanced security scanning

---

This architecture supports the core CodeSage mission: **transforming repositories into AI-discoverable knowledge through clean MCP protocol integration**.
