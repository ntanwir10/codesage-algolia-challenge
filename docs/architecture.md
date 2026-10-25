# Architecture

## Components

```
Browser                                        Claude Desktop
   |                                                 |
   | HTTP /api/v1, WebSocket /ws                     | stdio (MCP, JSON-RPC)
   v                                                 v
+------------------+                       +--------------------------+
| React dashboard  |                       | mcp_launcher.sh          |
| (Vite dev :5173  |                       |  -> python -m codesage_mcp|
|  or nginx :80)   |                       |  (official `mcp` SDK)    |
+--------+---------+                       +------------+-------------+
         |  X-API-Key / WS subprotocol                  | HTTP, X-API-Key
         v                                              v
+------------------------------------------------------------------+
| FastAPI backend (one process, 127.0.0.1:8001)                    |
|  /api/v1/repositories   CRUD, status, stats, process             |
|  /api/v1/ai             MCP tools and resources over HTTP        |
|  /api/v1/performance    metrics (API key required)               |
|  /ws                    repository status frames                 |
|  /health                database + Algolia check                 |
|                                                                  |
|  background job (asyncio task, one per repository)               |
+--------+---------------------------+-----------------------------+
         |                           |
         v                           v
   SQLite (Alembic)         +-----------------+      +-------------------+
   repositories             | Algolia (v3     |      | GitHub REST API   |
   code_files               | client, in      |      | git trees +       |
   code_entities            | worker threads) |      | file contents     |
                            +-----------------+      +-------------------+
```

- The stdio bridge (`backend/codesage_mcp`) holds no data. It translates MCP `tools/list`, `tools/call`, `resources/list` and `resources/read` into HTTP calls to the backend. Tool names, descriptions and argument models live in `codesage_mcp/schemas.py`, which the backend imports too, so `tools/list` works even when the backend is down.
- The backend owns all state: SQLite for files and entities, Algolia for search.
- Job state and WebSocket subscriptions are in memory, so the backend must run as a single worker.

## Data model (SQLite)

```
repositories 1 --- * code_files 1 --- * code_entities
(code_entities also stores repository_id directly)
```

| Table | Main columns |
| --- | --- |
| `repositories` | `id`, `name`, `url` (unique), `branch` (null = default branch), `language`, `framework`, `status`, `error_message`, `total_files`, `processed_files`, `total_lines`, timestamps |
| `code_files` | `id`, `repository_id`, `file_path`, `content`, `language`, `line_count` |
| `code_entities` | `id`, `file_id`, `repository_id`, `entity_type` (`function`, `class`, `import`, `doc_section`), `entity_name`, `start_line`, `end_line`, `signature`, `docstring`, `entity_metadata` (parameters, return type) |

Deleting a repository removes its files and entities (cascade) after its Algolia records are deleted. Status values are `pending`, `processing`, `completed` and `failed`.

Alembic migrations (`backend/alembic`) run automatically at startup. A database that predates Alembic (tables present, no `alembic_version`) is stamped at `baseline` and then upgraded. In-memory SQLite is created directly from the models.

## Ingestion pipeline

Triggered by `POST /api/v1/repositories/` (201) or `POST /api/v1/repositories/{id}/process` (202, or 409 if a job is running).

1. Mark the repository `processing` and broadcast the status.
2. Check Algolia credentials; fail with a clear `error_message` if missing.
3. Fetch the file list from the GitHub git trees endpoint for the repository's branch (default branch if none) and download the selected files. Denied directories (`node_modules`, `dist`, `build`, `vendor`, and similar), minified files and lockfiles are dropped, as are files of 1 MB or more; at most 1000 files and 100 MB in total are kept. At most two runs index at once; a queued run already shows `processing`.
4. Only after a successful fetch, clear the repository's previous Algolia records, files and entities, so a transient GitHub error does not wipe a working index.
5. Parse each file: `ast` for Python, tree-sitter for JavaScript, TypeScript, Java, Go, Rust, C, C++, C#, PHP and Ruby, a heading scanner for Markdown. CSS, HTML, JSON, YAML and XML yield no entities.
6. Store files and entities in SQLite, 200 files per commit, broadcasting progress after each batch.
7. Index the entity documents in Algolia in batches of 1000. Fail the run if nothing was indexed.
8. Set the primary language and a best-effort framework, mark the repository `completed`. If files were left out (not stored, not parsed, or over the limits), `error_message` says so as `Partially indexed: ...`. Any exception ends in `failed` with `error_message`; database errors are recorded as a generic message, since their text carries SQL and file contents.

At startup, repositories left `pending` or `processing` by a previous process are marked `failed`.

## Real-time updates

`/ws` accepts the connection only if the key is valid (when a key is configured; otherwise it closes with code 1008). Browsers send it as a `codesage.key.<hex>` subprotocol next to `codesage`; the prod nginx sends `X-API-Key`. Cross-origin handshakes are refused. Client messages are `subscribe` and `unsubscribe` (each with a positive `repository_id`; at most 100 subscriptions per connection) and `ping`. Server frames are `{type, data}`: `connected`, `subscribed`, `unsubscribed`, `pong`, `error`, and `repository_status` for subscribed repositories. The dashboard also polls the status endpoint while a repository is in progress.

## Search

Indexed fields are searched in this order: entity name, description, content, parameters, file path. Facets are `repository_id` (filter only), `entity_type`, `language` and `file_path`. Ties are broken by entity kind (classes, then functions, doc sections, imports). Each record stores at most 2000 characters of the entity body.

## Security model

- Binds to `127.0.0.1` by default. A non-loopback `MCP_SERVER_HOST` requires `CODESAGE_API_KEY`, or the app will not start.
- The key is checked with a constant-time comparison. It guards writes, `/api/v1/performance/*`, `GET /api/v1/ai/search/suggestions`, `GET /api/v1/ai/mcp/resources/read`, `POST /api/v1/ai/mcp/tools/call` and `/ws`. Other GETs are public.
- `BrowserRequestGuard` (`app/core/security.py`) refuses browser writes and WebSocket handshakes whose `Origin` is neither in `CORS_ORIGINS` nor the API's own scheme and host, because prod nginx adds the key to any request carrying the browser's login. With no key configured it also serves only loopback clients addressed as `localhost`, `127.0.0.1` or `[::1]`, which blocks DNS rebinding and LAN access to a server bound to `0.0.0.0` by hand.
- CORS origins are an explicit list; `*` is rejected.
- Rate limiting uses slowapi, keyed by client address.
- Unhandled errors return a generic 500 with a request ID (`X-Request-ID`); details stay in the logs.
- The frontend's `VITE_CODESAGE_API_KEY` is embedded in the bundle, so the dashboard is a local, single-user tool.

## Known limitations

- The Algolia v3 client is synchronous and runs in worker threads.
- One worker only: job state, the two-run limit and WebSocket subscriptions are in process.
- SQLite only.
- Frontend tests are unit tests only; Docker images are untested.
