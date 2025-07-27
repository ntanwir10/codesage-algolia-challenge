.PHONY: help build up down restart logs shell test clean start stop start-backend start-frontend

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
	@echo "  up              - Start services (backend + database)"
	@echo "  down            - Stop all services"
	@echo "  logs            - Show logs for all services"
	@echo ""
	@echo "🛠️  Development:"
	@echo "  start-backend   - Start backend development server"
	@echo "  start-frontend  - Start frontend development server"
	@echo "  health          - Check backend health and MCP status"
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
	@cp .env.example .env 2>/dev/null || echo "⚠️  .env.example not found, create .env manually"
	@echo ""
	@echo "📋 Required environment variables:"
	@echo "   ALGOLIA_APP_ID=your_app_id"
	@echo "   ALGOLIA_ADMIN_API_KEY=your_admin_key"
	@echo "   SECRET_KEY=your_secret_key"
	@echo ""
	@echo "🎯 Next: Edit .env file and run 'make start'"

# Quick start commands  
start:
	@echo "🚀 Starting CodeSage - MCP-First Code Discovery..."
	@$(MAKE) start-backend &
	@sleep 5
	@$(MAKE) start-frontend


start-backend:
	@echo "🔧 Starting CodeSage - MCP-First Code Discovery backend server..."
	@echo "📍 Make sure your virtual environment is active: source .venv/bin/activate"
	cd backend && python -m uvicorn app.main:app --reload --port 8001

start-frontend:
	@echo "🎨 Starting frontend development server..."
	cd frontend && npm run dev

stop:
	@echo "🛑 Stopping development servers..."
	@pkill -f "uvicorn app.main:app" || echo "Backend not running"
	@pkill -f "vite" || echo "Frontend not running"
	@echo "✅ Servers stopped"

# Docker commands
build:
	docker-compose build

up:
	docker-compose up -d
	@echo "✅ CodeSage - MCP-First Code Discovery is running!"
	@echo "🚀 Backend API: http://localhost:8001"
	@echo "📚 API Docs: http://localhost:8001/docs"
	@echo "🔌 MCP Endpoint: http://localhost:8001/api/v1/ai/mcp/capabilities"
	@echo ""
	@echo "💡 Test with: curl http://localhost:8001/health"

down:
	docker-compose -f deployment/docker-compose.yml down

restart:
	docker-compose -f deployment/docker-compose.yml restart

# Logs
logs:
	docker-compose -f deployment/docker-compose.yml logs -f

logs-backend:
	docker-compose -f deployment/docker-compose.yml logs -f backend

# Development  
shell:
	docker-compose -f deployment/docker-compose.yml exec backend bash

health:
	@echo "🏥 CodeSage - MCP-First Code Discovery Health Check:"
	@curl -s http://localhost:8001/health | jq . || echo "❌ Backend not responding"
	@echo ""
	@echo "🤖 MCP Capabilities:"
	@curl -s http://localhost:8001/api/v1/ai/mcp/capabilities | jq .tools || echo "❌ MCP not responding"

# Testing
test:
	@echo "🧪 Running CodeSage API tests..."
	cd backend && python -m pytest tests/ -v

test-mcp:
	@echo "🤖 Testing MCP protocol endpoints..."
	@echo "Testing capabilities..."
	@curl -s http://localhost:8001/api/v1/ai/mcp/capabilities | jq .
	@echo "Testing tools list..."
	@curl -s http://localhost:8001/api/v1/ai/mcp/tools | jq .

# Database
db-reset:
	@echo "🗄️  Resetting SQLite database..."
	rm -f backend/codesage.db 2>/dev/null || true
	rm -f codesage.db 2>/dev/null || true
	@echo "✅ SQLite database reset complete"

db-migrate:
	@echo "🔄 Running database migrations..."
	cd backend && alembic upgrade head

db-migration:
	@read -p "Enter migration message: " message; \
	cd backend && alembic revision --autogenerate -m "$$message"

# Cleanup
clean:
	docker-compose down -v
	docker system prune -f

clean-all:
	docker-compose down -v  
	docker system prune -a -f

# Production
prod-build:
	docker-compose -f docker-compose.prod.yml build

prod-up:
	docker-compose -f docker-compose.prod.yml up -d

# Status
status:
	@echo "📊 CodeSage MCP Server Status:"
	@docker-compose ps

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