---
title: Commands reference
description: Every Makefile target, the Claude Desktop installer options, npm scripts, backend test and lint commands, and useful curl one-liners.
---

Run every command from the repository root unless a block says otherwise. `make help` prints the target list. The recipes below come from the [Makefile](https://github.com/ntanwir10/codesage-algolia-challenge/blob/master/Makefile). Settings that the commands read are in [Configuration](/docs/reference/configuration/).

The Makefile defines two variables used by the Docker targets:

| Variable | Value |
| --- | --- |
| `COMPOSE` | `docker compose -f deployment/docker-compose.yml` |
| `COMPOSE_PROD` | `docker compose -f deployment/docker-compose.prod.yml` |

## Make targets

### Setup and local run

| Target | What it runs | Use it when | Side effects |
| --- | --- | --- | --- |
| `make help` | Prints the target list with `echo` | You forget a target name | None |
| `make setup` | See below | First install, or after you pull new dependencies | Creates `backend/.env`, `.venv/`, `frontend/node_modules/` and `frontend/.env`; may generate the API key |
| `make start` | See below | Everyday local development | Starts two long-running processes; may generate the API key |
| `make start-backend` | `cd backend && exec ../.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001` | You want only the backend, for example to run the dashboard separately | Serves on `127.0.0.1:8001` with auto-reload. Creates `backend/codesage.db` on first start and runs migrations |
| `make start-frontend` | `cd frontend && npm run dev` | The backend already runs | Serves the dashboard on port 5173 and fails if the port is taken |
| `make stop` | Kills the process listening on TCP 8001, then the one on 5173 (`lsof -ti tcp:<port> -sTCP:LISTEN \| xargs kill`) | You started with `make start` and want to stop | Stops only listeners on those two ports. Prints `Backend not running` or `Frontend not running` for a port with no listener |

`make setup` runs these steps:

1. Copy `.env.example` to `backend/.env` if `backend/.env` is missing.
2. Create `.venv` with `uv venv --python 3.13 .venv`, or `python3.13 -m venv .venv` when `uv` is missing. It stops with `Python 3.13 (or uv) is required` if neither exists. Skipped when `.venv/bin/python` already works.
3. Install `backend/requirements-dev.txt` with `uv pip install`, or `pip install` without `uv`.
4. Check that Node.js is version 22 or newer. It stops with `Node.js 22 or newer is required` otherwise.
5. Run `npm ci` in `frontend/`.
6. Run `.venv/bin/python scripts/ensure_api_key.py`, which generates `CODESAGE_API_KEY` in `backend/.env` if it is missing or empty and copies it to `frontend/.env` as `VITE_CODESAGE_API_KEY`. A key that already exists is never changed. The script never prints the key.
7. Print which values to put in `backend/.env`.

`make start` runs these steps:

1. Run `scripts/ensure_api_key.py`.
2. Refuse to continue if `http://127.0.0.1:8001/health` already answers. The message tells you to run `make stop` or `make start-frontend`.
3. Start `make start-backend` in the background.
4. Poll `/health` once a second for up to 15 seconds. If the backend process exits or never answers, kill it and fail with `The backend did not start; see its output above.`
5. Run `make start-frontend` in the foreground.

:::note
`make start` checks `/health` for any HTTP success. `degraded` (no Algolia) is still a `200`, so it starts. A `503` (database failure) counts as not started.
:::

### Docker

All of these use the dev Compose file except the two `prod-` targets. See [Docker](/docs/guides/docker/) and [Production](/docs/guides/production/).

| Target | What it runs | Use it when | Side effects |
| --- | --- | --- | --- |
| `make build` | `$(COMPOSE) build` | First run, or after changing code or `CODESAGE_API_KEY` | Builds the backend and nginx/frontend images |
| `make up` | `$(COMPOSE) up -d`, then prints the URLs | You want the dev stack | Starts `codesage_mcp_server` and `codesage_nginx` on `127.0.0.1` ports 8001 and 80. Needs `CODESAGE_API_KEY` exported for the frontend build |
| `make down` | `$(COMPOSE) down` | You are done | Stops and removes containers and the network. Volumes stay |
| `make restart` | `$(COMPOSE) restart` | You changed `backend/.env` | Restarts the containers |
| `make logs` | `$(COMPOSE) logs -f` | You want all logs | Follows until you press Ctrl+C |
| `make logs-backend` | `$(COMPOSE) logs -f backend` | You want only backend logs | Follows until you press Ctrl+C |
| `make shell` | `$(COMPOSE) exec backend bash` | You need a shell in the container | Interactive |
| `make status` | `$(COMPOSE) ps` | You want to see running containers | None |
| `make clean` | `$(COMPOSE) down -v --remove-orphans` | You want a fresh dev stack | Deletes the dev containers, network and the `backend_data` volume, so the dev database is gone. Algolia keeps its records |
| `make clean-all` | `$(COMPOSE) down -v --remove-orphans --rmi local` | Like `clean`, and you want the images gone too | The same, plus the locally built images. It never runs a host-wide prune |
| `make prod-build` | `$(COMPOSE_PROD) build` | Preparing the production stack | Builds the production images |
| `make prod-up` | `$(COMPOSE_PROD) up -d` | Starting the production stack | Starts nginx on ports 80 and 443. Needs `deployment/htpasswd`, `deployment/ssl/` and an exported `CODESAGE_API_KEY` |

### Checks and tests

| Target | What it runs | Use it when | Side effects |
| --- | --- | --- | --- |
| `make health` | `curl -sS http://127.0.0.1:8001/health \| jq .`, then `curl -fsS .../api/v1/ai/mcp/capabilities \| jq .tools` | You want to confirm the backend answers | None. Needs `jq`. Prints `Backend not responding` or `MCP not responding` on failure |
| `make test` | `.venv/bin/python -m pytest backend/tests -v` | Before you commit backend changes | None. Each test uses a fresh in-memory SQLite database |
| `make test-mcp` | Curls `.../api/v1/ai/mcp/capabilities` and `.../api/v1/ai/mcp/tools`, piping each to `jq .` | You want to see the MCP listings | None. Needs `jq` and a running backend |

### Database

| Target | What it runs | Use it when | Side effects |
| --- | --- | --- | --- |
| `make db-reset` | `rm -f backend/codesage.db backend/codesage.db-journal backend/codesage.db-wal backend/codesage.db-shm` | You want an empty local database | Deletes every local repository, file and entity. It does not touch Algolia. Stop the backend first |
| `make db-migrate` | `cd backend && ../.venv/bin/python -m alembic upgrade head` | You want to apply migrations by hand | Changes the schema of `backend/codesage.db`. The backend also does this at startup |
| `make db-migration` | Prompts for a message, then `cd backend && ../.venv/bin/python -m alembic revision --autogenerate -m "<message>"` | You changed a model and need a migration | Writes a file under `backend/alembic/versions/` |

`db-reset`, `db-migrate` and `db-migration` act on the local file `backend/codesage.db`, not on the Docker volume.

### Claude Desktop

| Target | What it runs | Use it when | Side effects |
| --- | --- | --- | --- |
| `make install-claude` | `.venv/bin/python scripts/ensure_api_key.py`, then `.venv/bin/python scripts/install_claude_desktop.py $(ARGS)` | Connecting Claude Desktop, or changing its settings | Merges one entry into the Claude Desktop config, after a backup. Restart Claude Desktop afterwards |

Pass installer options through `ARGS`: `make install-claude ARGS="--dry-run"`. See the next section for every option.

## Claude Desktop installer

`scripts/install_claude_desktop.py` uses only the Python standard library. It merges `mcpServers.<name>` into the Claude Desktop config, keeps every other key and server, writes a backup first and writes the new file atomically with mode 600.

| Option | Default | Effect |
| --- | --- | --- |
| `--config PATH` | Per-OS path, below | The config file to merge into |
| `--name NAME` | `codesage` | The key under `mcpServers`. A second name gives a second server entry |
| `--server-url URL` | `$MCP_SERVER_URL`, else `http://127.0.0.1:8001` | Backend base URL. Must be `http(s)` with a host. A URL that contains a password is refused |
| `--api-key KEY` | `CODESAGE_API_KEY` from `backend/.env` | Written into the entry's `env` block |
| `--basic-auth USER` | unset | For the production stack. Prompts for the password and stores it in the macOS Keychain (service `codesage-mcp`). No API key is written, because nginx supplies it. Needs the `security` command, so macOS only |
| `--dry-run` | off | Prints the merged config with the key shown as `********`, and writes nothing |

| OS | Default config path |
| --- | --- |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

The entry it writes:

```json title="claude_desktop_config.json"
{
  "mcpServers": {
    "codesage": {
      "command": "/absolute/path/to/codesage-algolia-challenge/mcp_launcher.sh",
      "env": {
        "MCP_SERVER_URL": "http://127.0.0.1:8001",
        "CODESAGE_API_KEY": "your-api-key"
      }
    }
  }
}
```

What the installer does and refuses:

- It copies an existing config to `claude_desktop_config.json.bak-<YYYYMMDD-HHMMSS>-<pid>` (with `-1`, `-2` if the name exists) before it writes.
- It refuses a config that is not valid JSON or not a JSON object, and changes nothing.
- It refuses a config whose `mcpServers` is not an object.
- It checks that the folder is writable before it touches the Keychain, so a failed run leaves no stray item.
- It warns, and creates the folder, when the default config folder does not exist. It does not warn when you pass `--config`.
- With no key found and no `--basic-auth`, it warns and writes an empty `CODESAGE_API_KEY`.

```bash title="Examples"
make install-claude ARGS="--dry-run"
make install-claude ARGS="--name codesage-dev --api-key your-api-key"
make install-claude ARGS="--server-url https://your-host --basic-auth alice"
python scripts/install_claude_desktop.py --config ./test-config.json --dry-run
```

The key helper `scripts/ensure_api_key.py` takes no options by default. It reads `backend/.env`, writes a key only when `CODESAGE_API_KEY` is missing or empty, and keeps `VITE_CODESAGE_API_KEY` in `frontend/.env` equal to it. Both files end up at mode 600.

## Frontend scripts

Run these from `frontend/`.

| Script | Command it runs | Use it when |
| --- | --- | --- |
| `npm run dev` | `vite` | Local development on port 5173, with a proxy for `/api`, `/ws` and `/health` to `127.0.0.1:8001` |
| `npm run build` | `tsc -b && vite build` | Type-checking and a production build into `frontend/dist/` |
| `npm run lint` | `eslint .` | Linting TypeScript and React code |
| `npm run preview` | `vite preview` | Serving the production build locally |
| `npm test` | `vitest run` | Running the unit tests once (jsdom) |

Install dependencies with `npm ci`. Node.js 22 or newer is required.

## Backend tests and lint

The backend targets Python 3.13. Use the virtual environment that `make setup` creates.

| Task | Command | Notes |
| --- | --- | --- |
| Run all tests | `make test` | Same as `.venv/bin/python -m pytest backend/tests -v` |
| Run tests from `backend/` | `cd backend && ../.venv/bin/python -m pytest` | `pytest.ini` sets `testpaths = tests`, `pythonpath = .` and `asyncio_mode = auto` |
| Run one test file | `.venv/bin/python -m pytest backend/tests/test_mcp_tools.py -v` | |
| Lint the backend | `.venv/bin/ruff check backend` | Rules `E`, `F`, `I`, `B`, `UP`, line length 100, target `py313` |
| Lint as CI does | `cd backend && ../.venv/bin/ruff check . ../scripts` | Also checks the scripts folder |

CI runs the backend lint and tests, the frontend lint, build and tests, validates both Compose files and both nginx configs, and builds the Docker images. See [Development](/docs/development/).

## Useful curl one-liners

Set the key once. It stays out of your shell history if you read it from the file:

```bash title="Export the key"
export CODESAGE_API_KEY=$(sed -n 's/^CODESAGE_API_KEY=//p' backend/.env)
```

```bash title="Health"
curl -sS http://127.0.0.1:8001/health
```

```bash title="List repositories"
curl -sS http://127.0.0.1:8001/api/v1/repositories/
```

```bash title="Add a repository"
curl -sS -X POST http://127.0.0.1:8001/api/v1/repositories/ \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"url": "https://github.com/octo/demo"}'
```

```bash title="Poll a repository's status"
curl -sS http://127.0.0.1:8001/api/v1/repositories/1/status
```

```bash title="Reprocess"
curl -sS -X POST -H "X-API-Key: $CODESAGE_API_KEY" \
  "http://127.0.0.1:8001/api/v1/repositories/1/process?force_reprocess=true"
```

```bash title="Delete"
curl -sS -X DELETE -H "X-API-Key: $CODESAGE_API_KEY" http://127.0.0.1:8001/api/v1/repositories/1
```

```bash title="Search through the MCP endpoint"
curl -sS -X POST http://127.0.0.1:8001/api/v1/ai/mcp/tools/call \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"tool_name": "search_code", "arguments": {"query": "rate limit", "limit": 3}}'
```

```bash title="List the tool names"
curl -sS http://127.0.0.1:8001/api/v1/ai/mcp/capabilities | jq .tools
```

```bash title="Performance health"
curl -sS -H "X-API-Key: $CODESAGE_API_KEY" http://127.0.0.1:8001/api/v1/performance/health-check
```

```bash title="Production health (self-signed certificate)"
curl -k https://localhost/health
```

For more on each route, see [REST API](/docs/reference/rest-api/) and [MCP HTTP endpoints](/docs/reference/mcp-endpoints/).
