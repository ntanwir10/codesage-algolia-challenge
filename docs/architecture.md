# CodeSage - Simplified MCP Server Architecture

## Overview

**CodeSage is a lightweight, AI-powered code discovery platform built entirely around Algolia MCP Server integration using the Model Context Protocol (MCP).**

**⚠️ CRITICAL: This application uses MCP-first architecture. All AI capabilities come through MCP protocol, not direct API calls.**

## Simplified MCP Architecture

```arch
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   MCP Client    │    │   CodeSage       │    │   Algolia       │
│   (Claude/AI)   │◄──►│   MCP Server     │◄──►│   Search API    │
│                 │    │   (FastAPI)      │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         ▲                       ▲                       ▲
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User Natural  │    │   PostgreSQL     │    │   Search Index  │
│   Language      │    │   (Metadata)     │    │   (Code Data)   │
│   Queries       │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Component Details

### 1. MCP Client Layer

**Technology Stack:**

- Claude Desktop (primary)
- Custom MCP clients
- Any MCP-compatible AI model

**Key Features:**

- Natural language code queries
- Real-time code search responses
- Context-aware code exploration
- Fast, interactive code discovery

**MCP Integration:**

- Direct connection to CodeSage MCP Server
- Uses MCP tools for instant code search
- Maintains conversation context

### 2. CodeSage MCP Server (Core Component)

**Purpose**: Lightweight bridge between AI models and Algolia search

**Technology Stack:**

- FastAPI (Python web framework)
- PostgreSQL (lightweight metadata storage)
- Algolia Search API (primary search engine)
- Tree-sitter (code parsing when needed)

**Key Features:**

- **Fast MCP Tools**: All tools respond in < 30 seconds
- **Search-Focused**: Leverages Algolia for heavy lifting
- **Lightweight**: No background jobs or complex queues
- **Scalable**: Stateless design for easy scaling

**MCP Tools Exposed:**

- `search_code` - Natural language code search
- `analyze_repository` - Repository overview and stats
- `explore_functions` - Function and class discovery
- `explain_code` - Code explanation data
- `find_patterns` - Pattern detection in code

**MCP Resources Exposed:**

- `repositories` - Repository metadata
- `files` - File information
- `entities` - Code entities (functions, classes)
- `search_indexes` - Search index status

### 3. Data Storage Layer

**PostgreSQL Database:**

- Repository metadata
- File information
- Code entity references
- Search index status
- **No complex relational queries** - kept simple

**Algolia Search Engine:**

- Primary code search capability
- Full-text search across code
- Faceted search (language, type, repository)
- Fast autocomplete and suggestions
- **Handles all search complexity**

## Simplified Data Flow

### MCP Tool Request Flow

```text
1. AI Model calls MCP tool → CodeSage MCP Server
2. MCP Server formats search query → Algolia API
3. Algolia returns search results → MCP Server
4. MCP Server formats response → AI Model
5. AI Model processes and responds → User
```

### Repository Processing Flow

```text
1. User uploads repository → MCP Server
2. MCP Server parses code (tree-sitter) → Code entities
3. Code entities sent directly → Algolia indexing
4. Metadata stored → PostgreSQL
5. Repository ready for search → MCP tools
```

## Key Architectural Decisions

### ✅ **What We Kept:**

- **PostgreSQL**: Simple metadata storage
- **Algolia**: Powerful search capabilities
- **FastAPI**: High-performance async API
- **Tree-sitter**: Code parsing when needed
- **MCP Protocol**: Standard AI model integration

### ❌ **What We Removed:**

- **Redis**: Not needed for MCP server simplicity
- **Celery**: No background jobs, direct processing
- **Complex queuing**: MCP tools should be fast and direct
- **Heavy caching**: Algolia provides fast search
- **Background workers**: Process on-demand instead

### 🎯 **Benefits of Simplified Architecture:**

1. **Faster Development**: Less complexity to manage
2. **Easier Deployment**: Fewer services to orchestrate
3. **Better Performance**: Direct processing, no queue overhead
4. **Lower Costs**: Fewer infrastructure components
5. **MCP-Optimized**: Designed for fast AI model interactions
6. **Easier Debugging**: Simpler request flow
7. **Better Scaling**: Stateless, horizontal scaling ready

## Performance Characteristics

**MCP Tool Response Times:**

- `search_code`: < 1 second (Algolia speed)
- `analyze_repository`: < 5 seconds (database + light processing)
- `explore_functions`: < 1 second (search-based)
- `explain_code`: < 1 second (data retrieval)
- `find_patterns`: < 3 seconds (search + simple analysis)

**Throughput:**

- Concurrent MCP tool calls: 100+ per second
- Repository processing: On-demand, < 5 minutes for typical repos
- Search queries: 1000+ per second (Algolia capacity)

## Deployment Architecture

**Production Setup:**

```arch
Load Balancer → [CodeSage MCP Server Instances] → PostgreSQL Cluster
                            ↓
                     Algolia Search API
```

**Development Setup:**

```arch
Local Docker → PostgreSQL Container + FastAPI Container
                            ↓
                     Algolia Search API
```

**Scaling Strategy:**

- Horizontal scaling of MCP server instances
- PostgreSQL read replicas if needed
- Algolia handles search scaling automatically
- No complex queue management needed

This simplified architecture is **perfectly suited for MCP protocol** requirements while maintaining all the core functionality for AI-powered code discovery.
