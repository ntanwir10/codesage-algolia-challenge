# 🎯 **Frontend Implementation Plan - CodeSage ALGOLIA MCP Integration**

## **📋 Architecture Overview**

The frontend will be a modern React application that seamlessly integrates with your existing ALGOLIA MCP server backend. Here's how every component will work together:

### **🔄 Complete User Flow**

1. **GitHub URL Submission** → Repository Creation → Processing → Indexing → Ready for Questions
2. **AI Questioning Interface** → MCP Tool Calls → Algolia Search → Intelligent Responses

### **🛠 Technical Stack Decision**

**Frontend Framework:**

- **React 18** with TypeScript for type safety
- **Vite** for fast development and building
- **TailwindCSS** for utility-first styling
- **shadcn/ui** for beautiful, accessible components

**Key Libraries:**

- **React Query (TanStack Query)** for server state management
- **React Hook Form** with Zod for form validation
- **WebSocket/Socket.io** for real-time updates
- **Monaco Editor** for code display (optional)
- **Framer Motion** for smooth animations

### **🏗 Detailed Component Architecture**

#### **1. Core Application Structure**

```tree
src/
├── components/           # Reusable UI components
│   ├── ui/              # shadcn components
│   ├── forms/           # Form components
│   ├── layout/          # Layout components
│   └── features/        # Feature-specific components
├── pages/               # Page components
├── services/            # API services and MCP integration
├── hooks/               # Custom React hooks
├── utils/               # Utilities and helpers
├── types/               # TypeScript type definitions
└── lib/                 # Configuration and setup
```

#### **2. Key Pages & Components**

**Main Dashboard (`/`)**

- GitHub URL input form with validation
- Repository list with status indicators
- Quick access to recent repositories

**Repository Status Page (`/repository/:id`)**

- Real-time processing status
- Progress indicators with WebSocket updates
- Processing logs and statistics

**AI Chat Interface (`/repository/:id/chat`)**

- Chat-style interface for asking questions
- MCP tool integration for code queries
- Search results display with syntax highlighting

### **🔌 Backend Integration Strategy**

#### **API Service Layer**

```typescript
class CodeSageAPI {
  // Repository Management
  async createRepository(githubUrl: string): Promise<Repository>
  async processRepository(id: number): Promise<ProcessingStatus>
  async getRepositoryStatus(id: number): Promise<RepositoryStatus>
  
  // MCP Integration
  async callMCPTool(toolName: string, args: object): Promise<MCPResponse>
  async searchCode(query: string, filters?: SearchFilters): Promise<SearchResults>
  
  // Real-time Updates
  subscribeToRepositoryUpdates(id: number, callback: (status) => void)
}
```

#### **MCP Tools Integration**

The frontend will directly call your existing MCP tools:

1. **`search_code`** - For natural language code search
2. **`analyze_repository`** - For repository overview and insights  
3. **`explore_functions`** - For function and class discovery
4. **`explain_code`** - For code explanations
5. **`find_patterns`** - For pattern detection

### **📱 User Interface Design**

#### **1. GitHub URL Submission Interface**

```typescript
interface GitHubSubmissionForm {
  // Clean, minimal form with URL validation
  // Real-time GitHub URL validation
  // Branch selection (defaults to main)
  // Optional repository description
  // Submit button with loading states
}
```

**Features:**

- URL format validation (`https://github.com/owner/repo`)
- Branch detection and selection
- Duplicate repository checking
- Clear error messaging

#### **2. Repository Processing Dashboard**

```typescript
interface ProcessingDashboard {
  // Real-time progress tracking
  // Processing stages visualization
  // File count and processing statistics
  // Estimated completion time
  // Error handling and retry options
}
```

**Real-time Status Updates:**

- "Cloning repository..."
- "Parsing code files..."
- "Extracting code entities..."
- "Indexing to Algolia..."
- "Ready for questions!"

#### **3. AI-Powered Q&A Interface**

```typescript
interface ChatInterface {
  // Chat-style message interface
  // Natural language input with suggestions
  // Rich code result display
  // Context preservation across questions
  // Export/share conversation capability
}
```

**Question Suggestions:**

- "How does authentication work in this repo?"
- "Show me all the database models"
- "What are the security vulnerabilities?"
- "Explain the main API endpoints"

### **🔄 Real-time Integration Plan**

#### **WebSocket Connection for Status Updates**

