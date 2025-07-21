# CodeSage Documentation

Welcome to the CodeSage documentation! This folder contains comprehensive documentation for the **CodeSage MCP Server** - an AI-powered code discovery platform built around Algolia MCP Server integration.

## 📖 Documentation Overview

### Core Architecture

- **[Architecture](./architecture.md)** - Simplified MCP-first system architecture and design decisions
- **[MCP-First Architecture](./MCP-FIRST-ARCHITECTURE.md)** - Critical reference document for MCP protocol compliance

### Development & Deployment

- **[Deployment & Costs](./deployment-and-costs.md)** - Complete deployment strategy and cost analysis
- **[Project Plan](./plan.md)** - Original project planning and requirements document

## 🎯 Quick Start

1. **Start here**: [MCP-First Architecture](./MCP-FIRST-ARCHITECTURE.md) - Understand the core principles
2. **System overview**: [Architecture](./architecture.md) - See how everything fits together
3. **Deployment**: [Deployment & Costs](./deployment-and-costs.md) - Learn deployment strategies

## 🏗️ Architecture Summary

CodeSage uses a **simplified MCP-first architecture**:

```arch
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   MCP Client    │    │   CodeSage       │    │   Algolia       │
│   (Claude/AI)   │◄──►│   MCP Server     │◄──►│   Search API    │
│                 │    │   (FastAPI)      │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                               ▲
                               ▼
                    ┌──────────────────┐
                    │   PostgreSQL     │
                    │   (Metadata)     │
                    └──────────────────┘
```

## 🚨 Critical Principles

⚠️ **MCP-First Architecture**: All AI capabilities come through MCP protocol, not direct API calls.

### Key Design Decisions

- ✅ **Lightweight**: No Redis, no Celery, no complex queuing
- ✅ **Fast**: Direct processing optimized for MCP tool responses
- ✅ **Scalable**: Stateless design for easy horizontal scaling
- ✅ **Search-Focused**: Algolia handles all heavy lifting
- ✅ **Simple**: PostgreSQL for lightweight metadata only

## 🔧 MCP Tools Available

- `search_code` - Natural language code search
- `analyze_repository` - Repository overview and stats
- `explore_functions` - Function and class discovery
- `explain_code` - Code explanation data
- `find_patterns` - Pattern detection in code
