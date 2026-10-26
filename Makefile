.PHONY: help setup start start-backend start-frontend stop build up down restart logs logs-backend shell health test test-mcp db-reset db-migrate db-migration clean clean-all prod-build prod-up status install-claude

COMPOSE      = docker compose -f deployment/docker-compose.yml
COMPOSE_PROD = docker compose -f deployment/docker-compose.prod.yml

# CodeSage Makefile: local development, Docker, tests, database and Claude Desktop setup.
# Run 'make help' for the list of targets.

# Default target
help:
	@echo "🏆 CodeSage - MCP-First Code Discovery - Algolia Challenge Edition"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  help            - Show this list"
	@echo "  setup           - Create backend/.env, the .venv and install frontend deps (npm ci)"
	@echo "  start           - Start both backend and frontend (recommended)"
	@echo "  stop            - Stop all development servers"
	@echo ""
	@echo "🐳 Docker Commands:"
	@echo "  build           - Build all Docker containers"
	@echo "  up              - Start services (backend + nginx/frontend on http://localhost)"
	@echo "  down            - Stop all services"
	@echo "  restart         - Restart all services"
	@echo "  logs            - Show logs for all services"
	@echo "  logs-backend    - Show backend logs only"
	@echo "  shell           - Open a shell in the backend container"
	@echo ""
	@echo "🛠️  Development:"
	@echo "  start-backend   - Start backend development server"
	@echo "  start-frontend  - Start frontend development server"
	@echo "  health          - Check backend health and MCP status"
	@echo "  install-claude  - Add the CodeSage MCP server to Claude Desktop (merges config, keeps a backup)"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  test            - Run API tests"
	@echo "  test-mcp        - Test MCP protocol endpoints"
	@echo ""
	@echo "🗄️  Database:"
	@echo "  db-reset        - Delete the local SQLite database"
	@echo "  db-migrate      - Apply Alembic migrations (alembic upgrade head)"
	@echo "  db-migration    - Autogenerate a new Alembic migration (prompts for a message)"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  clean           - Remove this project's containers, networks and volumes"
	@echo "  clean-all       - Like clean, and also remove the images it built"
	@echo "  status          - Show running containers"
	@echo ""
	@echo "🚢 Production:"
	@echo "  prod-build      - Build the production images"
	@echo "  prod-up         - Start the production stack"

