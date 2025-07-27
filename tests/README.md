# 🧪 **CodeSage - MCP-First Code Discovery: Test Suite**

This directory contains comprehensive tests for **CodeSage - MCP-First Code Discovery** API endpoints and functionality. This is the only code discovery tool built entirely around the Model Context Protocol (MCP) for seamless AI integration.

## 📁 Test Organization

Tests are now organized by category for better maintainability:

```tree
tests/
├── api/                    # API endpoint tests
│   ├── test_endpoints.py   # General API tests
│   ├── test_repository_endpoints.py
│   ├── test_search_endpoints.py
│   ├── test_file_endpoints.py
│   ├── test_realtime_flow.py
│   ├── test_rate_limiting.py
│   └── test_upload.py
├── mcp/                    # MCP protocol tests
│   ├── test_mcp_protocol.py
│   └── test_mcp_convenience_tools.py
└── postman/               # Postman collection
    ├── CodeSage_MCP_Server_API.postman_collection.json
    └── POSTMAN_COLLECTION_GUIDE.md
```

## 🚀 **Running Tests**

### **Prerequisites**

```bash
# Ensure the server is running
cd /path/to/codesage-algolia-challenge
make up

# Install required Python packages
pip3 install requests
```

### **Run Individual Test Suites**

```bash
# From project root directory
cd tests/

# 1. Complete API Test Suite (recommended first)
python3 test_endpoints.py

# 2. MCP Protocol Compliance
python3 test_mcp_protocol.py

# 3. MCP Convenience Tools
python3 test_mcp_convenience_tools.py

# 4. Repository Management
python3 test_repository_endpoints.py

# 5. Advanced Search Features
python3 test_search_endpoints.py

# 6. File Operations
python3 test_file_endpoints.py
```

### **Run All Tests (Sequential)**

```bash
# From project root
cd tests/
for test in test_*.py; do 
    echo "=== Running $test ===" 
    python3 "$test"
    echo
done
```

### **📮 Postman Collection Testing**

For **visual/GUI testing**, use the comprehensive Postman collection:

```bash
# 1. Import collection into Postman
# File: CodeSage_MCP_Server_API.postman_collection.json

# 2. Setup environment in Postman
# Variable: baseUrl = http://localhost:8000

# 3. Run collection or individual requests
# See: POSTMAN_COLLECTION_GUIDE.md for complete instructions
```

**Postman Collection Features:**

- ✅ **48 endpoints** organized in 7 logical folders
- ✅ **Ready-to-use examples** with realistic request bodies
- ✅ **Automated tests** for status codes and response times
- ✅ **Environment variables** for easy server switching
- ✅ **Complete documentation** for each endpoint

## 📊 **Test Categories**

### **🏗️ 1. Repository Management Tests**

- ✅ Repository CRUD operations
- ✅ File upload and processing
- ✅ Status monitoring and statistics
- ✅ Repository lifecycle management

### **🔍 2. Search & Discovery Tests**

- ✅ Natural language code search
- ✅ Search suggestions and autocomplete
- ✅ Voice search processing
- ✅ Similarity search and analytics
- ✅ Search index management

### **📁 3. File Operations Tests**

- ✅ File listing and content retrieval
- ✅ Entity extraction and analysis
- ✅ AI-powered file summarization
- ✅ Bulk file processing operations

### **🤖 4. MCP Protocol Tests**

- ✅ MCP server capabilities
- ✅ Tool discovery and execution
- ✅ Resource access and reading
- ✅ Protocol compliance validation

### **🔧 5. MCP Convenience Tools Tests**

- ✅ Code search via MCP
- ✅ Repository analysis tools
- ✅ Function exploration
- ✅ Code explanation and patterns
- ✅ Server status monitoring

## 🎯 **Expected Results**

### **Success Metrics**

- **Repository Management**: 100% success rate (9/9 tests)
- **MCP Protocol**: 100% compliance (5/5 endpoints)
- **Search Features**: 75%+ success rate (6-8/8 tests)
- **File Operations**: 75%+ success rate (6-8/8 tests)
- **Overall System**: 90%+ success rate

### **Performance Targets**

