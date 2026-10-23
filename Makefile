.PHONY: help build up down restart logs shell test clean clean-all start stop start-backend start-frontend prod-build prod-up status install-claude

COMPOSE      = docker compose -f deployment/docker-compose.yml
COMPOSE_PROD = docker compose -f deployment/docker-compose.prod.yml

# CodeSage - MCP-First Code Discovery Makefile
# 
# This project is built entirely around the Model Context Protocol (MCP)
# for seamless AI integration with Claude Desktop and other MCP clients.
# 
# Default target
help:
	@echo "🏆 CodeSage - MCP-First Code Discovery - Algolia Challenge Edition"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  setup           - Initial setup with environment files"
	@echo "  start           - Start both backend and frontend (recommended)"
	@echo "  stop            - Stop all development servers"
	@echo ""
	@echo "🐳 Docker Commands:"
	@echo "  build           - Build all Docker containers"
	@echo "  up              - Start services (backend + nginx/frontend on http://localhost)"
	@echo "  down            - Stop all services"
	@echo "  logs            - Show logs for all services"
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
	@echo "🧹 Maintenance:"
	@echo "  clean           - Clean up containers and volumes"

# Setup development environment
setup:
	@echo "🏆 Setting up CodeSage - MCP-First Code Discovery for Algolia Challenge..."
	@test -f backend/.env || cp .env.example backend/.env
	@if [ ! -x .venv/bin/python ]; then \
		if command -v uv >/dev/null; then uv venv --python 3.13 .venv; else python3.13 -m venv .venv; fi; \
	fi
	@if command -v uv >/dev/null; then uv pip install --python .venv/bin/python -r backend/requirements-dev.txt; \
	else .venv/bin/python -m pip install -r backend/requirements-dev.txt; fi
	@cd frontend && npm ci
	@echo ""
	@echo "📋 Edit backend/.env and set at least:"
	@echo "   ALGOLIA_APP_ID, ALGOLIA_ADMIN_API_KEY  (Algolia dashboard)"
	@echo "   GITHUB_TOKEN                           (optional; raises GitHub rate limits)"
	@echo "   CODESAGE_API_KEY                       (required unless bound to 127.0.0.1)"
	@echo ""
	@echo "🎯 Next: 'make start', then 'make install-claude' for Claude Desktop"

# Quick start commands  
start:
	@echo "🚀 Starting CodeSage - MCP-First Code Discovery..."
	@$(MAKE) start-backend &
	@sleep 5
	@$(MAKE) start-frontend


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
	@curl -s http://localhost:8001/health | jq . || echo "❌ Backend not responding"
	@echo ""
	@echo "🤖 MCP Capabilities:"
	@curl -s http://localhost:8001/api/v1/ai/mcp/capabilities | jq .tools || echo "❌ MCP not responding"

# Testing
test:
	@echo "🧪 Running CodeSage API tests..."
	.venv/bin/python -m pytest backend/tests -v

test-mcp:
	@echo "🤖 Testing MCP protocol endpoints..."
	@echo "Testing capabilities..."
	@curl -s http://localhost:8001/api/v1/ai/mcp/capabilities | jq .
	@echo "Testing tools list..."
	@curl -s http://localhost:8001/api/v1/ai/mcp/tools | jq .

# Database
db-reset:
	@echo "🗄️  Resetting SQLite database..."
	@# Dev DB default is sqlite:///./codesage.db relative to the backend dir
	@echo "Deleting: backend/codesage.db (and -journal/-wal/-shm if present)"
	rm -f backend/codesage.db backend/codesage.db-journal backend/codesage.db-wal backend/codesage.db-shm
	@echo "✅ SQLite database reset complete"

db-migrate:
	@echo "🔄 Running database migrations..."
	cd backend && alembic upgrade head

db-migration:
	@read -p "Enter migration message: " message; \
	cd backend && alembic revision --autogenerate -m "$$message"

# Cleanup
clean:
	$(COMPOSE) down -v
	docker system prune -f

clean-all:
	$(COMPOSE) down -v
	docker system prune -a -f

# Production
prod-build:
	$(COMPOSE_PROD) build

prod-up:
	$(COMPOSE_PROD) up -d

# Status
status:
	@echo "📊 CodeSage MCP Server Status:"
	@$(COMPOSE) ps

# Install dependencies locally (for IDE support)
install-local:
	@echo "📦 Installing dependencies locally..."
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

# Challenge workflow
challenge-setup: setup install-local
	@echo "🏆 Algolia MCP Server Challenge Setup Complete!"
	@echo ""  
	@echo "🎯 Ready for the challenge:"
	@echo "   1. Edit .env with your Algolia credentials"
	@echo "   2. Run 'make start' to start development"
	@echo "   3. Submit repository: POST /api/v1/repositories/"
	@echo "   4. Connect Claude Desktop to MCP endpoint"
	@echo ""
	@echo "🔗 Challenge: https://dev.to/challenges/algolia-2025-07-09"

# Register the MCP server with Claude Desktop (use ARGS='--dry-run' to preview)
install-claude:
	.venv/bin/python scripts/install_claude_desktop.py $(ARGS)