```typescript
// Real-time repository processing updates
const useRepositoryStatus = (repositoryId: number) => {
  const [status, setStatus] = useState<ProcessingStatus>()
  
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/repository/${repositoryId}`)
    ws.onmessage = (event) => {
      const update = JSON.parse(event.data)
      setStatus(update)
    }
    return () => ws.close()
  }, [repositoryId])
  
  return status
}
```

#### **MCP Tool Integration Hooks**

```typescript
// Custom hook for MCP tool calls
const useMCPTool = () => {
  return useMutation({
    mutationFn: async ({ tool, args }: MCPToolCall) => {
      return api.callMCPTool(tool, args)
    },
    onSuccess: (data) => {
      // Handle successful tool response
    }
  })
}
```

### **🎨 UI/UX Design Principles**

#### **Design System with shadcn/ui**

- **Primary Colors:** Blue gradient for tech feel
- **Accent Colors:** Green for success, Red for errors
- **Typography:** Inter font for readability
- **Spacing:** Consistent 8px grid system

#### **Component Library:**

- `<Button>` - Various sizes and variants
- `<Input>` - With validation states
- `<Card>` - For repository and result display
- `<Badge>` - For status indicators
- `<Progress>` - For processing status
- `<Dialog>` - For modals and confirmations

#### **Responsive Design:**

- Mobile-first approach
- Breakpoints: `sm: 640px`, `md: 768px`, `lg: 1024px`, `xl: 1280px`
- Optimized for both desktop and mobile usage

### **⚡ Performance Optimization**

#### **Loading Strategies:**

- Lazy loading for pages and heavy components
- React Query for caching API responses
- Optimistic updates for better UX
- Skeleton loaders for better perceived performance

#### **Bundle Optimization:**

- Code splitting by route
- Tree shaking for unused code elimination
- Image optimization and lazy loading
- Service worker for caching (optional)

### **🔒 Error Handling & Validation**

#### **Form Validation:**

```typescript
const githubUrlSchema = z.object({
  url: z.string()
    .url("Must be a valid URL")
    .regex(/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/, "Must be a GitHub repository URL"),
  branch: z.string().min(1, "Branch is required").default("main"),
  description: z.string().optional()
})
```

#### **API Error Handling:**

- Retry mechanisms for failed requests
- User-friendly error messages
- Fallback states for network issues
- Error boundary components for React errors

### **📊 State Management Strategy**

#### **Server State:** React Query

- Repository data caching
- Background refetching
- Optimistic updates
- Error and loading states

#### **Client State:** React hooks + Context

- User preferences
- UI state (modals, sidebars)
- Form state management
- Theme and appearance settings

### **🚀 Development Workflow**

#### **Project Setup:**

1. Vite + React + TypeScript template
2. shadcn/ui initialization
3. TailwindCSS configuration
4. ESLint + Prettier setup
5. React Query and routing setup

#### **Environment Configuration:**

```typescript
// Environment variables
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
VITE_ENABLE_DEV_TOOLS=true
```

### **🧪 Testing Strategy**

#### **Testing Stack:**

- **Vitest** for unit testing
- **React Testing Library** for component testing
- **Mock Service Worker (MSW)** for API mocking
- **Playwright** for E2E testing (optional)

#### **Test Coverage:**

- Form validation logic
- API integration functions
- Component rendering and interactions
- Error boundary functionality

### **📈 Monitoring & Analytics**

#### **Performance Monitoring:**

- Web Vitals tracking
- Bundle size monitoring
- API response time tracking
- User interaction analytics

#### **Error Tracking:**

- Error boundary integration
- API error logging
- User feedback collection
- Performance issue detection

## **🔌 Detailed Endpoint Integration**

### **Repository Management Endpoints**

#### **Create Repository**

```typescript
POST /api/v1/repositories/
{
  "name": "repository-name",
  "description": "Repository description", 
  "url": "https://github.com/owner/repo",
  "branch": "main",
  "language": "typescript"
}
```

#### **Process Repository**

```typescript
POST /api/v1/repositories/{id}/process
{
  "force_reprocess": false
}
```

#### **Get Repository Status**

```typescript
GET /api/v1/repositories/{id}/status
Response: {
  "repository_id": 1,
  "status": "processing",
  "message": "Repository processing started",
  "processing_progress": 45.0,
  "algolia_indexed": false,
  "mcp_ready": false
}
```

### **MCP Tool Integration Endpoints**

#### **Call MCP Tool**

```typescript
POST /api/v1/ai/mcp/tools/call
{
  "tool_name": "search_code",
  "arguments": {
    "query": "authentication functions",
    "repository_id": "1",
    "language": "python"
  }
}
```

#### **Available MCP Tools**

```typescript
GET /api/v1/ai/mcp/tools
Response: {
  "tools": [
    {
      "name": "search_code",
      "description": "Search code using natural language",
      "parameters": {...}
    },
    {
      "name": "analyze_repository", 
      "description": "Analyze repository structure",
      "parameters": {...}
    }
  ]
}
```

### **Search Endpoints**

#### **Advanced Search**

```typescript
POST /api/v1/search/
{
  "query": "user authentication",
  "repository_id": 1,
  "language": "python",
  "entity_type": "function",
  "page": 0,
  "per_page": 20
}
```

## **🎯 Implementation Phases**

### **Core Setup & GitHub Integration**

- ✅ Project setup with Vite + React + TypeScript
- ✅ Basic routing and layout structure
- ✅ shadcn/ui component library setup
- ✅ GitHub URL submission form with validation
- ✅ Repository creation API integration
- ✅ Basic error handling and loading states

**Deliverables:**

- Working GitHub URL submission form
- Repository creation functionality
- Basic navigation and layout

### **Processing Dashboard & Real-time Updates**

- ✅ Repository status dashboard with real-time updates
- ✅ WebSocket integration for live progress tracking
- ✅ Processing progress visualization components
- ✅ Repository list with status indicators
- ✅ Error handling and retry mechanisms
- ✅ Responsive design implementation

**Deliverables:**

- Real-time repository processing dashboard
- Live status updates via WebSocket
- Comprehensive error handling

### **MCP-Powered Q&A Interface**

- ✅ Chat-style interface design and implementation
- ✅ MCP tool integration for all available tools
- ✅ Search results display with syntax highlighting
- ✅ Conversation history and context preservation
- ✅ Question suggestions and auto-complete
- ✅ Export and share conversation functionality

**Deliverables:**

- Fully functional AI chat interface
- Integration with all MCP tools
- Rich code display and search results

### **Polish & Optimization**

- ✅ Performance optimization and code splitting
- ✅ Comprehensive testing suite
- ✅ Accessibility improvements
- ✅ Documentation and user guides
- ✅ Deployment configuration
- ✅ Analytics and monitoring setup

**Deliverables:**

- Production-ready application
- Complete test coverage
- Deployment documentation

## **🚀 Getting Started**

### **Prerequisites**

- Node.js 18+
- npm or yarn package manager
- Access to the CodeSage MCP server API

### **Initial Setup Commands**

```bash
# Create new Vite React TypeScript project
npm create vite@latest codesage-frontend -- --template react-ts

