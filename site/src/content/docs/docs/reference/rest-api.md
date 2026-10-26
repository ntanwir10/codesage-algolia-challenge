---
title: REST API reference
description: Every REST route the CodeSage backend serves, with auth, rate limits, parameters, body and response schemas, examples and status codes.
---

The backend is a FastAPI app. The dashboard uses these routes, and you can call them with any HTTP client. Examples use `http://127.0.0.1:8001`, the default for a local install. For a walkthrough with `curl`, see the [REST API guide](/docs/guides/rest-api/). The MCP routes under `/api/v1/ai` are in [MCP HTTP endpoints](/docs/reference/mcp-endpoints/), and the `/ws` socket is in [WebSocket](/docs/reference/websocket/).

## Route summary

"Key" means the `X-API-Key` header, which is checked only when `CODESAGE_API_KEY` is set. "Limit" is the per-client-address rate limit.

| Method and path | Key | Limit | Purpose |
| --- | --- | --- | --- |
| `GET /` | No | None | Server name, version and links |
| `GET /health` | No | None | Database and Algolia health |
| `GET /docs`, `GET /redoc` | No | None | Interactive API docs. Off when `ENVIRONMENT=production` |
| `GET /api/v1/repositories/` | No | None | List repositories |
| `POST /api/v1/repositories/` | Yes | 100/minute | Add a GitHub repository and start indexing |
| `GET /api/v1/repositories/{repository_id}` | No | None | One repository |
| `PUT /api/v1/repositories/{repository_id}` | Yes | None | Edit a repository |
| `DELETE /api/v1/repositories/{repository_id}` | Yes | None | Delete a repository and its index records |
| `GET /api/v1/repositories/{repository_id}/status` | No | None | Processing status and progress |
| `GET /api/v1/repositories/{repository_id}/stats` | No | None | File, line and entity counts |
| `POST /api/v1/repositories/{repository_id}/process` | Yes | 100/minute | Start or restart indexing |
| `GET /api/v1/performance/metrics` | Yes | None | Full performance report |
| `GET /api/v1/performance/operations/{operation_name}` | Yes | None | Metrics for one operation type |
| `GET /api/v1/performance/system` | Yes | None | CPU, memory, disk and process figures |
| `POST /api/v1/performance/reset` | Yes | None | Clear operation history |
| `GET /api/v1/performance/health-check` | Yes | None | Quick health summary. `/performance/health` is a hidden alias |
| `GET /api/v1/performance/export` | Yes | None | Export the report as JSON |
| `GET /api/v1/ai/...` | Mixed | Mixed | See [MCP HTTP endpoints](/docs/reference/mcp-endpoints/) |
| `WS /ws` | Yes | Connection caps | See [WebSocket](/docs/reference/websocket/) |

