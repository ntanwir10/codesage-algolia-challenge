# Docker deployment

Status: the Dockerfiles and Compose files have never been built in CI. Treat everything here as untested and expect to fix small problems.

## What runs

- `backend`: FastAPI on port 8001 (python:3.13-slim, non-root user, one uvicorn worker).
- `nginx`: serves the built frontend on port 80 and proxies `/api`, `/ws` and `/health` to the backend.

Run exactly one backend worker. Job state, WebSocket subscriptions and rate-limit counters are in-process, and SQLite is single-writer.

## Setup

```bash
cp .env.example backend/.env
# edit backend/.env: ALGOLIA_APP_ID, ALGOLIA_ADMIN_API_KEY, GITHUB_TOKEN, CODESAGE_API_KEY

python -c "import secrets; print(secrets.token_urlsafe(32))"   # generate a key
export CODESAGE_API_KEY=<the same key>

make build
make up      # docker compose -f deployment/docker-compose.yml up -d
```

(`docker compose -f deployment/docker-compose.yml up --build` does the same in the foreground.)

- The backend reads `backend/.env` (`env_file`).
- The container binds `0.0.0.0`, so `CODESAGE_API_KEY` is mandatory: the backend refuses to start without it.
- Export `CODESAGE_API_KEY` in your shell before building. Compose passes it to the frontend build as `VITE_CODESAGE_API_KEY`, and Vite embeds it in the JavaScript bundle. It must match the value in `backend/.env`. This is acceptable for local, single-user use only.
- Open http://localhost for the app. The backend is also published on http://localhost:8001 (API docs at `/docs`).
- The SQLite database lives in the `backend_data` volume at `/app/data` (`DATABASE_URL=sqlite:///./data/codesage.db`). Migrations run automatically at startup.
- Port 443 is not published: TLS is not configured. `nginx.conf` has a commented-out HTTPS server block to start from.

The development compose file bind-mounts `backend/` into the container and runs uvicorn with `--reload`.

## Common commands

```bash
make logs          # follow all logs
make logs-backend  # backend only
make status        # docker compose ps
make shell         # bash in the backend container
make down          # stop
make clean         # stop and remove volumes (deletes the database)
```

## Production compose

`make prod-build` and `make prod-up` use `deployment/docker-compose.prod.yml` and `backend/Dockerfile.prod` (no bind mount, no reload, `--workers 1`, `ENVIRONMENT=production`, so `/docs` is disabled). The backend expects `CORS_ORIGINS` as a comma-separated list (`https://app.example.com,https://other.example.com`); the placeholder in that file uses a JSON-style list, so replace it for your domain. It is also untested.

## Troubleshooting

- Backend exits immediately: check `make logs-backend`. A missing `CODESAGE_API_KEY` is the usual cause.
- Dashboard shows 401 errors or the WebSocket is rejected: the key baked into the frontend build differs from the backend's. Re-export `CODESAGE_API_KEY` and rebuild with `make build`.
- Repository ends in `failed`: read `error_message` (for example missing Algolia credentials, or a GitHub rate limit; set `GITHUB_TOKEN`).
