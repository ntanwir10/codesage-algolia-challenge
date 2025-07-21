.PHONY: help build up down restart logs shell test clean

# Default target
help:
	@echo "CodeSage Development Commands:"
	@echo "  build       - Build all Docker containers"
	@echo "  up          - Start all services"
	@echo "  down        - Stop all services"
	@echo "  restart     - Restart all services"
	@echo "  logs        - Show logs for all services"
	@echo "  logs-api    - Show backend API logs"
	@echo "  logs-celery - Show Celery worker logs"
	@echo "  shell       - Open shell in backend container"
	@echo "  test        - Run tests"
	@echo "  clean       - Clean up containers and volumes"
	@echo "  setup       - Initial setup with environment file"

# Setup development environment
setup:
	@echo "Setting up CodeSage development environment..."
	@cp .env.example .env
	@echo "✅ Created .env file from template"
	@echo "⚠️  Please edit .env file with your API keys:"
	@echo "   - OPENAI_API_KEY"
	@echo "   - ALGOLIA_APP_ID, ALGOLIA_API_KEY, ALGOLIA_SEARCH_API_KEY"
	@echo "   - Update SECRET_KEY for security"

# Docker commands
build:
	docker-compose build

up:
	docker-compose up -d
	@echo "✅ CodeSage is running!"
	@echo "🚀 Backend API: http://localhost:8000"
	@echo "📚 API Docs: http://localhost:8000/docs"
	@echo "🌸 Flower (Celery): http://localhost:5555"
	@echo "🗄️  PostgreSQL: localhost:5432"
	@echo "🔴 Redis: localhost:6379"

down:
	docker-compose down

restart:
	docker-compose restart

# Logs
logs:
	docker-compose logs -f

logs-api:
	docker-compose logs -f backend

logs-celery:
	docker-compose logs -f celery

logs-postgres:
	docker-compose logs -f postgres

logs-redis:
	docker-compose logs -f redis

# Development
shell:
	docker-compose exec backend bash

shell-db:
	docker-compose exec postgres psql -U codesage -d codesage

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

test-watch:
	docker-compose exec backend pytest-watch

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
	@echo "🔍 CodeSage Service Status:"
	@docker-compose ps

health:
	@echo "🏥 Health Check:"
	@curl -s http://localhost:8000/health | jq . || echo "❌ Backend not responding"

# Quick development workflow
dev: down build up logs-api

# Install dependencies locally (for IDE support)
install-local:
	cd backend && pip install -r requirements.txt 