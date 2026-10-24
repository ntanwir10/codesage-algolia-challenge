# CodeSage

CodeSage indexes GitHub repositories into Algolia and exposes them to AI assistants through the Model Context Protocol (MCP). It has a FastAPI backend, a React dashboard, and a stdio MCP server that Claude Desktop launches.

Built for the [Algolia MCP Server Challenge](https://dev.to/challenges/algolia-2025-07-09).

## What it does

1. You submit a GitHub repository URL (dashboard or API).
2. A background job downloads the repository's source files through the GitHub REST API (git trees endpoint), parses them into entities (functions, classes, imports, doc sections), stores files and entities in SQLite, and indexes the entities in Algolia.
3. Claude Desktop (or any MCP client) calls six tools to search and inspect the indexed code.

### Supported languages

- Python is parsed with `ast`.
- JavaScript, TypeScript, Java, Go, Rust, C, C++, C#, PHP and Ruby are parsed with tree-sitter.
- Markdown headings become `doc_section` entities.
- CSS, HTML, JSON, YAML and XML files are stored but produce no entities.
- `dist/`, `build/`, `vendor/`, `node_modules/`, minified files and lockfiles are skipped. At most 1000 files of under 1 MB each are fetched per repository.

## Requirements

- Python 3.13 and [`uv`](https://docs.astral.sh/uv/) (or any way to create `.venv` at the repo root)
- Node.js 22 and npm (frontend)
- An Algolia application ID and Admin API key
- Optional: a GitHub token. Without one, GitHub's unauthenticated rate limit applies, so `GITHUB_TOKEN` is recommended.

## Quick start

```bash
make setup
```

`make setup` copies `.env.example` to `backend/.env` (if missing), creates `.venv` at the repo root (with `uv` if available, otherwise `python3.13 -m venv`), installs `backend/requirements-dev.txt` into it, and runs `npm ci` in `frontend/`.

Edit `backend/.env`: set `ALGOLIA_APP_ID`, `ALGOLIA_ADMIN_API_KEY`, `GITHUB_TOKEN` and `CODESAGE_API_KEY` (see below). Docker and `make install-claude` read `backend/.env`; the backend also finds a `.env` in the repo root.

Then:

```bash
make start            # backend on 127.0.0.1:8001 and frontend on http://localhost:5173
# or separately:
make start-backend    # .venv/bin/python -m uvicorn app.main:app --reload, from backend/
make start-frontend   # Vite dev server on 5173, proxying /api, /ws and /health to the backend
make stop             # stops whatever listens on ports 8001 and 5173
```

Interactive API docs are at http://127.0.0.1:8001/docs (disabled when `ENVIRONMENT=production`).

### API key setup

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the output in `backend/.env` as `CODESAGE_API_KEY=...`. For the dashboard, set the same value as `VITE_CODESAGE_API_KEY` in `frontend/.env.local`.

The key is required unless the server is bound to a loopback address: the backend refuses to start with a non-loopback `MCP_SERVER_HOST` and no key. When a key is set, it must be sent as:

- the `X-API-Key` header on write endpoints (create, update, delete, process), on `/api/v1/performance/*`, and on `POST /api/v1/ai/mcp/tools/call`
- the `?api_key=` query parameter on the `/ws` WebSocket

Read endpoints (listing and fetching repositories, status, stats, tool and resource listings, `/health`) do not require the key.

Warning: `VITE_*` variables are inlined into the JavaScript bundle, so anyone who can load the dashboard can read the key. This setup is for local, single-user use only.

## Using it

### Index a repository

```bash
curl -X POST http://127.0.0.1:8001/api/v1/repositories/ \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"url": "https://github.com/owner/repo"}'
```

The response is `201` with the repository record, and a background job starts (one job per repository at a time).

- Status moves `pending`, `processing`, then `completed` or `failed`. On failure, `error_message` says why.
- Poll `GET /api/v1/repositories/{id}/status`, or connect to `/ws`, send `{"type":"subscribe","repository_id":N}`, and read `{type, data}` frames.
- `POST /api/v1/repositories/{id}/process?force_reprocess=true` re-runs processing. It returns `202`, or `409` if a job is already running (or the repository is completed and `force_reprocess` is not set).
- A server restart marks interrupted runs as `failed`; reprocess them.

### Connect Claude Desktop

```bash
make install-claude                 # merge into the Claude Desktop config
make install-claude ARGS=--dry-run  # preview only; the key is masked
```

The installer keeps your other servers, writes a timestamped backup, and sets the file to mode 600. It reads `CODESAGE_API_KEY` from `backend/.env`. Restart Claude Desktop afterwards and keep the backend running. Details and troubleshooting: [docs/MCP_INTEGRATION_GUIDE.md](docs/MCP_INTEGRATION_GUIDE.md).

### MCP tools

| Tool | Purpose |
| --- | --- |
| `list_repositories` | Indexed repositories with status and size |
| `search_code` | Full-text search over functions, classes, imports and doc sections |
| `get_file` | Read a file with line numbers (at most 400 lines per call) |
| `list_definitions` | Definitions in a repository, ordered by file and line |
| `analyze_repository` | File, line and entity counts, languages, top directories, largest files |
| `find_patterns` | Literal or regex line matches across a repository's files |

## Docker

```bash
export CODESAGE_API_KEY=...   # becomes the frontend build argument; must match backend/.env
make up                       # docker compose -f deployment/docker-compose.yml up -d
```

This starts the backend and nginx, which serves the frontend on http://localhost and proxies `/api`, `/ws` and `/health`. The images have never been built in CI, so treat this path as untested. See [deployment/DOCKER.md](deployment/DOCKER.md).

## Testing

```bash
make test                         # backend pytest (backend/tests)
.venv/bin/ruff check backend      # backend lint
cd frontend && npm test           # vitest unit tests
cd frontend && npm run lint
cd frontend && npm run build      # type-check and production build
```

CI (`.github/workflows/ci.yml`) runs ruff and pytest for the backend, and lint, build and tests for the frontend. Frontend tests are unit tests only; there are no end-to-end tests.

## Configuration

Set these in `backend/.env` (see `.env.example`):

| Variable | Default | Notes |
| --- | --- | --- |
| `CODESAGE_API_KEY` | unset | Required unless bound to loopback |
| `MCP_SERVER_HOST`, `MCP_SERVER_PORT` | `127.0.0.1`, `8001` | A non-loopback host requires the key |
| `ALGOLIA_APP_ID`, `ALGOLIA_ADMIN_API_KEY` | unset | Required for indexing |
| `ALGOLIA_INDEX_NAME` | `codesage_code_entities` | One index per database. Compose overrides it: `codesage_code_entities_docker` (dev) and `codesage_code_entities_prod` (prod) |
| `GITHUB_TOKEN` | unset | Optional; raises GitHub rate limits |
| `DATABASE_URL` | `sqlite:///./codesage.db` | SQLite only |
| `CORS_ORIGINS` | localhost ports 3000, 5173, 5174 | Comma-separated; `*` is rejected |
| `ENVIRONMENT`, `LOG_LEVEL` | `development`, `INFO` | `production` hides `/docs` |

Rate limits (slowapi, per client address): 100 per minute on repository create and process, 30 per minute on the MCP tool-call endpoint.

## Project layout

```
backend/app/            FastAPI app (api, core, models, schemas, services)
backend/codesage_mcp/   stdio MCP server (python -m codesage_mcp)
backend/alembic/        database migrations
backend/tests/          pytest suite
frontend/               React + Vite dashboard
deployment/             Docker Compose files, nginx.conf
scripts/                install_claude_desktop.py
mcp_launcher.sh         what Claude Desktop runs
docs/                   architecture and MCP guide
```

## Known limitations

- The Algolia v3 client is synchronous; calls run in worker threads.
- Job state and WebSocket subscriptions live in the server process, so run exactly one worker.
- SQLite only. Alembic migrations run automatically at startup; a database from before Alembic is stamped at `baseline` first.
- Frontend tests are unit tests only.
- The Docker images are untested.
- The dashboard API key is embedded in the JavaScript bundle (local, single-user use only).

See [docs/architecture.md](docs/architecture.md) for how the pieces fit together.
