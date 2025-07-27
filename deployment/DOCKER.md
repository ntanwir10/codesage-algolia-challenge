# 🐳 CodeSage - MCP-First Code Discovery: Docker Deployment Guide

> **📁 Note:** This file has been moved to the `deployment/` folder as part of project organization improvements.
> All Docker and infrastructure files are now centralized here for better maintainability.

## Overview

**CodeSage - MCP-First Code Discovery** uses Docker for containerized deployment with SQLite database for simplicity and portability. This is the only code discovery tool built entirely around the Model Context Protocol (MCP) for seamless AI integration.

## Architecture

- **Backend**: FastAPI application with MCP server
- **Database**: SQLite (file-based, no separate database container needed)
- **Proxy**: Nginx for production load balancing and SSL termination

## Development Deployment

### Quick Start

```bash
# Clone and navigate to project
git clone <repository>
cd codesage-algolia-challenge

# Copy environment file
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys

# Build and run
docker-compose up --build
```

### Development Services

- **Backend**: `http://localhost:8001`
  - API documentation: `http://localhost:8001/docs`
  - Health check: `http://localhost:8001/health`
  - MCP endpoints: `http://localhost:8001/api/v1/ai/mcp/`

### Volumes

- `backend_uploads`: File uploads storage
- `backend_data`: SQLite database persistence

## Production Deployment

### Docker Prerequisites

1. **Environment Configuration**

   ```bash
   # Copy and configure environment
   cp backend/.env.example backend/.env
   # Edit with production values:
   # - ENVIRONMENT=production
   # - ALGOLIA_APP_ID=your_app_id
   # - ALGOLIA_ADMIN_API_KEY=your_api_key
   # - GITHUB_TOKEN=your_github_token
   ```

2. **SSL Certificates** (Optional)

   ```bash
   mkdir ssl
   # Copy your SSL certificates to ssl/cert.pem and ssl/key.pem
   ```

### Deployment

```bash
# Build and deploy production stack
docker-compose -f docker-compose.prod.yml up --build -d

# Check status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f backend
```

### Production Services

- **Backend**: Internal port 8001
- **Nginx**: External ports 80/443
  - HTTP access: `http://yourdomain.com`
  - HTTPS access: `https://yourdomain.com` (if SSL configured)

## Key Features

### SQLite Database

- **Persistence**: Database stored in `backend_data` volume
- **Backup**: Simple file copy from container
- **Migration**: Automatic on container start

### Performance Optimization

- **Multi-stage builds**: Optimized production images
- **Nginx caching**: Static content and API response caching
- **Resource limits**: Configurable in docker-compose

### Security

- **Non-root user**: Application runs as non-privileged user
- **Read-only configs**: Nginx configuration mounted read-only
- **Health checks**: Built-in container health monitoring

## Maintenance Commands

### Backup Database

```bash
# Development
docker cp codesage_mcp_server:/app/codesage.db ./backup-$(date +%Y%m%d).db

# Production
docker cp codesage_mcp_server_prod:/app/data/codesage.db ./backup-prod-$(date +%Y%m%d).db
```

### View Logs

```bash
# Development
docker-compose logs -f backend

# Production
docker-compose -f docker-compose.prod.yml logs -f backend
docker-compose -f docker-compose.prod.yml logs -f nginx
```

### Update Deployment

```bash
# Pull latest code and rebuild
git pull
docker-compose down
docker-compose up --build -d

# Production
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up --build -d
```

### Monitor Resources

```bash
# Container stats
docker stats

# Disk usage
docker system df

# Clean up unused images/containers
docker system prune -a
```

## Environment Variables

### Required Variables

```env
# Algolia Configuration
ALGOLIA_APP_ID=your_algolia_app_id
ALGOLIA_ADMIN_API_KEY=your_algolia_admin_key
ALGOLIA_INDEX_NAME=codesage_code_entities

# GitHub Integration
GITHUB_TOKEN=your_github_personal_access_token

# Application Settings
SECRET_KEY=your_secret_key_for_session_management
ENVIRONMENT=development  # or production
DEBUG=true  # false for production

# Database (SQLite)
DATABASE_URL=sqlite:///./data/codesage.db
```

## Troubleshooting

### Common Issues

1. **Port conflicts**

   ```bash
   # Check what's using port 8001
   lsof -i :8001
   ```

2. **Permission issues**

   ```bash
   # Fix volume permissions
   docker-compose down
   sudo chown -R 1000:1000 ./backend
   docker-compose up --build
   ```

3. **Database connection issues**

   ```bash
   # Check database file exists and is writable
   docker exec codesage_mcp_server ls -la /app/data/
   ```

4. **Environment variables not loaded**

   ```bash
   # Verify environment inside container
   docker exec codesage_mcp_server env | grep ALGOLIA
   ```

### Debug Mode

```bash
# Run backend in debug mode
docker-compose run --rm backend python -c "
from app.main import app
from app.core.config import get_settings
settings = get_settings()
print('Config loaded:', settings.algolia_app_id[:8] + '...')
"
```

## Performance Tuning

### Production Optimizations

1. **Worker Processes**: Adjust in `docker-compose.prod.yml`

   ```yaml
   command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
   ```

2. **Memory Limits**: Add resource constraints

   ```yaml
   deploy:
     resources:
       limits:
         memory: 512M
       reservations:
         memory: 256M
   ```

3. **Nginx Caching**: Enable in `nginx.conf`

   ```nginx
   location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
       expires 1y;
       add_header Cache-Control "public, immutable";
   }
   ```

### Monitoring

```bash
# Resource usage
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Application metrics
curl -s http://localhost:8001/health | jq .
```