The limits are `RATE_LIMIT_DEFAULT` (100/minute) for create and process, and `RATE_LIMIT_AI` (30/minute) for the MCP routes. Update, delete and the performance routes have no rate limit. See [Configuration](/docs/reference/configuration/#rate-limits).

:::note
Repository routes end with a slash (`/api/v1/repositories/`). A request without it normally gets a redirect from the framework, so send the slash to avoid an extra round trip.
:::

## Root and health

### `GET /`

Public. Returns static server information.

```json title="200 OK"
{
  "name": "CodeSage MCP Server",
  "version": "1.0.0",
  "docs": "/docs",
  "health": "/health",
  "mcp_capabilities": "/api/v1/ai/mcp/capabilities"
}
```

The `docs` value is always `/docs`, even in production where the docs page is off.

### `GET /health`

Public, no rate limit. The request guard exempts it from the `Host` check, because load balancers often address it by IP.

```bash title="curl"
curl -sS http://127.0.0.1:8001/health
```

```json title="200 OK, everything working"
{
  "status": "healthy",
  "timestamp": "2026-10-26T14:03:11.482913+00:00",
  "version": "1.0.0",
  "components": {
    "database": {"status": "healthy"},
    "algolia": {"status": "healthy"}
  }
}
```

```json title="200 OK, Algolia unreachable"
{
  "status": "degraded",
  "timestamp": "2026-10-26T14:03:11.482913+00:00",
  "version": "1.0.0",
  "components": {
    "database": {"status": "healthy"},
    "algolia": {"status": "degraded", "message": "Algolia is unreachable"}
  }
}
```

| Status | Meaning |
| --- | --- |
| `200` | `healthy` or `degraded` |
| `503` | `unhealthy`: the database check failed |

See [Health semantics](#health-semantics) for how the status is decided.

### `GET /docs` and `GET /redoc`

Swagger UI and ReDoc. Both return `404` when `ENVIRONMENT=production`. The schema at `/openapi.json` is not switched off by that setting.

## Repository object

Create, get, list and update return this object. The same fields appear in the list.

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | integer | Numeric ID |
| `name` | string | Display name, at most 255 characters. Defaults to `owner/repo` |
| `description` | string or null | Free text |
| `url` | string or null | Normalised `https://github.com/owner/repo`, at most 500 characters. Unique, compared case-insensitively on create |
| `branch` | string or null | Branch to index. `null` means the repository's default branch |
| `language` | string or null | Primary programming language. Set by each run. At most 50 characters |
| `framework` | string or null | Framework guessed by each run. At most 100 characters |
| `status` | string | `pending`, `processing`, `completed` or `failed` |
| `error_message` | string or null | Why the last run failed, or `Partially indexed: ...` when a completed run left something out |
| `total_files` | integer | Files selected for the run. Default 0 |
| `processed_files` | integer | Files stored so far. Default 0 |
| `total_lines` | integer | Lines across stored files. Default 0 |
| `created_at` | string (date-time) | When the row was created |
| `updated_at` | string or null | Set on the first update; `null` before that |
| `processed_at` | string or null | When the last run completed; `null` until then |

```json title="Repository object"
{
  "id": 1,
  "name": "octo/demo",
  "description": null,
  "url": "https://github.com/octo/demo",
  "branch": null,
  "language": "python",
  "framework": "fastapi",
  "status": "completed",
  "error_message": null,
  "total_files": 214,
  "processed_files": 214,
  "total_lines": 31842,
  "created_at": "2026-10-26T14:00:02",
  "updated_at": null,
  "processed_at": "2026-10-26T14:03:11"
}
```

The status moves `pending` to `processing` to `completed` or `failed`. A completed repository returns to `processing` on a forced reprocess, and a failed one on any reprocess. A server restart marks every `pending` or `processing` repository `failed`. See [Indexing pipeline](/docs/concepts/indexing-pipeline/) and [Data model](/docs/concepts/data-model/).

:::note
The SQLite driver returns timestamps without a UTC offset, so the example values above have none. Treat them as UTC.
:::

## `GET /api/v1/repositories/`

Lists repositories ordered by ID. Public, no rate limit.

| Query argument | Type | Default | Constraints | Meaning |
| --- | --- | --- | --- | --- |
| `skip` | integer | 0 | 0 to 2147483648 | Repositories to skip |
| `limit` | integer | 100 | 1 to 500 | Maximum repositories to return |
| `language` | string | none | exact match | Filter on the `language` field |
| `status` | string | none | exact match | Filter on `status`. Any text is accepted; an unknown value matches nothing |

```bash title="curl"
curl -sS "http://127.0.0.1:8001/api/v1/repositories/?status=completed&limit=20"
```

The response is a JSON array of [repository objects](#repository-object).

| Status | Cause |
| --- | --- |
| `200` | Array of repositories, possibly empty |
| `403` | Request guard refusal |
| `422` | `skip` or `limit` is out of range |

## `POST /api/v1/repositories/`

Adds a GitHub repository and starts a background indexing job. Needs the key. Limit 100/minute.

The route accepts github.com URLs only. Other hosts are added through the [`add_repository`](/docs/reference/mcp-tools/#add_repository) tool. See [Other git hosts](/docs/guides/other-git-hosts/).

### Body

| Field | Type | Required | Default | Constraints |
| --- | --- | --- | --- | --- |
| `url` | string | Yes | none | At most 500 characters. A github.com URL, with optional `www.`, `.git`, trailing slash and `/tree/<branch>`. `http://` and `git@github.com:owner/repo.git` are rewritten to `https://`. Ports, credentials, queries and fragments are refused |
| `name` | string | No | `""` | At most 255 characters. A blank name becomes `owner/repo` |
| `description` | string or null | No | `null` | Free text |
| `branch` | string or null | No | `null` | At most 100 characters. Omitted or `null` uses the branch in the URL, if any. An empty string means the default branch, even if the URL has a branch. Refused when it has a `..` path segment, a NUL, or starts with `-` |
| `language` | string or null | No | `null` | At most 50 characters. Replaced by the first run |
| `framework` | string or null | No | `null` | At most 100 characters. Replaced by the first run |

The stored `url` is rewritten to `https://github.com/<owner>/<repo>`, with the branch suffix and `.git` removed.

```bash title="curl"
curl -sS -X POST http://127.0.0.1:8001/api/v1/repositories/ \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"url": "https://github.com/octo/demo", "branch": "main"}'
```

### Response

`201 Created` with the [repository object](#repository-object). The job starts right after, so the first response shows `pending` and zero counts.

```json title="201 Created"
{
  "id": 7,
  "name": "octo/demo",
  "description": null,
  "url": "https://github.com/octo/demo",
  "branch": "main",
  "language": null,
  "framework": null,
  "status": "pending",
  "error_message": null,
  "total_files": 0,
  "processed_files": 0,
  "total_lines": 0,
  "created_at": "2026-10-26T14:00:02",
  "updated_at": null,
  "processed_at": null
}
```

### Order of checks and status codes

Nothing is created when a check fails. The checks run in this order: key, request guard, rate limit, body validation, duplicate URL, Algolia configured, GitHub check.

| Status | Cause |
| --- | --- |
| `201` | Created and scheduled |
| `401` | Missing or wrong key |
| `403` | Request guard refusal |
| `409` | Duplicate URL, matched case-insensitively. The body is `{"detail": "octo/demo has already been added.", "repository_id": 1}`. A rare race can instead give `{"detail": "Repository with URL https://github.com/octo/demo already exists"}` with no `repository_id` |
| `422` with a list | Body validation. `loc` is `["body", "url"]`, `["body", "branch"]`, `["body", "name"]` and so on. A URL on another host is `Invalid GitHub URL (host must be github.com): ...` |
| `422` with a string | The GitHub check refused the repository (see the table below) |
| `429` | Rate limit reached |
| `502` | GitHub rejected the server's `GITHUB_TOKEN`, answered with a 5xx, or could not be reached |
| `503` | Algolia is not configured, or GitHub's API rate limit was reached (with `Retry-After`) |
| `504` | The GitHub check did not answer within 10 seconds |

The GitHub check makes one request for the repository and one for its branch, 10 seconds in total, with no retries.

| Status | `detail` |
| --- | --- |
| `422` | `GitHub repository octo/demo was not found. Check the URL; if it's private, the server's GITHUB_TOKEN needs access.` |
| `422` | `GitHub denied access to octo/demo.` |
| `422` | `Branch 'x' does not exist in octo/demo.` |
| `422` | `octo/demo is empty; there is nothing to index.` |
| `502` | `GitHub rejected the server's GITHUB_TOKEN; check the token configured on the CodeSage server.` |
| `502` | `Could not reach GitHub; try again.` |
| `503` | `GitHub's API rate limit was reached; try again in about 2 minutes.` with `Retry-After: <seconds>` |
| `503` | `Search indexing is not configured on the server (Algolia credentials are missing).` |
| `504` | `GitHub did not respond in time; try again.` |

A repository that passes can still fail later, during the run. The reason is then in `error_message`.

## `GET /api/v1/repositories/{repository_id}`

Public, no rate limit.

| Path argument | Type | Constraints |
| --- | --- | --- |
| `repository_id` | integer | 1 to 9223372036854775807 |

```bash title="curl"
curl -sS http://127.0.0.1:8001/api/v1/repositories/7
```

| Status | Cause |
| --- | --- |
| `200` | The [repository object](#repository-object) |
| `404` | `{"detail": "Repository 7 not found"}` |
| `422` | The ID is not an integer in range, for example `0` or a 20-digit number |

## `PUT /api/v1/repositories/{repository_id}`

Edits a repository. Needs the key. No rate limit. Only the fields you send change. Fields that are not in the table (such as `url`) are ignored without an error.

### Body

| Field | Type | Constraints |
| --- | --- | --- |
| `name` | string | At most 255 characters. Must not be blank, and an explicit `null` is refused. Omit the field to keep the name |
| `description` | string or null | Free text. `null` clears it |
| `branch` | string or null | At most 100 characters. Refused when it has a `..` segment, a NUL, or starts with `-`. An empty string or `null` means the default branch and is stored as `null` |
| `language` | string or null | At most 50 characters |
| `framework` | string or null | At most 100 characters |

```bash title="curl"
curl -sS -X PUT http://127.0.0.1:8001/api/v1/repositories/7 \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"description": "Demo service", "branch": "release"}'
```

A new `branch` does not re-index anything. Run [`process`](#post-apiv1repositoriesrepository_idprocess) to index the new branch.

| Status | Cause |
| --- | --- |
| `200` | The updated [repository object](#repository-object) |
| `401` | Missing or wrong key |
| `404` | `Repository 7 not found` |
| `409` | A run or a delete holds the repository and the request changes `branch`, `language` or `framework`. For example `Repository 7 is being processed; change branch when it finishes`. Other fields can change at any time, and sending the same value is not a change |
| `422` | Validation. A blank name is `Value error, name cannot be empty` at `["body", "name"]`; a bad branch is `Value error, Invalid branch name` at `["body", "branch"]` |

## `DELETE /api/v1/repositories/{repository_id}`

Deletes the repository, its stored files and entities, and its Algolia records. Needs the key. No rate limit.

The Algolia delete is sent without waiting for Algolia to finish. Algolia applies an index's tasks in order, so records added later under a reused ID still land after the delete. Open WebSocket subscribers for the repository are dropped.

```bash title="curl"
curl -sS -X DELETE -H "X-API-Key: $CODESAGE_API_KEY" http://127.0.0.1:8001/api/v1/repositories/7
```

```json title="200 OK"
{"message": "Repository 7 deleted successfully"}
```

| Status | Cause |
| --- | --- |
| `200` | Deleted |
| `401` | Missing or wrong key |
| `404` | `Repository 7 not found` |
| `409` | `Repository 7 is being processed`. Wait for the run to end |
| `502` | `Could not remove the repository's records from Algolia; nothing was deleted`. The row stays, so retry later |

## `GET /api/v1/repositories/{repository_id}/status`

Public. The dashboard polls this every 3 seconds while a repository is in progress.

```bash title="curl"
curl -sS http://127.0.0.1:8001/api/v1/repositories/7/status
```

```json title="200 OK"
{
  "repository_id": 7,
  "status": "processing",
  "processed_files": 400,
  "total_files": 1000,
  "progress": 40.0,
  "error_message": null
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `repository_id` | integer | The ID |
| `status` | string | `pending`, `processing`, `completed` or `failed` |
| `processed_files` | integer | Files stored so far |
| `total_files` | integer | Files selected for the run |
| `progress` | number | Percentage from 0 to 100 (`processed_files / total_files * 100`). `0.0` while `total_files` is 0 |
| `error_message` | string or null | Failure reason, or what a completed run left out |

| Status | Cause |
| --- | --- |
| `200` | The status object |
| `404` | `Repository 7 not found` |
| `422` | Bad ID |

## `GET /api/v1/repositories/{repository_id}/stats`

Public. Counts come from the stored data, not from Algolia.

```bash title="curl"
curl -sS http://127.0.0.1:8001/api/v1/repositories/7/stats
```

```json title="200 OK"
{
  "repository_id": 7,
  "status": "completed",
  "total_files": 214,
  "processed_files": 214,
  "total_lines": 31842,
  "total_entities": 1873,
  "entities_by_type": {"function": 910, "class": 121, "import": 702, "doc_section": 140},
  "files_by_language": {"python": 96, "typescript": 71, "markdown": 12, "json": 9},
  "language": "python",
  "framework": "fastapi"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `entities_by_type` | object | Entity count per type. A type with no entities is absent |
| `files_by_language` | object | File count per language label |
| `total_entities` | integer | Sum of `entities_by_type` |
| Other fields | | As in the [repository object](#repository-object) |

| Status | Cause |
| --- | --- |
| `200` | The statistics |
| `404` | `Repository 7 not found` |
| `422` | Bad ID |

## `POST /api/v1/repositories/{repository_id}/process`

Starts or restarts indexing. Needs the key. Limit 100/minute. It returns before the job finishes. Follow progress with `/status` or the [WebSocket](/docs/reference/websocket/).

| Query argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `force_reprocess` | boolean | `false` | Required to re-run a repository whose status is `completed` |

```bash title="curl"
curl -sS -X POST -H "X-API-Key: $CODESAGE_API_KEY" \
  "http://127.0.0.1:8001/api/v1/repositories/7/process?force_reprocess=true"
```

```json title="202 Accepted"
{"message": "Processing started for repository 7", "repository_id": 7}
```

The route sets the status to `processing` and clears `error_message` before it returns, so a client polling `/status` never reads the old `failed`. The run replaces the previous index only after the new files are fetched, so a transient GitHub error does not wipe a working index.

| Status | Cause |
| --- | --- |
| `202` | Scheduled |
| `401` | Missing or wrong key |
| `404` | `Repository 7 not found` |
| `409` | `Repository is already processed; pass force_reprocess=true to reprocess it` (status `completed` without the flag) |
| `409` | `Repository 7 is already being processed` (a job is running) |
| `422` | Bad ID or a non-boolean `force_reprocess` |
| `429` | Rate limit reached |
| `503` | `Search indexing is not configured on the server (Algolia credentials are missing).` |

At most two runs execute at once. A third waits for a free slot while already showing `processing`.

## Performance endpoints

All routes under `/api/v1/performance` need the key and have no rate limit. The data lives in memory in the backend process: it is lost on restart and capped at the last 1,000 operations overall and 200 per operation type. The only operation type CodeSage records is `repository_processing`.

### `GET /api/v1/performance/metrics`

```json title="200 OK"
{
  "timestamp": 1792000000.123,
  "active_operations": 0,
  "total_operations": 3,
  "operations_summary": {
    "repository_processing": {
      "operation": "repository_processing",
      "count": 3,
      "total_items_processed": 0,
      "total_errors": 0,
      "duration": {"min": 4.2, "max": 31.7, "avg": 15.9},
      "throughput": {"min": 0, "max": 0, "avg": 0},
      "success_rate": 100.0
    }
  },
  "system_metrics": {
    "cpu_percent": 7.5,
    "memory": {"total_gb": 16.0, "available_gb": 6.1, "used_percent": 61.9},
    "disk": {"total_gb": 460.4, "free_gb": 212.8, "used_percent": 53.8},
    "process": {"memory_mb": 184.3, "threads": 14}
  },
  "recent_operations": [
    {
      "operation": "repository_processing",
      "duration_seconds": 31.7,
      "items_processed": 0,
      "throughput_per_second": 0.0,
      "memory_mb": {"start": 150.2, "end": 184.3, "peak": 184.3},
      "errors": 0,
      "metadata": {"repo_name": 7, "file_count": 0}
    }
  ]
}
```

`recent_operations` holds the last 10. `items_processed` stays 0 for repository runs.

| Status | Cause |
| --- | --- |
| `200` | The report |
| `401` | Missing or wrong key |
| `500` | `{"detail": "Failed to retrieve performance metrics"}` |

### `GET /api/v1/performance/operations/{operation_name}`

Returns the `operations_summary` entry for one operation type, as shown above.

| Status | Cause |
| --- | --- |
| `200` | The summary |
| `401` | Missing or wrong key |
| `404` | `No metrics found for operation: <name>` |
| `500` | `Failed to retrieve operation metrics` |

### `GET /api/v1/performance/system`

Returns the `system_metrics` object from the report.

| Status | Cause |
| --- | --- |
| `200` | The system figures |
| `401` | Missing or wrong key |
| `500` | `Unable to retrieve system metrics` or `Failed to retrieve system metrics` |

### `POST /api/v1/performance/reset`

Clears the operation history and per-type statistics. System monitoring keeps working.

```json title="200 OK"
{"message": "Performance metrics reset successfully", "timestamp": 1792000000.123}
```

| Status | Cause |
| --- | --- |
| `200` | Reset |
| `401` | Missing or wrong key |
| `500` | `Failed to reset performance metrics` |

### `GET /api/v1/performance/health-check`

A quick check against fixed thresholds. `/api/v1/performance/health` is a hidden alias for the same handler.

```json title="200 OK"
{
  "status": "healthy",
  "warnings": [],
  "active_operations": 0,
  "system_summary": {
    "cpu_percent": 7.5,
    "memory_used_percent": 61.9,
    "disk_used_percent": 53.8,
    "process_memory_mb": 184.3
  },
  "timestamp": 1792000000.123
}
```

| Condition | Result |
| --- | --- |
| CPU above 80 percent | `warning`, `High CPU usage` |
| Memory above 85 percent | `warning`, `High memory usage` |
| Disk above 90 percent | `critical`, `Disk space critical` |
| More than 10 active operations | `warning`, `High number of active operations (<n>)` |

The rules run in that order and each one overwrites `status`, so more than 10 active operations turns `critical` back into `warning`. All matching messages stay in `warnings`. A failure returns `500` with `Performance health check failed`.

### `GET /api/v1/performance/export`

| Query argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `format` | string | `json` | Only `json` (any letter case) is supported |

```json title="200 OK"
{
  "export_timestamp": 1792000000.123,
  "export_format": "json",
  "codesage_version": "1.0.0",
  "performance_data": {"timestamp": 1792000000.123, "active_operations": 0, "total_operations": 0, "operations_summary": {}, "system_metrics": {}, "recent_operations": []}
}
```

| Status | Cause |
| --- | --- |
| `200` | The export |
| `400` | `Only JSON format is currently supported` |
| `401` | Missing or wrong key |
| `500` | `Failed to export metrics` |

## Error shapes

There are four shapes. Clients can handle all of them by checking `detail`.

### String detail

Most errors are `{"detail": "<message>"}`.

```json title="401 Unauthorized"
{"detail": "Invalid or missing API key"}
```

```json title="404 Not Found"
{"detail": "Repository 99 not found"}
```

The request guard uses the same shape for `403`:

| `detail` | Cause |
| --- | --- |
| `Host not allowed` | The `Host` header is not allowed. With no key set, only `localhost`, `127.0.0.1` and `[::1]` pass. With a key set, loopback, the `CORS_ORIGINS` hosts and `ALLOWED_HOSTS` pass |
| `Only local clients are served without an API key` | No key is configured and the TCP peer is not a loopback address |
| `Cross-origin request refused` | A write (`POST`, `PUT`, `PATCH`, `DELETE`) carried an `Origin` that is neither in `CORS_ORIGINS` nor the API's own origin |

A request with no `Origin` header passes the origin check, so `curl` works. A write with no `Host` header is refused when no key is set, and allowed when a key is set.

An unknown route returns `{"detail": "Not Found"}`, and a wrong method returns `405` with `{"detail": "Method Not Allowed"}`.

### 422 validation list

Request validation failures carry a list. Each entry names the field in `loc`.

```json title="422 Unprocessable Entity"
{
  "detail": [
    {
      "type": "invalid_url",
      "loc": ["body", "url"],
      "msg": "Invalid GitHub URL (host must be github.com): https://gitlab.com/group/project",
      "input": "https://gitlab.com/group/project"
    }
  ]
}
```

| Key | Meaning |
| --- | --- |
| `type` | Machine-readable error type, such as `missing`, `invalid_url`, `invalid_branch` or `string_too_long` |
| `loc` | Where the problem is: `["body", "url"]`, `["query", "limit"]` or `["path", "repository_id"]` |
| `msg` | Human-readable message |
| `input` | The offending value |

Errors raised by a plain `ValueError` validator (the `PUT` name and branch checks) have `msg` starting with `Value error, `. The create-time URL and branch checks do not.

Not every `422` is a list. The GitHub check on create answers `422` with a string `detail`.

### 429 with Retry-After

```http title="429 Too Many Requests"
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{"detail": "Too many requests; try again in 60 seconds."}
```

`Retry-After` is the length of the matched limit's window in seconds, so a `30/minute` limit gives `60`. It falls back to `60` if the window cannot be read. The server sends no other rate-limit headers.

A `503` from create can also carry `Retry-After`, when GitHub's API rate limit was reached.

### 500 with request ID

An unhandled exception returns a generic body and never the error text.

```http title="500 Internal Server Error"
HTTP/1.1 500 Internal Server Error
X-Request-ID: 3f8a1c0e9b7d4e2fa5c6d8e7b0a19c42
Content-Type: application/json

{"detail": "Internal server error", "request_id": "3f8a1c0e9b7d4e2fa5c6d8e7b0a19c42"}
```

- The `request_id` equals the `X-Request-ID` response header and is attached to the server log lines for that request.
- Send your own `X-Request-ID` request header to choose the ID. Without one, the server generates a 32-character hex value. Every response carries the header.
- The 500 response includes CORS headers for an allowed `Origin`, so a browser can read it.
- A `500` raised deliberately as an `HTTPException` (the performance routes) is the plain string shape and has no `request_id` in the body.

## Health semantics

`GET /health` combines two checks.

| Component | Check | Statuses |
| --- | --- | --- |
| `database` | Runs `SELECT 1` | `healthy`, `unhealthy` |
| `algolia` | Calls `list_indices` with a 5-second timeout. The result is cached for 30 seconds | `healthy`, `degraded` (with `message: "Algolia is unreachable"`), `not_configured` |

| Database | Algolia | Overall `status` | HTTP |
| --- | --- | --- | --- |
| `healthy` | `healthy` | `healthy` | 200 |
| `healthy` | `degraded` or `not_configured` | `degraded` | 200 |
| `unhealthy` | any | `unhealthy` | 503 |

Only the database decides between `200` and `503`. That keeps a Docker or load balancer health check green while Algolia is not set up. When you see `degraded`, indexing and search are unavailable, but the repository list, status and stats still work.

## Related pages

- [REST API guide](/docs/guides/rest-api/) for a task-oriented walkthrough.
- [Configuration](/docs/reference/configuration/) for the settings that change these behaviors.
- [Security](/docs/concepts/security/) for how the key and the request guard fit together.