- **Response Times**: < 200ms for most endpoints
- **Search Performance**: < 500ms for complex queries
- **File Processing**: < 1s for individual files
- **MCP Tool Execution**: < 300ms average

## 🔧 **Test Configuration**

### **Default Settings**

- **Base URL**: `http://localhost:8000`
- **Timeout**: 30 seconds per request
- **Retry Logic**: 3 attempts for network issues
- **Output Format**: Colored console output with timestamps

### **Environment Variables**

```bash
# Optional: Override default server URL
export CODESAGE_API_URL="http://localhost:8000"

# Optional: Enable verbose logging
export CODESAGE_TEST_VERBOSE=true

# Optional: Set test timeout
export CODESAGE_TEST_TIMEOUT=60
```

## 📈 **Test Reports**

### **Console Output**

Each test provides real-time feedback with:

- ✅ Success indicators (green)
- ❌ Failure indicators (red)
- ⚠️ Warnings (yellow)
- 📊 Summary statistics
- 🕐 Execution times

### **JSON Results**

Test results are automatically saved to `test_results.json` with:

- Detailed endpoint responses
- Performance metrics
- Error messages and stack traces
- Timestamp and environment info

## 🐛 **Troubleshooting**

### **Common Issues**

1. **Connection Refused**

   ```bash
   # Ensure server is running
   make up
   # Check server health
   curl http://localhost:8000/health
   ```

2. **Empty Search Results**

   ```bash
   # Normal for empty database
   # Upload test files first:
   curl -X POST "http://localhost:8000/api/v1/repositories/" \
        -H "Content-Type: application/json" \
        -d '{"name": "test-repo", "language": "python"}'
   ```

3. **File Upload Issues**

   ```bash
   # Check file permissions and format
   # Ensure repository exists before upload
   ```

4. **MCP Protocol Errors**

   ```bash
   # Verify Algolia configuration
   # Check .env file settings
   ```

## 🔄 **Continuous Testing**

### **Pre-commit Testing**

```bash
# Run core tests before commits
cd tests/
python3 test_mcp_protocol.py
python3 test_repository_endpoints.py
```

### **CI/CD Integration**

```yaml
# Example GitHub Actions
- name: Run API Tests
  run: |
    cd tests/
    python3 test_endpoints.py
    python3 test_mcp_protocol.py
```

## 📚 **Documentation**

