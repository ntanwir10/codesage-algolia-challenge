# 🚨 CRITICAL: MCP-FIRST ARCHITECTURE REFERENCE

**⚠️ READ THIS BEFORE ANY DEVELOPMENT ⚠️**

This document must be referenced during all development to ensure CodeSage remains a true **MCP-first application**.

## 🎯 Core Principle

**CodeSage is built ENTIRELY around Algolia MCP Server integration using the Model Context Protocol (MCP). ALL AI capabilities come through MCP protocol, NOT direct API calls.**

## 🚫 FORBIDDEN PRACTICES

### ❌ DO NOT:
- Add OpenAI API dependencies or direct AI API calls
- Create traditional chat endpoints with direct LLM integration
- Build custom AI conversation logic outside MCP protocol
- Add sentence-transformers or other AI/ML libraries for direct use
- Create endpoints that bypass MCP protocol for AI features

### ✅ DO:
- Use MCP tools for all AI functionality
- Connect AI models through MCP clients (Claude Desktop, etc.)
- Build code processing pipelines that feed Algolia search
- Create MCP-compliant tools and resources
- Focus on search indexing and data preparation

## 📐 Architecture Pattern

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   MCP Client    │    │   CodeSage       │    │   Algolia       │
│   (Claude/GPT)  │◄──►│   MCP Server     │◄──►│   Search API    │
│                 │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**NOT:**
```
User ↔ Frontend ↔ Backend ↔ OpenAI API ❌
```

**CORRECT:**
```
User ↔ AI Model ↔ MCP Client ↔ CodeSage MCP Server ↔ Algolia Search ✅
```

## 🛠 Implementation Guidelines

### MCP Tools (app/services/ai_service.py → MCPToolsService)
- `search_code()` - Natural language code search via Algolia
- `analyze_repository()` - Repository insights from Algolia data
- `explore_functions()` - Function/class exploration
- `explain_code()` - Structural analysis (AI explanation comes from MCP client)
- `find_patterns()` - Pattern detection via search

### MCP Resources (app/services/mcp_server.py → MCPResourcesService)
- `codesage://repositories` - Available repositories
- `codesage://files` - Code files within repositories
- `codesage://entities` - Functions, classes, variables
- `codesage://search_indexes` - Algolia index status

### API Endpoints (app/api/v1/endpoints/ai.py)
- `/mcp/capabilities` - MCP server capabilities
- `/mcp/tools` - List available MCP tools
- `/mcp/tools/call` - Execute MCP tool
- `/mcp/resources` - List MCP resources
- `/mcp/resources/read` - Read MCP resource

## 🔧 Required Dependencies

### ✅ ALLOWED:
```python
# MCP and search
mcp==1.0.0
algoliasearch==3.0.0

# Code parsing (non-AI)
tree-sitter==0.20.4
tree-sitter-python==0.20.4
# ... other tree-sitter languages

# Backend infrastructure
fastapi==0.104.1
sqlalchemy==2.0.23
redis==5.0.1
celery==5.3.4
```

### ❌ FORBIDDEN:
```python
# Direct AI APIs
openai==1.3.7          # ❌ NO!
anthropic==0.x.x       # ❌ NO!
sentence-transformers  # ❌ NO!
langchain             # ❌ NO!
```

## 📝 Configuration Requirements

### Environment Variables (.env)
```bash
# MINIMAL REQUIRED CONFIGURATION - Only 3 variables needed!
SECRET_KEY=your-secure-secret-key-here
ALGOLIA_APP_ID=your-algolia-app-id
ALGOLIA_ADMIN_API_KEY=your-algolia-admin-api-key

# DEVELOPMENT SETTINGS (optional)
ENVIRONMENT=development
DEBUG=true

# Docker defaults (uncomment only if you need to override)
# DATABASE_URL=postgresql://codesage:codesage123@postgres:5432/codesage
# REDIS_URL=redis://redis:6379/0
# MCP_SERVER_HOST=0.0.0.0
# MCP_SERVER_PORT=8000
```

**Everything else has sensible defaults!** No need for 50+ environment variables.

### Settings Validation (app/core/config.py)
```python
@field_validator("algolia_admin_api_key")
@classmethod
def validate_algolia_admin_api_key(cls, v: Optional[str]) -> Optional[str]:
    """Validate Algolia admin API key is provided for MCP server"""
    if v is None:
        raise ValueError("Algolia Admin API Key is required for MCP server functionality")
    return v
```

## 🔌 MCP Client Setup

### Claude Desktop Configuration
```json
// claude_desktop_config.json
{
  "mcpServers": {
    "codesage": {
      "command": "python",
      "args": ["-m", "codesage_mcp_server"],
      "env": {
        "ALGOLIA_APP_ID": "your_app_id",
        "ALGOLIA_ADMIN_API_KEY": "your_admin_api_key",
        "MCP_SERVER_URL": "http://localhost:8000"
      }
    }
  }
}
```

### Usage Example
```
User asks Claude: "How does authentication work in this repository?"
Claude → MCP Client → CodeSage MCP Server → search_code() → Algolia Search → Results → Claude → User
```

## 🚨 CODE REVIEW CHECKLIST

Before merging any code, verify:

- [ ] No direct OpenAI/Anthropic API calls
- [ ] No AI/ML libraries for direct use
- [ ] All AI functionality goes through MCP tools
- [ ] New features implement MCP protocol correctly
- [ ] Configuration follows MCP-first pattern
- [ ] Documentation mentions MCP protocol
- [ ] Tests validate MCP tool functionality

## 🔍 How to Verify MCP Compliance

### ✅ GOOD - MCP Tool Implementation:
```python
async def search_code(self, query: str, repository: Optional[str] = None) -> Dict[str, Any]:
    """MCP Tool: Search code using natural language queries"""
    response = await self.algolia_service.search(query=query, filters=filters)
    return {
        "tool": "search_code",
        "results": response.get("hits", []),
        "total_hits": response.get("nbHits", 0)
    }
```

### ❌ BAD - Direct AI Integration:
```python
async def analyze_code(self, code: str) -> str:
    """❌ FORBIDDEN - Direct AI call"""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)  # ❌ NO!
    response = client.chat.completions.create(...)    # ❌ NO!
    return response.choices[0].message.content        # ❌ NO!
```

## 📊 Success Metrics

### MCP-First Success Indicators:
- ✅ All AI features work through Claude Desktop MCP client
- ✅ No direct AI API costs (only Algolia search costs)
- ✅ Natural language code queries work via MCP protocol
- ✅ AI models can call MCP tools successfully
- ✅ Search results come from Algolia, AI insights from MCP client

### Warning Signs:
- ❌ Direct OpenAI/Anthropic bills
- ❌ AI conversation endpoints in FastAPI
- ❌ Custom LLM integration code
- ❌ Sentence transformers or embeddings generation

## 🎯 Remember

**The goal is to create the BEST MCP server for code discovery, not another AI chatbot. The AI intelligence comes from MCP clients like Claude Desktop connecting to our MCP server.**

---

## 🚨 FINAL WARNING

**If you see ANY direct AI API integration being added to this codebase, STOP and refer back to this document. CodeSage is MCP-first, period.**

This application's value comes from:
1. **Superior code indexing and search** (via Algolia)
2. **Excellent MCP tool implementation** (for AI model integration)  
3. **Rich code analysis pipeline** (feeding search index)

**NOT** from being another OpenAI wrapper.