.PHONY: help build up down restart logs shell test clean frontend backend start stop start-backend start-frontend backend-check

# Default target
help:
	@echo "CodeSage MCP Server Development Commands:"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  start           - Start both backend and frontend (recommended)"
	@echo "  stop            - Stop all development servers"
	@echo "  start-backend   - Start backend with health checks and validation"
	@echo "  start-frontend  - Start frontend development server"
	@echo ""
	@echo "🐳 Docker Commands:"
	@echo "  build       - Build all Docker containers"
	@echo "  up          - Start all services (backend + database)"
	@echo "  down        - Stop all services"
	@echo "  restart     - Restart all services"
	@echo "  logs        - Show logs for all services"
	@echo "  logs-api    - Show backend API logs"
	@echo "  shell       - Open shell in backend container"
	@echo ""
	@echo "🛠️  Development:"
	@echo "  backend         - Start backend with enhanced startup script"
	@echo "  frontend        - Start frontend development server"
	@echo "  backend-check   - Check backend health and WebSocket status"
	@echo "  test            - Run tests"
	@echo "  setup           - Initial setup with environment files"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  clean       - Clean up containers and volumes"
	@echo "  health      - Check backend health"
	@echo "  status      - Show service status"

# Quick start commands
start:
	@echo "🚀 Starting CodeSage MCP Server (full development environment)"
	@echo ""
	@echo "Starting backend server with health checks..."
	@$(MAKE) start-backend &
	@sleep 8
	@echo ""
	@echo "Starting frontend development server..."
	@$(MAKE) start-frontend

start-backend:
	@echo "🚀 Starting backend with enhanced startup script..."
	cd backend && python start_server.py

start-frontend:
	@echo "🎨 Starting frontend development server..."
	cd frontend && npm run dev

# Stop development servers
stop:
	@echo "🛑 Stopping development servers..."
	@pkill -f "uvicorn app.main:app" || echo "Backend not running"
	@pkill -f "vite" || echo "Frontend not running"
	@echo "✅ Development servers stopped"

# Enhanced backend startup (replaces simple uvicorn command)
backend:
	@echo "🚀 Starting backend development server with validation..."
	cd backend && python start_server.py

# Backend health and status checks
backend-check:
	@echo "🔍 Checking backend service health..."
	@echo ""
	@echo "📊 Backend Health:"
	@curl -s http://localhost:8001/health | jq .status 2>/dev/null || curl -s http://localhost:8001/health || echo "❌ Backend not responding"
	@echo ""
	@echo "🔌 WebSocket Health:"
	@curl -s http://localhost:8001/api/v1/ws/health | jq 2>/dev/null || echo "❌ WebSocket service not responding"
	@echo ""
	@echo "📋 Process Status:"
	@ps aux | grep uvicorn | grep -v grep || echo "❌ No uvicorn processes found"

# Setup development environment
setup:
	@echo "Setting up CodeSage MCP Server development environment..."
	@cp .env.example .env 2>/dev/null || echo "⚠️  .env.example not found, skipping backend .env"
	@cp frontend/.env.example frontend/.env 2>/dev/null || echo "⚠️  frontend/.env.example not found, skipping frontend .env"
	@echo "✅ Created .env files from templates"
	@echo ""
	@echo "⚠️  Please edit .env file with your API keys:"
	@echo "   - ALGOLIA_APP_ID, ALGOLIA_ADMIN_API_KEY, ALGOLIA_SEARCH_API_KEY"
	@echo "   - Update SECRET_KEY for security"
	@echo ""
	@echo "🎯 Next steps:"
	@echo "   1. Edit .env files with your configuration"
	@echo "   2. Run 'make start' to start the full development environment"

# Docker commands
build:
	docker-compose build

up:
	docker-compose up -d
	@echo "✅ CodeSage MCP Server is running!"
	@echo "🚀 Backend API: http://localhost:8001"
	@echo "📚 API Docs: http://localhost:8001/docs"
	@echo "🔌 WebSocket: ws://localhost:8001/ws"
	@echo "🗄️  PostgreSQL: localhost:5432"
	@echo ""
	@echo "Frontend: Run 'make frontend' in a separate terminal"

down:
	docker-compose down

restart:
	docker-compose restart

# Logs
logs:
	docker-compose logs -f

logs-api:
	docker-compose logs -f backend

logs-postgres:
	docker-compose logs -f postgres

# Development
shell:
	docker-compose exec backend bash

shell-db:
	docker-compose exec postgres psql -U codesage -d codesage

# Frontend development
frontend:
	@echo "🎨 Starting frontend development server..."
	cd frontend && npm run dev

# Database
db-reset:
	docker-compose down
	docker volume rm codesage-algolia-challenge_postgres_data
	docker-compose up -d postgres
	@echo "⚠️  Database reset complete"

db-migrate:
	docker-compose exec backend alembic upgrade head

db-migration:
	@read -p "Enter migration message: " message; \
	docker-compose exec backend alembic revision --autogenerate -m "$$message"

# Testing
test:
	docker-compose exec backend pytest -v

test-realtime:
	@echo "🧪 Testing real-time WebSocket flow..."
	python test_realtime_flow.py

# Code quality
lint:
	docker-compose exec backend black app/
	docker-compose exec backend isort app/
	docker-compose exec backend flake8 app/

# Cleanup
clean:
	docker-compose down -v
	docker system prune -f
	docker volume prune -f

clean-all:
	docker-compose down -v
	docker system prune -a -f
	docker volume prune -f

# Production
prod-build:
	docker-compose -f docker-compose.prod.yml build

prod-up:
	docker-compose -f docker-compose.prod.yml up -d

# Status
status:
	@echo "🔍 CodeSage MCP Server Status:"
	@docker-compose ps

health:
	@echo "🏥 Health Check:"
	@curl -s http://localhost:8001/health | jq . || echo "❌ Backend not responding"

websocket-health:
	@echo "🔌 WebSocket Health Check:"
	@curl -s http://localhost:8001/api/v1/ws/health | jq . || echo "❌ WebSocket service not responding"

# Quick development workflow
dev: down build up logs-api

# Install dependencies locally (for IDE support)
install-local:
	@echo "📦 Installing backend dependencies locally..."
	cd backend && pip install -r requirements.txt
	@echo "📦 Installing frontend dependencies locally..."
	cd frontend && npm install

# Full development setup
dev-setup: setup install-local
	@echo "🎯 Development environment ready!"
	@echo "Run 'make start' to start both backend and frontend"
	@echo "Or run 'make up' for Docker-based development"