# Setup development environment
setup:
	@echo "🏆 Setting up CodeSage - MCP-First Code Discovery for Algolia Challenge..."
	@test -f backend/.env || cp .env.example backend/.env
	@if [ ! -x .venv/bin/python ]; then \
		command -v uv >/dev/null || command -v python3.13 >/dev/null || { echo "❌ Python 3.13 (or uv) is required"; exit 1; }; \
		if command -v uv >/dev/null; then uv venv --python 3.13 .venv; else python3.13 -m venv .venv; fi; \
	fi
	@if command -v uv >/dev/null; then uv pip install --python .venv/bin/python -r backend/requirements-dev.txt; \
	else .venv/bin/python -m pip install -r backend/requirements-dev.txt; fi
	@command -v node >/dev/null && [ "$$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] || { echo "❌ Node.js 22 or newer is required"; exit 1; }
	@cd frontend && npm ci
	@echo ""
	@echo "📋 Edit backend/.env (these values are empty by default):"
	@echo "   ALGOLIA_APP_ID, ALGOLIA_ADMIN_API_KEY  (from the Algolia dashboard; needed for indexing and search)"
	@echo "   GITHUB_TOKEN                           (optional; raises GitHub rate limits)"
	@echo "   CODESAGE_API_KEY                       (optional for local use; required when the server listens beyond localhost (Docker))"
	@echo ""
	@echo "🎯 Next: 'make start', then 'make install-claude' for Claude Desktop"

# Quick start commands  
start:
	@echo "🚀 Starting CodeSage - MCP-First Code Discovery..."
	@$(MAKE) start-backend & pid=$$!; ok=; \
	for i in $$(seq 1 15); do \
		kill -0 $$pid 2>/dev/null || break; \
		curl -fsS http://127.0.0.1:8001/health >/dev/null 2>&1 && ok=1 && break; \
		sleep 1; \
	done; \
	if [ -z "$$ok" ]; then \
		echo "❌ The backend did not start; see its output above."; \
		pkill -P $$pid 2>/dev/null; kill $$pid 2>/dev/null; exit 1; \
	fi; \
	$(MAKE) start-frontend


start-backend:
	@echo "🔧 Starting CodeSage - MCP-First Code Discovery backend server..."
	@echo "📍 Make sure your virtual environment is active: source .venv/bin/activate"
	cd backend && ../.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

start-frontend:
	@echo "🎨 Starting frontend development server..."
	cd frontend && npm run dev

stop:
	@echo "🛑 Stopping development servers..."
	@# Only kill listeners on the dev ports, never every vite on the machine
	@pids=$$(lsof -ti tcp:8001 -sTCP:LISTEN); if [ -n "$$pids" ]; then echo "$$pids" | xargs kill; else echo "Backend not running"; fi
	@pids=$$(lsof -ti tcp:5173 -sTCP:LISTEN); if [ -n "$$pids" ]; then echo "$$pids" | xargs kill; else echo "Frontend not running"; fi
	@echo "✅ Servers stopped"

# Docker commands
build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d
	@echo "✅ CodeSage - MCP-First Code Discovery is running!"
	@echo "🌐 App (nginx): http://localhost"
	@echo "🚀 Backend API: http://localhost:8001"
	@echo "📚 API Docs: http://localhost:8001/docs"
	@echo "🔌 MCP Endpoint: http://localhost:8001/api/v1/ai/mcp/capabilities"
	@echo ""
	@echo "💡 Test with: curl http://localhost:8001/health"

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

# Logs
logs:
	$(COMPOSE) logs -f

logs-backend:
	$(COMPOSE) logs -f backend

# Development  
shell:
	$(COMPOSE) exec backend bash

health:
	@echo "🏥 CodeSage - MCP-First Code Discovery Health Check:"
	@out=$$(curl -fsS http://127.0.0.1:8001/health) && echo "$$out" | jq . || echo "❌ Backend not responding"
	@echo ""
	@echo "🤖 MCP Capabilities:"
	@out=$$(curl -fsS http://127.0.0.1:8001/api/v1/ai/mcp/capabilities) && echo "$$out" | jq .tools || echo "❌ MCP not responding"

# Testing
test:
	@echo "🧪 Running CodeSage API tests..."
	.venv/bin/python -m pytest backend/tests -v

test-mcp:
	@echo "🤖 Testing MCP protocol endpoints..."
	@echo "Testing capabilities..."
	@curl -s http://127.0.0.1:8001/api/v1/ai/mcp/capabilities | jq .
	@echo "Testing tools list..."
	@curl -s http://127.0.0.1:8001/api/v1/ai/mcp/tools | jq .

# Database
db-reset:
	@echo "🗄️  Resetting SQLite database..."
	@# Dev DB default is sqlite:///./codesage.db relative to the backend dir
	@echo "Deleting: backend/codesage.db (and -journal/-wal/-shm if present)"
	rm -f backend/codesage.db backend/codesage.db-journal backend/codesage.db-wal backend/codesage.db-shm
	@echo "✅ SQLite database reset complete"

db-migrate:
	@echo "🔄 Running database migrations..."
	cd backend && ../.venv/bin/python -m alembic upgrade head

db-migration:
	@read -p "Enter migration message: " message; \
	cd backend && ../.venv/bin/python -m alembic revision --autogenerate -m "$$message"

# Cleanup
# Scoped to this project: a host-wide `docker system prune` would also delete other projects' data
clean:
	$(COMPOSE) down -v --remove-orphans

clean-all:
	$(COMPOSE) down -v --remove-orphans --rmi local

# Production
prod-build:
	$(COMPOSE_PROD) build

prod-up:
	$(COMPOSE_PROD) up -d

# Status
status:
	@echo "📊 CodeSage MCP Server Status:"
	@$(COMPOSE) ps

# Register the MCP server with Claude Desktop (use ARGS='--dry-run' to preview)
install-claude:
	.venv/bin/python scripts/install_claude_desktop.py $(ARGS)
