# 📮 **CodeSage MCP Server - Postman Collection Guide**

## 🚀 **Quick Start**

### **1. Import the Collection**

#### **Method 1: Import File**
1. Open Postman
2. Click **"Import"** button (top left)
3. Select **"Upload Files"**
4. Choose `CodeSage_MCP_Server_API.postman_collection.json`
5. Click **"Import"**

#### **Method 2: Import from Raw JSON**
1. Open Postman
2. Click **"Import"** → **"Raw text"**
3. Copy and paste the entire JSON content from the collection file
4. Click **"Continue"** → **"Import"**

### **2. Setup Environment**

The collection uses a `{{baseUrl}}` variable. Set it up:

1. Click the **"Environment"** tab (left sidebar)
2. Create **"New Environment"**
3. Name it: `CodeSage Local`
4. Add variable:
   - **Variable**: `baseUrl`
   - **Initial Value**: `http://localhost:8000`
   - **Current Value**: `http://localhost:8000`
5. Click **"Save"**
6. Select this environment from the dropdown (top right)

### **3. Start the Server**

Before testing, ensure the CodeSage MCP Server is running:

```bash
# From project root
make up
# OR
docker-compose up -d

# Verify server is running
curl http://localhost:8000/health
```

## 📁 **Collection Structure**

The Postman collection is organized into **7 main folders**:

### **🏥 1. Health & Status**
- **Health Check**: `GET /health`

### **🏗️ 2. Repository Management (9 endpoints)**
- List Repositories
- Create Repository
- Get Repository Details
- Update Repository
- Delete Repository
- Upload Repository Files
- Process Repository
- Get Repository Status
- Get Repository Statistics

### **🔍 3. Search & Discovery (8 endpoints)**
- Advanced Code Search
- Search Suggestions
- Voice Search
- Similarity Search
- Trending Searches
- Search Analytics
- Refresh Search Index
- Search Service Health

### **📁 4. File Operations (8 endpoints)**
- List Repository Files
- Get File Content
- Get Raw File Content
- Get File Entities
- Get File Summary
- Analyze File
- Bulk Analyze Files
- Get Repository File Statistics

### **🤖 5. MCP Protocol (5 endpoints)**
- Get MCP Capabilities
- List MCP Tools
- Execute MCP Tool
- List MCP Resources
- Read MCP Resource

### **🔧 6. MCP Convenience Tools (6 endpoints)**
- AI Search (Convenience)
- Repository Analysis (Convenience)
- Function Exploration (Convenience)
- Code Explanation (Convenience)
- Pattern Detection (Convenience)
- MCP Server Status

### **🤝 7. Collaboration (9 endpoints)**
- Create Collaboration Room
- Get Collaboration Room
- List Room Participants
- Join Collaboration Room
- Leave Collaboration Room
- Update Cursor Position
- Get Room Activity
- Get Session Status
- Create Code Annotation

## 🎯 **Complete Testing Workflow**

### **Step 1: Verify System Health**
```
🏥 Health & Status → Health Check
```
**Expected**: Status 200, healthy components

### **Step 2: Create and Setup Repository**
```
🏗️ Repository Management → Create Repository
```
**Body Example**:
```json
{
  "name": "test-repo-{{$timestamp}}",
  "description": "Test repository for API exploration",
  "language": "python",
  "url": "https://github.com/test/test-repo"
}
```

### **Step 3: Upload Files**
```
🏗️ Repository Management → Upload Repository Files
```
- Set `repository_id` in path (from Step 2 response)
- Upload sample `.py`, `.js`, or `.ts` files

### **Step 4: Process Repository**
```
🏗️ Repository Management → Process Repository
```
- Set `repository_id` in path
- Set `force_reprocess=false`

### **Step 5: Test Search Functionality**
```
🔍 Search & Discovery → Advanced Code Search
```
**Body Example**:
```json
{
  "query": "function authentication",
  "repository_id": 1,
  "language": "python",
  "per_page": 10
}
```

### **Step 6: Test MCP Protocol**
```
🤖 MCP Protocol → Get MCP Capabilities
🤖 MCP Protocol → List MCP Tools
🤖 MCP Protocol → Execute MCP Tool
```

### **Step 7: Test File Operations**
```
📁 File Operations → List Repository Files
📁 File Operations → Get File Content
```

## 📋 **Request Templates & Examples**

### **Repository Creation**
```json
{
  "name": "demo-{{$randomWord}}-{{$timestamp}}",
  "description": "Demo repository for testing CodeSage API",
  "language": "python",
  "url": "https://github.com/demo/python-project"
}
```

### **Advanced Search**
```json
{
  "query": "user authentication login",
  "repository_id": 1,
  "language": "python",
  "entity_type": "function",
  "page": 0,
  "per_page": 20,
  "include_content": true,
  "similarity_threshold": 0.7
}
```

### **MCP Tool Execution**
```json
{
  "tool_name": "search_code",
  "arguments": {
    "query": "authentication",
    "repository_id": "1",
    "language": "python"
  }
}
```

### **File Analysis**
```json
{
  "force_reanalysis": false,
  "include_entities": true,
  "include_content": true
}
```

### **Bulk File Analysis**
```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force_reanalysis": false,
  "parallel_processing": true
}
```