# Navigate to project directory
cd codesage-frontend

# Install dependencies
npm install

# Install additional dependencies
npm install @tanstack/react-query @hookform/react-hook-form zod
npm install @radix-ui/react-slot class-variance-authority clsx tailwind-merge
npm install lucide-react framer-motion

# Setup shadcn/ui
npx shadcn-ui@latest init

# Start development server
npm run dev
```

### **Project Structure Creation**

```bash
# Create directory structure
mkdir -p src/{components/{ui,forms,layout,features},pages,services,hooks,utils,types,lib}

# Create initial files
touch src/services/api.ts
touch src/services/websocket.ts  
touch src/types/repository.ts
touch src/types/mcp.ts
touch src/hooks/useRepository.ts
touch src/hooks/useMCPTool.ts
```

## **🔧 Technical Implementation Details**

### **API Client Setup**

```typescript
// src/services/api.ts
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
})

export class CodeSageAPI {
  async createRepository(data: CreateRepositoryRequest): Promise<Repository> {
    const response = await api.post('/api/v1/repositories/', data)
    return response.data
  }

  async processRepository(id: number): Promise<ProcessingStatus> {
    const response = await api.post(`/api/v1/repositories/${id}/process`)
    return response.data
  }

  async getRepositoryStatus(id: number): Promise<RepositoryStatus> {
    const response = await api.get(`/api/v1/repositories/${id}/status`)
    return response.data
  }

  async callMCPTool(toolName: string, args: object): Promise<MCPResponse> {
    const response = await api.post('/api/v1/ai/mcp/tools/call', {
      tool_name: toolName,
      arguments: args
    })
    return response.data
  }
}
```

### **WebSocket Integration**

```typescript
// src/services/websocket.ts
export class WebSocketService {
  private ws: WebSocket | null = null
  private subscribers: Map<string, (data: any) => void> = new Map()

  connect() {
    const wsUrl = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'
    this.ws = new WebSocket(`${wsUrl}/ws`)
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      const subscriber = this.subscribers.get(data.type)
      if (subscriber) {
        subscriber(data)
      }
    }
  }

  subscribe(type: string, callback: (data: any) => void) {
    this.subscribers.set(type, callback)
  }

  unsubscribe(type: string) {
    this.subscribers.delete(type)
  }
}
```

### **Type Definitions**

```typescript
// src/types/repository.ts
export interface Repository {
  id: number
  name: string
  description?: string
  url?: string
  branch: string
  language?: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  total_files: number
  processed_files: number
  created_at: string
  updated_at?: string
}

export interface CreateRepositoryRequest {
  name: string
  description?: string
  url: string
  branch?: string
  language?: string
}

export interface ProcessingStatus {
  repository_id: number
  status: string
  message: string
  processing_progress?: number
  algolia_indexed?: boolean
  mcp_ready?: boolean
}
```

### **React Query Setup**

```typescript
// src/lib/queryClient.ts
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      cacheTime: 1000 * 60 * 10, // 10 minutes
    },
  },
})
```
