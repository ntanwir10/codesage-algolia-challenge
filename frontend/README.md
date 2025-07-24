# CodeSage Frontend

Simple repository management interface for the CodeSage MCP-first code discovery platform.

## 🎯 Purpose

The frontend provides a **minimal interface** for repository management. The core code discovery happens through **Claude Desktop** and the MCP protocol - not through complex frontend UI.

## ✨ Features

### 🏗️ Repository Management
- **GitHub URL Submission** - Clean form for repository input
- **Repository Listing** - View submitted repositories with status
- **Status Tracking** - Visual indicators (pending, processing, completed)
- **Basic CRUD** - Create, read, delete repositories

### 🎨 Simple UI/UX  
- **React 18 + TypeScript** - Modern, type-safe development
- **TailwindCSS** - Clean, responsive design
- **Vite** - Fast development and building
- **shadcn/ui** - Consistent component library

## 🚫 What This Frontend Does NOT Do

- ❌ Complex code search interface
- ❌ WebSocket real-time updates
- ❌ Collaboration features  
- ❌ Advanced analytics dashboards
- ❌ Direct AI chat interface

**Why?** Because code discovery happens through **Claude Desktop** via MCP protocol. The frontend's job is simple repository management only.

## 🚀 Development

### Prerequisites
- Node.js 18+
- Backend running on `http://localhost:8001`

### Setup
```bash
cd frontend
npm install
npm run dev
```

### Environment Configuration
The frontend gets its configuration from the backend API. No separate `.env` file needed.

Optional environment variables:
```bash
# Only if backend runs on different URL
VITE_API_BASE_URL=http://localhost:8001/api/v1
```

### Scripts
```bash
npm run dev         # Development server
npm run build       # Production build
npm run preview     # Preview production build
npm run lint        # ESLint checking
npm run type-check  # TypeScript checking
```

## 📁 Project Structure

```
src/
├── components/
│   ├── ui/              # Basic UI components (button, card, etc.)
│   └── forms/           # Repository form components
├── pages/
│   ├── HomePage.tsx     # Repository submission
│   └── RepositoryPage.tsx # Repository list/management
├── services/
│   └── api.ts           # Backend API client
├── types/
│   └── repository.ts    # TypeScript types
└── main.tsx            # App entry point
```

## 🔌 API Integration

The frontend connects to these backend endpoints:

```typescript
// Repository Management
GET    /api/v1/repositories/        // List repositories
POST   /api/v1/repositories/        // Create repository  
GET    /api/v1/repositories/{id}    // Get repository
DELETE /api/v1/repositories/{id}    // Delete repository
```

**Note**: The frontend does NOT call MCP endpoints. Those are used by Claude Desktop directly.

## 🎨 UI Components

### Repository Form
```tsx
// Simple GitHub URL submission
<form onSubmit={handleSubmit}>
  <input 
    type="url" 
    placeholder="https://github.com/facebook/react"
    pattern="https://github\.com/.+"
  />
  <button type="submit">Submit Repository</button>
</form>
```

### Repository List
```tsx
// Basic table with status indicators
<table>
  <thead>
    <tr>
      <th>Repository</th>
      <th>Status</th>
      <th>Actions</th>
    </tr>
  </thead>
  <tbody>
    {repositories.map(repo => (
      <tr key={repo.id}>
        <td>{repo.name}</td>
        <td><StatusBadge status={repo.status} /></td>
        <td><DeleteButton onClick={() => deleteRepo(repo.id)} /></td>
      </tr>
    ))}
  </tbody>
</table>
```

## 🔧 Technical Decisions

### Why Keep It Simple?
- **MCP-first architecture** - AI discovery happens in Claude Desktop
- **Focused responsibility** - Repository management only
- **Faster development** - Less complexity means faster iteration
- **Better UX** - Users get powerful AI discovery without complex UI

### Technology Choices
- **React 18** - Modern, stable, great TypeScript support
- **TailwindCSS** - Utility-first, no complex CSS architecture needed
- **Vite** - Fast development, simple configuration
- **TypeScript** - Type safety for API integration

## 🚀 Deployment

### Development
```bash
npm run dev  # http://localhost:5173
```

### Production Build
```bash
npm run build    # Creates dist/ folder
npm run preview  # Preview production build locally
```

### Static Hosting
The built frontend is a static site that can be deployed to:
- Vercel
- Netlify  
- GitHub Pages
- Any static hosting service

Just set `VITE_API_BASE_URL` to your production backend URL.

## 🧪 Testing Strategy

### Manual Testing
1. Start backend server
2. Submit GitHub repository URL
3. Verify repository appears in list
4. Check status updates (pending → processing → completed)
5. Test delete functionality

### Integration with MCP
1. Submit repository and wait for "completed" status
2. Connect Claude Desktop to backend MCP server
3. Ask questions about the repository through Claude
4. Verify Claude can discover and analyze the code

---

**The frontend's role is simple: manage repositories so Claude Desktop can discover the code through MCP.**