- **[API Documentation](../README.md#api-endpoints)**: Complete API reference
- **[MCP Architecture](../docs/MCP-FIRST-ARCHITECTURE.md)**: MCP protocol implementation
- **[Development Guide](../docs/development-roadmap.md)**: Development workflow
- **📮 [Postman Collection Guide](./POSTMAN_COLLECTION_GUIDE.md)**: Complete Postman setup and usage

## 🌐 **Testing Endpoints in Browser**

### **🚀 Interactive API Documentation**

The fastest way to test endpoints is through the browser using FastAPI's built-in interactive documentation:

**Primary Documentation (Swagger UI):**

```url
http://localhost:8000/docs
```

**Alternative Documentation (ReDoc):**

```url
http://localhost:8000/redoc
```

### **🏥 Quick Health Check**

Verify the server is running:

```url
http://localhost:8000/health
```

### **📋 Complete Testing Workflow**

#### **Step 1: Start the Server**

```bash
# From project root
make up
# OR
docker-compose up -d
```

#### **Step 2: Access Documentation**

Open `http://localhost:8000/docs` in your browser for interactive testing.

#### **Step 3: Test by Category**

##### **🏗️ Repository Management**

**Create Repository** (`POST /api/v1/repositories/`):

```json
{
  "name": "my-test-repo",
  "description": "Testing repository for API exploration",
  "language": "python",
  "url": "https://github.com/test/my-test-repo"
}
```

**Upload Files** (`POST /api/v1/repositories/{id}/upload`):

- Path Parameter: `id = 1`
- Upload any `.py`, `.js`, or `.ts` file

**Process Repository** (`POST /api/v1/repositories/{id}/process`):

- Path Parameter: `id = 1`
- Query Parameter: `force_reprocess = false`

##### **🔍 Search & Discovery**

**Basic Search** (`POST /api/v1/search/`):

```json
{
  "query": "authentication function",
  "repository_id": 1,
  "language": "python",
  "entity_type": "function"
}
```

**Search Suggestions** (`GET /api/v1/search/suggestions`):

- Query Parameters: `q = auth`, `limit = 5`

**Voice Search** (`POST /api/v1/search/voice`):

```json
{
  "voice_query": "find login functions",
  "repository_id": 1
}
```

**Similarity Search** (`POST /api/v1/search/similar`):

```json
{
  "entity_type": "function",
  "entity_id": 1,
  "threshold": 0.7,
  "limit": 5
}
```

##### **📁 File Operations**

**List Repository Files** (`GET /api/v1/files/repositories/{repository_id}`):

- Path Parameter: `repository_id = 1`
- Query Parameters: `language = python`, `limit = 10`

**Get File Content** (`GET /api/v1/files/{file_id}`):

- Path Parameter: `file_id = 1`
- Query Parameters: `include_entities = true`, `include_raw_content = true`

**File Summary** (`GET /api/v1/files/{file_id}/summary`):

- Path Parameter: `file_id = 1`
- Query Parameters: `include_entities = true`, `detail_level = brief`

##### **🤖 MCP Protocol**

**Get Capabilities** (`GET /api/v1/ai/mcp/capabilities`):

- No parameters needed

**List Tools** (`GET /api/v1/ai/mcp/tools`):

- No parameters needed

**Call MCP Tool** (`POST /api/v1/ai/mcp/tools/call`):

```json
{
  "tool_name": "search_code",
  "arguments": {
    "query": "authentication",
    "repository_id": "1"
  }
}
```

**List Resources** (`GET /api/v1/ai/mcp/resources`):

- No parameters needed

##### **🔧 MCP Convenience Tools**

**AI Search** (`POST /api/v1/ai/search`):

```json
{
  "query": "How does user authentication work?",
  "repository_id": "1",
  "include_context": true
}
```

**Repository Analysis** (`POST /api/v1/ai/analyze`):

```json
{
  "repository_id": "1",
  "analysis_type": "structure",
  "include_dependencies": true
}
```

**Function Exploration** (`POST /api/v1/ai/explore`):

```json
{
  "repository_id": "1",
  "entity_type": "function",
  "search_term": "login"
}
```

### **🎯 Recommended Testing Order**

1. **🏥 Health Check**: `GET /health`
2. **🏗️ Create Repository**: `POST /repositories/`
3. **📤 Upload Files**: `POST /repositories/{id}/upload`
4. **⚙️ Process Repository**: `POST /repositories/{id}/process`
5. **🔍 Test Search**: `POST /search/`
6. **📁 File Operations**: `GET /files/repositories/{id}`
7. **🤖 MCP Protocol**: `GET /ai/mcp/capabilities`
8. **🔧 MCP Tools**: `POST /ai/search`

### **🔧 Troubleshooting Browser Tests**

**Server Not Running:**

```bash
docker-compose up -d
curl http://localhost:8000/health
```

**Common Issues:**

- **404 Errors**: Use valid repository/file IDs from creation responses
- **422 Validation**: Check JSON format in request bodies
- **Empty Results**: Upload and process files first

**Suggested Test Data:**

- **Repository Name**: `demo-python-app`
- **Search Queries**: `"user authentication"`, `"database connection"`
- **File Types**: `.py`, `.js`, `.ts` files from your computer

### **💡 Browser Testing Tips**

1. **Use the `/docs` interface** - it provides real-time examples
2. **Start with simple endpoints** (health, capabilities) before complex ones
3. **Note the response format** for IDs to use in subsequent requests
4. **Try different parameter combinations** to understand endpoint behavior
5. **Check the response schemas** in the documentation for expected formats

## 🎉 **Contributing**

When adding new tests:

1. Follow the existing naming convention: `test_[feature]_endpoints.py`
2. Include comprehensive error handling
3. Add performance timing
4. Update this README with new test descriptions
5. Maintain 80%+ success rate targets

---

**Last Updated**: January 2024  
**Maintainer**: CodeSage Development Team  
**Test Framework**: Python 3.9+ with requests library
