---
title: MCP HTTP endpoints
description: The /api/v1/ai endpoints behind the MCP bridge, with auth, rate limits, request and response examples, and how every failure reaches Claude.
---

The stdio bridge turns each MCP request into an HTTP call under `/api/v1/ai`. You can call the same endpoints directly with `curl`, which is the quickest way to debug a tool. The examples use `http://127.0.0.1:8001`, the default for a local install. For the tools themselves, see [MCP tools](/docs/reference/mcp-tools/).

## Endpoint summary

"Key" means the `X-API-Key` header, which the backend requires when `CODESAGE_API_KEY` is set. Rate limits are per client address and apply only while `ENABLE_RATE_LIMITING` is `true`.

| Endpoint | Key | Rate limit | Purpose |
| --- | --- | --- | --- |
| `GET /api/v1/ai/mcp/capabilities` | No | None | Server name, version and tool names |
| `GET /api/v1/ai/mcp/tools` | No | None | Every tool with its JSON Schema |
| `POST /api/v1/ai/mcp/tools/call` | Yes | `RATE_LIMIT_AI` (30/minute) | Run one tool |
| `GET /api/v1/ai/mcp/resources` | No | None | List resources |
| `GET /api/v1/ai/mcp/resources/read?uri=...` | Yes | `RATE_LIMIT_AI` (30/minute) | Read one resource |
| `GET /api/v1/ai/search/suggestions` | Yes | `RATE_LIMIT_DEFAULT` (100/minute) | Distinct entity names for auto-complete |

The key is only compared when one is configured. With no `CODESAGE_API_KEY` on a loopback install, every endpoint accepts any request from a local client. See [Security](/docs/concepts/security/).

