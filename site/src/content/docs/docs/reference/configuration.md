---
title: Configuration reference
description: Every backend, frontend, bridge and Docker Compose setting, with defaults, types, validation and startup refusals.
---

CodeSage reads its backend settings from environment variables and from `backend/.env`. The settings class is [`backend/app/core/config.py`](https://github.com/ntanwir10/codesage-algolia-challenge/blob/master/backend/app/core/config.py), and the template is [`.env.example`](https://github.com/ntanwir10/codesage-algolia-challenge/blob/master/.env.example). For a first install, see [Installation](/docs/installation/). For the production stack, see [Production](/docs/guides/production/).

## How settings load

- `make setup` copies `.env.example` to `backend/.env` if that file is missing. Edit the copy.
- Variable names are case-insensitive. `algolia_app_id` and `ALGOLIA_APP_ID` are the same setting.
- A real environment variable beats a value in `.env`. In Docker, the Compose `environment:` entries beat `env_file`.
- Unknown variables in `.env` are ignored.
- Settings are read once at startup and cached. Restart the backend after any change.
- The backend must run from the `backend/` directory so the relative `.env` and `sqlite:///./codesage.db` paths resolve. `make start-backend` does this for you.

:::caution
Never commit `backend/.env`. It holds your Algolia admin key and the CodeSage API key. The repository ignores it.
:::

## Backend variables

### Server and security

| Variable | Default | Type | Effect |
| --- | --- | --- | --- |
| `CODESAGE_API_KEY` | unset | string | The shared key for write routes, the MCP tool call, resource reads, search suggestions, `/api/v1/performance/*` and `/ws`. Sent as `X-API-Key`. Empty counts as unset. `make setup`, `make start` and `make install-claude` generate one when it is missing |
| `MCP_SERVER_HOST` | `127.0.0.1` | string | Host used for startup validation, the OpenAPI `servers` entry and `python -m app.main`. A value other than `127.0.0.1`, `localhost` or `::1` requires `CODESAGE_API_KEY` |
| `MCP_SERVER_PORT` | `8001` | integer | Port used for the OpenAPI `servers` entry and `python -m app.main` |
| `ENVIRONMENT` | `development` | string | `production` turns off `/docs` and `/redoc`. `development` makes `python -m app.main` reload on change |
| `LOG_LEVEL` | `INFO` | string | Python log level, case-insensitive. Logs are JSON lines |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173,http://localhost:5174` | comma-separated list | Origins allowed by CORS. Also decides which browser origins may write and open `/ws`, and which hosts the API answers to when a key is set. `*` is refused |
| `ALLOWED_HOSTS` | empty | comma-separated list | Extra hostnames (no port) the API answers to when a key is set, on top of loopback and the `CORS_ORIGINS` hosts. `*.example.com` allows subdomains. `*` allows any host, which allows DNS rebinding, and logs a warning |

:::note
`make start-backend` always runs uvicorn with `--host 127.0.0.1 --port 8001`. `MCP_SERVER_HOST` and `MCP_SERVER_PORT` do not change that command. The Docker images pass `--host 0.0.0.0 --port 8001` themselves.
:::

### Algolia and GitHub

| Variable | Default | Type | Effect |
| --- | --- | --- | --- |
| `ALGOLIA_APP_ID` | unset | string | Algolia application ID. Required for indexing and search |
| `ALGOLIA_ADMIN_API_KEY` | unset | string | Algolia admin key. Required for indexing and search. Never expose it to the browser |
| `ALGOLIA_INDEX_NAME` | `codesage_code_entities` | string | The index CodeSage writes to. Use one index per database, because records are keyed by repository ID |
| `GITHUB_TOKEN` | unset | string | Raises the GitHub API rate limit and lets the backend read private github.com repositories. A rejected token makes create return `502` |

Without Algolia credentials the backend still starts. Adding or reprocessing a repository returns `503`, MCP search says search is not configured, and `/health` reports `degraded`.

### Database

| Variable | Default | Type | Effect |
| --- | --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./codesage.db` | URL | SQLite is the supported database. Migrations run at startup. File databases use WAL mode with foreign keys on |
| `SQL_ECHO` | `false` | boolean | `true` logs every SQL statement |

### Rate limits

| Variable | Default | Type | Effect |
| --- | --- | --- | --- |
| `ENABLE_RATE_LIMITING` | `true` | boolean | `false` switches every limit off |
| `RATE_LIMIT_DEFAULT` | `100/minute` | limit string | Repository create, repository process and search suggestions |
| `RATE_LIMIT_AI` | `30/minute` | limit string | MCP tool calls and MCP resource reads |

A limit string is `<count>/<period>`, for example `100/minute` or `5/second`. Limits are counted per client address. Behind nginx, uvicorn takes the address from `X-Forwarded-For` in the production image. Repository update and delete, the performance routes, the WebSocket and the read routes have no limit. A rejected request gets `429` with a `Retry-After` header. See [Error shapes](/docs/reference/rest-api/#429-with-retry-after).

### MCP server description

| Variable | Default | Type | Effect |
| --- | --- | --- | --- |
| `MCP_SERVER_NAME` | `codesage` | string | `name` in `GET /api/v1/ai/mcp/capabilities` |
| `MCP_SERVER_VERSION` | `1.0.0` | string | `version` in the same response |
| `MCP_SERVER_DESCRIPTION` | `AI-powered code discovery through natural language - MCP-First Architecture` | string | Description in the server configuration |

These three are not in `.env.example`. The bridge advertises its own fixed name `codesage` and version `1.0.0` to MCP clients, regardless of these values.

## Booleans and placeholders

- **Booleans.** `true`/`false`, `1`/`0`, `yes`/`no` and `on`/`off` are accepted, in any case.
- **Empty values.** An empty `ALGOLIA_APP_ID`, `ALGOLIA_ADMIN_API_KEY` or `CODESAGE_API_KEY` counts as unset, because the code tests for truthiness.
- **Placeholders.** For `ALGOLIA_APP_ID`, `ALGOLIA_ADMIN_API_KEY` and `GITHUB_TOKEN` only, a value that matches `your-...-here` (for example `your-algolia-app-id-here`) is converted to unset. This covers an `.env` copied from an old example. No other variable gets this treatment. A `CODESAGE_API_KEY` of `your-key-here` would be used as the key.

## Startup validation

The backend checks its settings before it serves anything. Two combinations stop it, with a `RuntimeError` and no server.

| Condition | Message |
| --- | --- |
| `CORS_ORIGINS` contains `*` | `CORS_ORIGINS must not contain '*' because credentials are allowed; list the allowed origins explicitly` |
| `CODESAGE_API_KEY` is unset and `MCP_SERVER_HOST` is not loopback | `CODESAGE_API_KEY is required when MCP_SERVER_HOST is not a loopback address (host is '0.0.0.0')` |

Two combinations only log a warning.

| Condition | Warning |
| --- | --- |
| No key, loopback host | `CODESAGE_API_KEY is not set; write endpoints are unauthenticated (acceptable on loopback only)` |
| Key set, `ALLOWED_HOSTS` contains `*` | `ALLOWED_HOSTS contains '*'; any Host is served, so DNS rebinding is not blocked` |

After validation, the backend runs database migrations, marks any repository left `pending` or `processing` by a previous process as `failed`, and logs whether Algolia is configured. A missing Algolia configuration logs an error but does not stop the server.

## Request guard rules that depend on settings

| Setting state | `Host` header must be | Other rule |
| --- | --- | --- |
| No key | `localhost`, `127.0.0.1` or `[::1]` | The TCP peer must be a loopback address |
| Key set | Loopback, a `CORS_ORIGINS` host, or in `ALLOWED_HOSTS` | None |

`/health` skips the `Host` check. Writes and WebSocket handshakes that carry an `Origin` header must match `CORS_ORIGINS` or the API's own origin. See [Security](/docs/concepts/security/).

## Frontend variables

The dashboard reads these at build time. Vite writes them into the JavaScript bundle, so anyone who can load the dashboard can read them. `make setup` creates `frontend/.env` from your backend key.

| Variable | Default | Effect |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | Base URL for API calls. A bare origin such as `http://localhost:8001` is accepted and gets `/api/v1` appended |
| `VITE_CODESAGE_API_KEY` | unset | Sent as `X-API-Key` on every request, and as the `codesage.key.<hex>` subprotocol on `/ws`. Must equal the backend key. `make setup`, `make start` and `make install-claude` keep it in sync |
| `VITE_WS_URL` | same-origin `/ws` | Full WebSocket URL, for example `ws://localhost:8001/ws`. Without it the client uses `ws:` or `wss:` to match the page |
| `VITE_WEBSOCKET_URL` | unset | Older alias. Used only when `VITE_WS_URL` is empty |
| `VITE_ENABLE_DEV_TOOLS` | unset | `true` shows the React Query devtools |

The dev server proxies `/api`, `/ws` and `/health` to `http://127.0.0.1:8001`, and it fails instead of moving off port 5173, because 5174 is not in the example `CORS_ORIGINS` for writes. Restart Vite after changing `frontend/.env`.

:::danger
`VITE_CODESAGE_API_KEY` is visible to every visitor of the dashboard. Use it for local, single-user setups only. The production stack keeps the key in nginx instead. See [Production](/docs/guides/production/).
:::

## Bridge environment

The stdio bridge (`python -m codesage_mcp`) does not read `backend/.env`. Claude Desktop sets these from the `env` block of its config. `make install-claude` writes `MCP_SERVER_URL` and `CODESAGE_API_KEY` there.

| Variable | Default | Effect |
| --- | --- | --- |
| `MCP_SERVER_URL` | `http://127.0.0.1:8001` | Backend base URL, without `/api/v1`. A trailing `/` is removed. Must start with `http://` or `https://` |
| `CODESAGE_API_KEY` | unset | Sent as `X-API-Key` |
| `CODESAGE_BASIC_AUTH_USER` | unset | Login for the production nginx (HTTP basic auth) |
| `CODESAGE_BASIC_AUTH_PASSWORD` | unset | Password for that login. The launcher fills it from the macOS Keychain (service `codesage-mcp`) when it is unset |
| `CODESAGE_ALLOW_INSECURE_AUTH` | unset | `1` allows the key or login over plain `http://` to a non-loopback host. Any other value does nothing |
| `CODESAGE_MCP_LOG_LEVEL` | `INFO` | Log level for the bridge's stderr output |
| `SSL_CERT_FILE` | unset | Standard Python variable. Point it at a certificate file when the production stack uses a self-signed certificate |

Request timeouts (5-second connect, 30-second request) and the single retry are fixed in code. See [Bridge request behavior](/docs/reference/mcp-endpoints/#bridge-request-behavior).

## Docker Compose

Both Compose files read `backend/.env` through `env_file`, then override some values. The overrides win.

| Variable | Dev stack (`docker-compose.yml`) | Prod stack (`docker-compose.prod.yml`) |
| --- | --- | --- |
| `MCP_SERVER_HOST` | `0.0.0.0` | `0.0.0.0` |
| `MCP_SERVER_PORT` | `8001` | `8001` |
| `DATABASE_URL` | `sqlite:///./data/codesage.db` | `sqlite:///./data/codesage.db` |
| `CORS_ORIGINS` | `http://localhost,http://localhost:3000,http://localhost:5173` | `https://yourdomain.com` (edit the file) |
| `ALGOLIA_INDEX_NAME` | `${DOCKER_ALGOLIA_INDEX_NAME:-codesage_code_entities_docker}` | `${PROD_ALGOLIA_INDEX_NAME:-codesage_code_entities_prod}` |
| `CODESAGE_API_KEY` | From `backend/.env` | `${CODESAGE_API_KEY:-}` from your shell |
| `ENVIRONMENT` | not set (`development`) | `production` |
| `ALLOWED_HOSTS` | not set | `${ALLOWED_HOSTS:-}` from your shell |

Variables you export in your shell before `make up` or `make prod-up`:

| Variable | Used by | Effect |
| --- | --- | --- |
| `CODESAGE_API_KEY` | Dev: the frontend build. Prod: backend and nginx | Dev bakes it into the bundle as `VITE_CODESAGE_API_KEY`. It must equal the key in `backend/.env`. Prod gives the same value to the backend and to nginx. The backend exits at start if it is empty |
| `DOCKER_ALGOLIA_INDEX_NAME` | Dev | Overrides `codesage_code_entities_docker` |
| `PROD_ALGOLIA_INDEX_NAME` | Prod | Overrides `codesage_code_entities_prod` |
| `ALLOWED_HOSTS` | Prod | Extra hostnames or IPs the site is reached by, comma-separated, no port |

Each stack uses its own index, and neither matches the local default `codesage_code_entities`. Two databases sharing one index delete each other's records, because records are keyed by repository ID.

Data lives in named volumes: `backend_data` (dev) and `backend_data_prod` (prod), mounted at `/app/data`. See [Docker](/docs/guides/docker/).

## Annotated example

A complete `backend/.env` with placeholders only. Replace every value in angle brackets.

```dotenv title="backend/.env"
# --- Security ---------------------------------------------------------------
# Shared key for writes, MCP tool calls, resource reads, suggestions,
# /api/v1/performance and /ws. Leave empty: make setup / start / install-claude
# generate one and copy it to frontend/.env.
CODESAGE_API_KEY=

# --- Server -----------------------------------------------------------------
# Anything other than loopback requires CODESAGE_API_KEY.
MCP_SERVER_HOST=127.0.0.1
MCP_SERVER_PORT=8001

# --- Algolia (required for indexing and search) ------------------------------
ALGOLIA_APP_ID=<your-algolia-application-id>
ALGOLIA_ADMIN_API_KEY=<your-algolia-admin-api-key>
# One index per database. Do not share it between local and Docker.
ALGOLIA_INDEX_NAME=codesage_code_entities

# --- GitHub (optional) -------------------------------------------------------
# Raises the GitHub rate limit and lets the backend read private repositories.
GITHUB_TOKEN=<your-github-personal-access-token>

# --- Database ----------------------------------------------------------------
DATABASE_URL=sqlite:///./codesage.db
SQL_ECHO=false

# --- Browser access ----------------------------------------------------------
# Comma-separated origins. "*" is rejected at startup.
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:5174
# Extra hostnames the API answers to when a key is set (no port).
# ALLOWED_HOSTS=docs.example.com,*.example.net

# --- Runtime -----------------------------------------------------------------
ENVIRONMENT=development
LOG_LEVEL=INFO

# --- Rate limits (per client address) ----------------------------------------
# ENABLE_RATE_LIMITING=true
# RATE_LIMIT_DEFAULT=100/minute
# RATE_LIMIT_AI=30/minute
```

The template `.env.example` lists `http://localhost:3000,http://localhost:5173` for `CORS_ORIGINS`, without 5174. The code default includes all three.

## Related pages

- [Commands](/docs/reference/commands/) for `make setup` and the other targets that write these files.
- [Security](/docs/concepts/security/) for what the key, hosts and origins protect.
- [Troubleshooting](/docs/troubleshooting/) for startup refusals and `degraded` health.