## 🔧 **Configuration Options**

### **Environment Variables**
| Variable        | Description          | Default Value            |
| --------------- | -------------------- | ------------------------ |
| `baseUrl`       | API server URL       | `http://localhost:8000`  |
| `repository_id` | Active repository ID | `1` (set after creation) |
| `file_id`       | Active file ID       | `1` (set after upload)   |

### **Global Headers**
All requests include:
- `Accept: application/json`
- `Content-Type: application/json` (for POST/PUT)

### **Query Parameters**
Common parameters across endpoints:
- `skip` / `limit`: Pagination
- `language`: Programming language filter
- `repository_id`: Repository scope
- `include_*`: Content inclusion flags

## 🧪 **Automated Testing Features**

### **Pre-request Scripts**
- Automatic timestamp generation
- Dynamic variable setting

### **Test Scripts**
Each request includes automatic tests:
- Status code validation (200, 201, 202, 204)
- Response time check (<5000ms)
- Content-Type validation

### **Collection Variables**
- `{{$timestamp}}`: Current Unix timestamp
- `{{$randomWord}}`: Random word for unique names
- `{{baseUrl}}`: Server base URL

## 📊 **Response Examples**

### **Health Check Response**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "version": "1.0.0",
  "architecture": "MCP-first - Simplified",
  "components": {
    "database": {"status": "healthy"},
    "algolia": {"status": "healthy"},
    "mcp_server": {"status": "ready"}
  }
}
```

### **Repository Creation Response**
```json
{
  "id": 1,
  "name": "test-repo",
  "description": "Test repository",
  "language": "python",
  "status": "created",
  "created_at": "2024-01-01T00:00:00Z",
  "total_files": 0
}
```

### **Search Response**
```json
{
  "query": "authentication",
  "hits": [
    {
      "id": "entity_123",
      "title": "authenticate_user",
      "content": "def authenticate_user(username, password):",
      "language": "python",
      "entity_type": "function"
    }
  ],
  "total_hits": 1,
  "processing_time": 0.045
}
```

## 🐛 **Troubleshooting**

### **Common Issues**

#### **1. Connection Refused (Cannot reach server)**
```bash
# Check if server is running
docker-compose ps
make up

# Check health endpoint directly
curl http://localhost:8000/health
```

#### **2. 404 Not Found (Invalid IDs)**
- **Solution**: Use valid repository/file IDs from previous responses
- **Check**: Repository exists before accessing files
- **Verify**: Correct endpoint paths

#### **3. 422 Unprocessable Entity (Validation errors)**
- **Check**: Request body format and required fields
- **Verify**: Data types (strings vs numbers)
- **Ensure**: Valid enum values

#### **4. Empty Search Results**
- **Cause**: No files uploaded or processed
- **Solution**: Upload files → Process repository → Search

### **Debug Steps**

1. **Check Server Logs**:
   ```bash
   docker-compose logs backend -f
   ```

2. **Verify Database Connection**:
   ```bash
   curl http://localhost:8000/health
   ```

3. **Test Basic Endpoints First**:
   - Health Check
   - List Repositories
   - MCP Capabilities

4. **Check Request Format**:
   - Valid JSON syntax
   - Correct Content-Type headers
   - Required fields present

## 📚 **Advanced Usage**

### **Collection Runner**
1. Click **"Runner"** (top left)
2. Select **"CodeSage MCP Server API"**
3. Choose specific folders to run
4. Set iterations and delay
5. Click **"Run CodeSage MCP Server API"**

### **Monitoring & Newman**
Export and run with Newman CLI:
```bash
npm install -g newman
newman run CodeSage_MCP_Server_API.postman_collection.json \
  --environment CodeSage_Local.postman_environment.json \
  --reporters cli,html
```

### **CI/CD Integration**
```yaml
# GitHub Actions example
- name: Run API Tests
  run: |
    newman run tests/CodeSage_MCP_Server_API.postman_collection.json \
      --environment tests/environment.json \
      --reporters junit,cli
```

## 🎉 **Collection Features**

### **📋 Complete Coverage**
- ✅ **48 total endpoints** across all API categories
- ✅ **All HTTP methods**: GET, POST, PUT, DELETE
- ✅ **All parameter types**: Path, Query, Headers, Body
- ✅ **Real examples**: Ready-to-use request bodies

### **🔧 Smart Organization**
- ✅ **Logical folders** by feature area
- ✅ **Descriptive names** and documentation
- ✅ **Consistent patterns** across similar endpoints
- ✅ **Environment variables** for easy configuration

### **🧪 Testing Ready**
- ✅ **Automated validation** scripts
- ✅ **Performance monitoring** (response times)
- ✅ **Collection runner** support
- ✅ **CI/CD integration** ready

### **📖 Documentation**
- ✅ **Detailed descriptions** for each endpoint
- ✅ **Parameter explanations** and examples
- ✅ **Expected responses** and error codes
- ✅ **Usage workflows** and best practices

---

**Collection Version**: 1.0.0  
**Last Updated**: January 2024  
**Total Endpoints**: 48  
**Coverage**: 100% of CodeSage MCP Server API

**🚀 Ready to explore the CodeSage MCP Server API with Postman!** 