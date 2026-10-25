# Docker deployment

Status: CI validates both Compose files and builds both images on every push, but never starts the containers. Expect to fix small problems at runtime.

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
- Export `CODESAGE_API_KEY` in your shell before building. Compose passes it to the frontend build as `VITE_CODESAGE_API_KEY`, and Vite embeds it in the JavaScript bundle. It must match the value in `backend/.env`. This is acceptable for local, single-user use only, which is why the dev file binds to 127.0.0.1. The prod stack does not embed the key (see below).
- Open http://localhost for the app. The dev file publishes nginx (port 80) and the backend (http://localhost:8001, API docs at `/docs`) on 127.0.0.1 only, because the bundle embeds the API key. The prod file publishes ports 80 and 443: port 80 answers only `/health` and redirects everything else, and 443 serves the app behind basic auth.
- The SQLite database lives in the `backend_data` volume at `/app/data` (`DATABASE_URL=sqlite:///./data/codesage.db`). Migrations run automatically at startup.
- Dev: port 443 is not published and TLS is not configured. Prod serves HTTPS on 443 (see below).

Each stack writes to its own Algolia index, because records are keyed by repository id and two databases sharing an index would delete each other's records. Dev compose sets `ALGOLIA_INDEX_NAME=codesage_code_entities_docker` (override with `DOCKER_ALGOLIA_INDEX_NAME`) and prod compose sets `codesage_code_entities_prod` (override with `PROD_ALGOLIA_INDEX_NAME`). Both differ from the local-run default `codesage_code_entities`.

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

`make prod-build` and `make prod-up` use `deployment/docker-compose.prod.yml` and `backend/Dockerfile.prod` (no bind mount, no reload, `--workers 1`, `ENVIRONMENT=production`, so `/docs` is disabled). `CORS_ORIGINS` is a comma-separated list (`https://app.example.com,https://other.example.com`); the compose file ships the placeholder `https://yourdomain.com`, so replace it with your domain. The nginx container is named `codesage_nginx_prod` so it cannot clash with the dev stack. This stack is untested.

Prod keeps the API key out of the browser. The frontend is built without `VITE_CODESAGE_API_KEY`; instead nginx (`deployment/nginx.prod.conf.template`) asks every visitor for a password with HTTP basic auth and adds `X-API-Key` to each `/api` and `/ws` request itself. `/health` stays open. Before `make prod-up`:

```bash
export CODESAGE_API_KEY=...   # used by both the backend and nginx; overrides backend/.env
docker run --rm httpd:alpine htpasswd -nbB <user> <password> > deployment/htpasswd
mkdir -p deployment/ssl   # then put cert.pem and key.pem there, for example:
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=your-host" \
  -addext "subjectAltName=DNS:your-host" -keyout deployment/ssl/key.pem -out deployment/ssl/cert.pem
```

Use a real certificate (for example from Let's Encrypt) for anything public. Port 80 answers only `/health` and redirects everything else to HTTPS.

`deployment/htpasswd` and `deployment/ssl/` are gitignored. To use the Claude Desktop bridge with this stack, run `make install-claude ARGS="--server-url https://your-host --basic-auth <user>"`. It asks for the password and stores it in the macOS Keychain (service `codesage-mcp`); the Claude Desktop config holds only the user name. nginx adds the API key, so the bridge needs none. The bridge refuses to send the login or an API key over plain `http://` to a non-loopback host unless `CODESAGE_ALLOW_INSECURE_AUTH=1` is set in its environment. With a self-signed certificate, add `SSL_CERT_FILE=/path/to/cert.pem` to the bridge's `env` in the Claude Desktop config. The Keychain needs macOS; elsewhere, set `CODESAGE_BASIC_AUTH_PASSWORD` in that `env` block instead (it is then stored in plain text, in a file the installer keeps at mode 600).

## Troubleshooting

- Backend exits immediately: check `make logs-backend`. A missing `CODESAGE_API_KEY` is the usual cause.
- Dashboard shows 401 errors or the WebSocket is rejected: the key baked into the frontend build differs from the backend's. Re-export `CODESAGE_API_KEY` and rebuild with `make build`.
- Repository ends in `failed`: read `error_message` (for example missing Algolia credentials, or a GitHub rate limit; set `GITHUB_TOKEN`).