:::note
The request guard runs before any endpoint. With a key set, a `Host` header that is not loopback, in `CORS_ORIGINS` or in `ALLOWED_HOSTS` gets `403 {"detail": "Host not allowed"}`. See [Error shapes](/docs/reference/rest-api/#error-shapes).
:::

## `POST /api/v1/ai/mcp/tools/call`

Runs a tool. This is the endpoint the bridge uses for every `tools/call`.

### Request

```http title="Request"
POST /api/v1/ai/mcp/tools/call HTTP/1.1
Content-Type: application/json
X-API-Key: your-api-key

{"tool_name": "search_code", "arguments": {"query": "parse", "limit": 3}}
```

| Field | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `tool_name` | string | Yes | none | One of the seven tool names |
| `arguments` | object | No | `{}` | The tool's arguments. Unknown keys are rejected |

```bash title="curl"
curl -sS -X POST http://127.0.0.1:8001/api/v1/ai/mcp/tools/call \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"tool_name": "search_code", "arguments": {"query": "parse", "limit": 3}}'
```

### Response

The body is always this envelope, whether the tool worked or not:

| Field | Type | Meaning |
| --- | --- | --- |
| `tool` | string | The tool that ran |
| `result` | object or null | The tool's result, or `null` on a tool error |
| `is_error` | boolean | `true` when the tool refused or failed in a way the caller can act on |
| `error` | string or null | The message, or `null` on success |

Success:

```json title="200 OK"
{
  "tool": "list_repositories",
  "result": {
    "repositories": [
      {
        "id": 1,
        "name": "octo/demo",
        "url": "https://github.com/octo/demo",
        "branch": null,
        "status": "completed",
        "total_files": 214,
        "total_entities": 1873,
        "error_message": null,
        "processed_at": "2026-10-26T14:03:11+00:00"
      }
    ]
  },
  "is_error": false,
  "error": null
}
```

A tool error is still HTTP `200`:

```json title="200 OK with is_error"
{
  "tool": "get_file",
  "result": null,
  "is_error": true,
  "error": "Repository 'nope' not found. Available repositories: octo/demo"
}
```

### Status codes

| Status | Cause |
| --- | --- |
| `200` | The tool ran. Check `is_error` |
| `401` | `{"detail": "Invalid or missing API key"}` |
| `403` | The request guard refused the host, the local-client rule or the origin |
| `404` | `{"detail": "Unknown tool 'x'"}` |
| `422` | The envelope or the tool arguments are invalid. See below |
| `429` | Rate limit reached. `Retry-After` is set |
| `500` | Unexpected failure: `{"detail": "Internal server error", "request_id": "..."}` |

A `422` for a bad envelope points at `body`, for example `["body", "tool_name"]`. A `422` for bad tool arguments names the argument directly, with no `body` prefix:

```json title="422 for search_code with limit=500"
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["limit"],
      "msg": "Input should be less than or equal to 50",
      "input": 500
    }
  ]
}
```

A missing required argument has `"type": "missing"` and the argument name in `loc`. The error list carries no `ctx` or `url` keys.

Every tool call has two outcomes you must handle: an HTTP error (this table) and a `200` with `is_error: true` (the tool's own refusal). The second kind is expected, for example when a repository is still indexing.

## `GET /api/v1/ai/mcp/capabilities`

```bash title="curl"
curl -sS http://127.0.0.1:8001/api/v1/ai/mcp/capabilities
```

```json title="200 OK"
{
  "name": "codesage",
  "version": "1.0.0",
  "capabilities": {"tools": true, "resources": true, "prompts": false},
  "tools": [
    "list_repositories",
    "search_code",
    "get_file",
    "list_definitions",
    "analyze_repository",
    "find_patterns",
    "add_repository"
  ]
}
```

`name` and `version` come from `MCP_SERVER_NAME` and `MCP_SERVER_VERSION`.

## `GET /api/v1/ai/mcp/tools`

Returns each tool with its description and its JSON Schema (`inputSchema`), the same schemas the bridge advertises.

```bash title="curl"
curl -sS http://127.0.0.1:8001/api/v1/ai/mcp/tools
```

```json title="200 OK (abridged to one tool)"
{
  "tools": [
    {
      "name": "list_repositories",
      "description": "List the repositories indexed by CodeSage with their status and size.",
      "inputSchema": {
        "additionalProperties": false,
        "properties": {},
        "title": "ListRepositoriesArgs",
        "type": "object"
      }
    }
  ],
  "count": 7
}
```

## `GET /api/v1/ai/mcp/resources`

```json title="200 OK"
{
  "resources": [
    {
      "uri": "codesage://repositories",
      "name": "Repositories",
      "description": "Indexed repositories and their status",
      "mimeType": "application/json"
    }
  ],
  "count": 1
}
```

Only the repository list is advertised. The per-repository file list is readable but not listed. See [Resources](/docs/reference/mcp-tools/#resources).

## `GET /api/v1/ai/mcp/resources/read`

| Query argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `uri` | string | Yes | `codesage://repositories` or `codesage://repositories/{id}/files` |

```bash title="curl"
curl -sS -H "X-API-Key: $CODESAGE_API_KEY" \
  "http://127.0.0.1:8001/api/v1/ai/mcp/resources/read?uri=codesage://repositories/1/files"
```

```json title="200 OK"
{
  "uri": "codesage://repositories/1/files",
  "mimeType": "application/json",
  "content": {
    "repository": "octo/demo",
    "total_files": 214,
    "truncated": false,
    "files": [
      {"file_path": "README.md", "language": "markdown", "line_count": 386}
    ]
  }
}
```

| Status | Cause |
| --- | --- |
| `200` | The resource was read |
| `401` | Missing or wrong key |
| `404` | `{"detail": "Unknown resource '<uri>'"}` or `{"detail": "Repository 99 not found"}` |
| `422` | `uri` is missing |
| `429` | Rate limit reached |

Unlike a tool call, a resource failure is an HTTP `404`, not a `200` with `is_error`.

## `GET /api/v1/ai/search/suggestions`

Returns distinct entity names for auto-complete. The dashboard uses it. It searches every repository unless you pass `repository_id`.

| Query argument | Type | Required | Default | Constraints |
| --- | --- | --- | --- | --- |
| `query` | string | Yes | none | Shorter than 2 characters (after trimming) returns an empty list |
| `limit` | integer | No | 10 | 1 to 20 |
| `repository_id` | integer | No | all repositories | Filters to one repository |

```bash title="curl"
curl -sS -H "X-API-Key: $CODESAGE_API_KEY" \
  "http://127.0.0.1:8001/api/v1/ai/search/suggestions?query=repo&limit=5"
```

```json title="200 OK"
{"suggestions": ["RepositoryService", "repository_status_websocket", "Repository", "RepositoryCreate"]}
```

The backend asks Algolia for twice `limit` hits and keeps the first distinct `entity_name` values in rank order. Any Algolia failure, including missing credentials, returns `{"suggestions": []}` with status `200`.

| Status | Cause |
| --- | --- |
| `200` | Always, once the key and rate limit pass |
| `401` | Missing or wrong key |
| `422` | `query` is missing, or `limit` is outside 1 to 20 |
| `429` | Rate limit reached |

## How failures reach Claude

The bridge maps every backend result to a tool error message that says what to fix. Resource reads fail as MCP protocol errors instead, with the same wording.

| Backend result | Tool error text |
| --- | --- |
| `MCP_SERVER_URL` is not `http(s)://host` | `MCP_SERVER_URL must start with http:// or https:// (got '<url>')`. Nothing is sent |
| Not reachable after one retry | ``CodeSage backend not reachable at <url>; start it with `make start-backend` ``. For a host other than loopback: `...; check MCP_SERVER_URL and that the host is up` |
| No answer in 30 seconds | `CodeSage backend did not answer within 30 s.` |
| Other transport error | `CodeSage backend request failed: <type>: <message>` |
| `401` with a Basic `WWW-Authenticate` header | `The proxy in front of CodeSage rejected the login (401); check the user and password (CODESAGE_BASIC_AUTH_USER and its Keychain entry)` |
| `401`, no key configured in the bridge | `No API key is configured; set CODESAGE_API_KEY in the MCP server's env in the Claude Desktop config.` |
| `401`, key sent | `CodeSage backend rejected the API key (401); check CODESAGE_API_KEY in the MCP server config` |
| `403` | `CodeSage refused the request (403): <detail>. If the backend runs on another host, add that host to ALLOWED_HOSTS on the backend and check MCP_SERVER_URL.` |
| `404` | `The backend returned 404 for <path>; check that MCP_SERVER_URL points at the backend root (no /api/v1).` |
| `422` | `Invalid arguments for '<name>' (422): <JSON detail>` |
| `429` | `CodeSage backend rate limit exceeded (429); wait a moment and retry` |
| `5xx` with a JSON body | `CodeSage backend error (<status>): <detail> (request <id>)`. The request ID comes from the body's `request_id`, or the `X-Request-ID` header. A `500` always has one |
| `5xx` without JSON (a proxy's HTML page) | `CodeSage backend error (<status>); the backend or the proxy in front of it may be down.` The body is not echoed |
| Any other non-`200` | `Unexpected response from CodeSage backend (<status>): <detail>` |
| `200` that is not a JSON object | `CodeSage backend returned an unexpected response; check MCP_SERVER_URL` |
| `200` with `is_error: true` | The backend's `error` text, or `Tool failed` if it is empty |
| Unknown tool name | `Unknown tool '<name>'. Available tools: <list>`. The bridge answers this itself and sends nothing |
| Bad arguments caught by the bridge | `Invalid arguments for '<name>': <field>: <reason>; ...`. Nothing is sent |

For resource reads, a `404` with a JSON body reads `Resource or repository not found: <detail>` and is reported as invalid params. Every other failure is an internal error.

## Bridge request behavior

The bridge is configured only by environment variables. Claude Desktop fills them from the `env` block of its config. The full list is in [Configuration](/docs/reference/configuration/#bridge-environment).

| Behavior | Detail |
| --- | --- |
| Base URL | `MCP_SERVER_URL` plus `/api/v1/ai`. A trailing `/` is removed. Default `http://127.0.0.1:8001` |
| Connect timeout | 5 seconds |
| Retry | A refused connection or a connect timeout is retried once, so a call makes at most two attempts. After the second failure the call errors with "not reachable" |
| Request timeout | 30 seconds. A timeout is not retried |
| Headers | `X-API-Key` when `CODESAGE_API_KEY` is set. HTTP basic auth when `CODESAGE_BASIC_AUTH_USER` is set |
| Plain-http refusal | If a key, a login, or a `user:password@` in the URL would go over `http://` to any host other than `127.0.0.1`, `localhost` or `::1`, the call errors and sends nothing. Use `https://`, or set `CODESAGE_ALLOW_INSECURE_AUTH=1` on a trusted network |
| URL check | The URL must start with `http://` or `https://` and have a host |
| Redaction | Messages and logs show the URL without any `user:password@`. The startup log line records only whether a key is set |
| Logs | stderr only. stdout carries the protocol. Level comes from `CODESAGE_MCP_LOG_LEVEL` (default `INFO`) |
| Argument check | The bridge validates arguments against the same models as the backend, then sends `{"tool_name": ..., "arguments": ...}` with `null` values removed |

:::caution
The bridge refuses plain `http://` to a remote host before it sends anything. If you see that error and the host is on a trusted network, set `CODESAGE_ALLOW_INSECURE_AUTH=1`. Otherwise put the backend behind HTTPS. See [Production](/docs/guides/production/).
:::

## Related pages

- [REST API](/docs/reference/rest-api/) for the repository endpoints and the shared error shapes.
- [Claude Desktop](/docs/guides/claude-desktop/) to install the bridge.
- [Troubleshooting](/docs/troubleshooting/) for a symptom-first view of these errors.
