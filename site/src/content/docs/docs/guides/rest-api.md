---
title: Use the REST API
description: A step-by-step curl walkthrough for adding, watching, searching, reprocessing and deleting repositories, and for handling errors and rate limits.
---

Everything the dashboard does is plain HTTP under `/api/v1`. This guide shows the full life of a repository with `curl`, with the responses you should expect. Field-by-field detail is in the [REST API reference](/docs/reference/rest-api/).

You need a running backend (see [Quick start](/docs/quick-start/)) and, for the search step, Algolia credentials in `backend/.env`. The examples use `http://127.0.0.1:8001`. CodeSage is self-hosted, so there is no public demo server.

## Set up your shell

Read the API key from `backend/.env` so it never appears in a command you type:

```bash title="Export the key"
export CODESAGE_API_KEY=$(sed -n 's/^CODESAGE_API_KEY=//p' backend/.env)
export BASE=http://127.0.0.1:8001
```

Reads need no key. Writes (create, edit, delete, process), the MCP tool call and the `/ws` socket do, and you send it in an `X-API-Key` header. If the backend runs without a key on loopback, the header is ignored.

## 1. Check health

```bash
curl -sS $BASE/health
```

```json title="Expected response"
{
  "status": "healthy",
  "timestamp": "2026-10-26T23:48:31.547878+00:00",
  "version": "1.0.0",
  "components": {
    "database": {
      "status": "healthy"
    },
    "algolia": {
      "status": "healthy"
    }
  }
}
```

If `algolia` says `not_configured` or `degraded`, the overall status is `degraded`. The backend still answers with `200`, but creating a repository returns `503` until you set `ALGOLIA_APP_ID` and `ALGOLIA_ADMIN_API_KEY`. Only a database failure gives `503` from `/health`.

## 2. Create a repository

```bash
curl -sS -X POST $BASE/api/v1/repositories/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"url": "https://github.com/pmndrs/zustand"}'
```

This response is illustrative. Creating a repository is a write call, so it was not run for this guide; the shape follows the response schema.

```json title="201 Created"
{
  "id": 2,
  "name": "pmndrs/zustand",
  "description": null,
  "url": "https://github.com/pmndrs/zustand",
  "branch": null,
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

The backend checks the repository on GitHub before it creates anything (10 seconds, one attempt). It then starts indexing in the background and returns at once. Note the `id`. You use it in every later step.

To index a branch, add `"branch": "release"` or use a branch URL such as `https://github.com/pmndrs/zustand/tree/release`. An empty `"branch": ""` means the default branch.

:::tip
Add the trailing slash in `/api/v1/repositories/`. Without it, the framework redirects the request and an extra round trip happens.
:::

Other git hosts go through the `add_repository` MCP tool. See [Other git hosts](/docs/guides/other-git-hosts/).

## 3. Poll the status

```bash
curl -sS $BASE/api/v1/repositories/2/status
```

The next block is illustrative, because a live run is too short to catch. The one after it is real.

```json title="While indexing"
{
  "repository_id": 2,
  "status": "processing",
  "processed_files": 100,
  "total_files": 120,
  "progress": 83.33333333333334,
  "error_message": null
}
```

`progress` is a percentage from 0 to 100. A small loop that waits for the end:

```bash title="Wait until the run ends"
while true; do
  status=$(curl -sS $BASE/api/v1/repositories/2/status | jq -r .status)
  echo "status: $status"
  case "$status" in completed|failed) break ;; esac
  sleep 3
done
```

When the run ends, the status is `completed` or `failed`:

```json title="Completed"
{
  "repository_id": 2,
  "status": "completed",
  "processed_files": 120,
  "total_files": 120,
  "progress": 100.0,
  "error_message": null
}
```

A completed run can still report `"error_message": "Partially indexed: ..."`. That means something was left out, for example files over the 1,000-file limit. The repository is searchable. A `failed` run puts the reason in `error_message`, for example `No supported code files found in repository`.

A real `failed` repository (id 1 in the test backend) reports its reason like this:

```json title="Failed"
{
  "repository_id": 1,
  "status": "failed",
  "processed_files": 0,
  "total_files": 0,
  "progress": 0.0,
  "error_message": "Processing was interrupted by a server restart; reprocess the repository"
}
```

## 4. Subscribe over WebSocket

Polling works, but the WebSocket pushes each batch as it is stored. Open the socket, then send a subscribe frame. The full protocol is in the [WebSocket reference](/docs/reference/websocket/).

With `websocat`, send the key as a header:

```bash title="websocat"
websocat -H "X-API-Key: $CODESAGE_API_KEY" ws://127.0.0.1:8001/ws
```

The server answers first:

```json
{"type": "connected", "data": {"message": "Connected to CodeSage real-time updates", "timestamp": "2026-10-26T14:00:00.123456+00:00"}}
```

Type this line and press Enter:

```json
{"type": "subscribe", "repository_id": 2}
```

The frames below are illustrative; their shape follows the [WebSocket reference](/docs/reference/websocket/).

```json title="Frames you receive"
{"type": "subscribed", "data": {"repository_id": 2}}
{"type": "repository_status", "data": {"repository_id": 2, "status": "processing", "name": "pmndrs/zustand", "processed_files": 100, "total_files": 120, "timestamp": "2026-10-26T14:00:19.552870+00:00"}}
{"type": "repository_status", "data": {"repository_id": 2, "status": "completed", "name": "pmndrs/zustand", "processed_files": 120, "total_files": 120, "timestamp": "2026-10-26T14:00:31.907316+00:00", "message": "Processing completed successfully"}}
```

Without `websocat`, Node 22 or later has a global `WebSocket`. This script sends the key as a `codesage.key.<hex>` subprotocol, the same way the dashboard does, and exits when the run ends:

```js title="watch.mjs"
const key = process.env.CODESAGE_API_KEY ?? "";
const id = Number(process.argv[2]);
const hex = Array.from(new TextEncoder().encode(key), (b) => b.toString(16).padStart(2, "0")).join("");
const socket = new WebSocket("ws://127.0.0.1:8001/ws", key ? ["codesage", `codesage.key.${hex}`] : ["codesage"]);

socket.onmessage = (event) => {
  const frame = JSON.parse(String(event.data));
  if (frame.type === "connected") {
    socket.send(JSON.stringify({ type: "subscribe", repository_id: id }));
  } else if (frame.type === "repository_status") {
    const u = frame.data;
    console.log(`${u.name}: ${u.status} ${u.processed_files}/${u.total_files}`);
    if (u.status === "completed" || u.status === "failed") socket.close(1000);
  } else if (frame.type === "error") {
    console.error(frame.data.message);
  }
};
socket.onclose = (event) => process.exit(event.code === 1000 ? 0 : 1);
```

```bash
CODESAGE_API_KEY=$CODESAGE_API_KEY node watch.mjs 2
```

```text title="Output"
pmndrs/zustand: processing 100/120
pmndrs/zustand: completed 120/120
```

A close with code `1008` means the key is wrong. A close with `1013` means the server has too many connections.

## 5. List repositories and read stats

```bash
curl -sS "$BASE/api/v1/repositories/?status=completed&limit=20"
```

The response is an array of repository objects, ordered by ID. You can filter by `language` and `status`, and page with `skip` and `limit` (1 to 500).

Real output for that request, from a backend holding one completed repository:

```json title="Expected response"
[
  {
    "name": "pmndrs/zustand",
    "description": null,
    "url": "https://github.com/pmndrs/zustand",
    "branch": null,
    "language": "typescript",
    "framework": "react",
    "id": 2,
    "status": "completed",
    "error_message": null,
    "total_files": 120,
    "processed_files": 120,
    "total_lines": 25117,
    "created_at": "2026-10-26T23:32:19",
    "updated_at": "2026-10-26T23:32:50",
    "processed_at": "2026-10-26T23:32:50.170474"
  }
]
```

```bash
curl -sS $BASE/api/v1/repositories/2/stats
```

```json title="Expected response"
{
  "repository_id": 2,
  "status": "completed",
  "total_files": 120,
  "processed_files": 120,
  "total_lines": 25117,
  "total_entities": 1025,
  "entities_by_type": {
    "class": 22,
    "doc_section": 398,
    "function": 474,
    "import": 131
  },
  "files_by_language": {
    "css": 3,
    "html": 2,
    "javascript": 14,
    "json": 7,
    "markdown": 47,
    "typescript": 34,
    "yaml": 13
  },
  "language": "typescript",
  "framework": "react"
}
```

To fetch one repository on its own, use `GET /api/v1/repositories/2`.

## 6. Search with the MCP tools endpoint

Search is an MCP tool, called through one HTTP endpoint. The body names the tool and its arguments. The response is always `{tool, result, is_error, error}`.

```bash
curl -sS -X POST $BASE/api/v1/ai/mcp/tools/call \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"tool_name": "search_code", "arguments": {"query": "createStoreImpl", "repository": "pmndrs/zustand", "limit": 2}}'
```

Real output, trimmed: the `snippet` strings are shortened with `…`.

```json title="Expected response"
{
  "tool": "search_code",
  "result": {
    "query": "createStoreImpl",
    "repository": "pmndrs/zustand",
    "total_hits": 5,
    "page": 0,
    "pages": 3,
    "results": [
      {
        "entity_name": "createStoreImpl",
        "entity_type": "function",
        "file_path": "src/vanilla.ts",
        "line_start": 60,
        "line_end": 97,
        "language": "typescript",
        "signature": "const createStoreImpl: CreateStoreImpl = (createState) => {",
        "snippet": "const createStoreImpl: CreateStoreImpl = (createState) => {\n  type TState = ReturnType<typeof createState>\n  type Listener = (state: TState, prevState: TState) => void\n  let state: TState\n  const list…",
        "description": "TypeScript function: createStoreImpl",
        "url": "https://github.com/pmndrs/zustand/blob/HEAD/src/vanilla.ts#L60-L97"
      },
      {
        "entity_name": "setState",
        "entity_type": "function",
        "file_path": "src/vanilla.ts",
        "line_start": 66,
        "line_end": 81,
        "language": "typescript",
        "signature": "const setState: StoreApi<TState>['setState'] = (partial, replace) => {",
        "snippet": "  const setState: StoreApi<TState>['setState'] = (partial, replace) => {\n    // TODO: Remove type assertion once https://github.com/microsoft/TypeScript/issues/37663 is resolved\n    // https://github.…",
        "description": "TypeScript function: createStoreImpl.setState",
        "url": "https://github.com/pmndrs/zustand/blob/HEAD/src/vanilla.ts#L66-L81"
      }
    ]
  },
  "is_error": false,
  "error": null
}
```

The other tools work the same way. This one reads a file:

```bash
curl -sS -X POST $BASE/api/v1/ai/mcp/tools/call \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"tool_name": "get_file", "arguments": {"repository": "pmndrs/zustand", "path": "src/vanilla.ts", "start_line": 1, "end_line": 6}}'
```

```json title="Expected response"
{
  "tool": "get_file",
  "result": {
    "repository": "pmndrs/zustand",
    "path": "src/vanilla.ts",
    "language": "typescript",
    "total_lines": 100,
    "start_line": 1,
    "end_line": 6,
    "truncated": false,
    "content": "   1| type SetStateInternal<T> = {\n   2|   _(\n   3|     partial: T | Partial<T> | { _(state: T): T | Partial<T> }['_'],\n   4|     replace?: false,\n   5|   ): void\n   6|   _(state: T | { _(state: T): T }['_'], replace: true): void"
  },
  "is_error": false,
  "error": null
}
```

Tool failures are `200` responses with `is_error: true`. This one is real: searching the failed repository id 1 (`gitlab.com/gitlab-org/gitlab-test`) with `search_code`:

```json title="A tool error"
{
  "tool": "search_code",
  "result": null,
  "is_error": true,
  "error": "Repository 'gitlab.com/gitlab-org/gitlab-test' failed to index: Processing was interrupted by a server restart; reprocess the repository. Reprocess it from the dashboard."
}
```

Check `is_error` as well as the HTTP status. The [MCP tools reference](/docs/reference/mcp-tools/) lists every tool and message.

## 7. Edit a repository

```bash
curl -sS -X PUT $BASE/api/v1/repositories/2 \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"description": "Demo service"}'
```

The response is the updated repository object, now with `updated_at` set. (The responses in steps 7 to 9 are illustrative: they are write calls, so they were not run for this guide.) Only the fields you send change, and `url` cannot be changed.

Changing `branch`, `language` or `framework` while a run is active returns `409`:

```json title="409 Conflict"
{"detail": "Repository 2 is being processed; change branch when it finishes"}
```

Changing the branch does not re-index. Reprocess to index the new branch.

## 8. Reprocess

A `completed` repository needs `force_reprocess=true`. A `failed` or `pending` one does not.

```bash
curl -sS -X POST -H "X-API-Key: $CODESAGE_API_KEY" \
  "$BASE/api/v1/repositories/2/process?force_reprocess=true"
```

```json title="202 Accepted"
{"message": "Processing started for repository 2", "repository_id": 2}
```

The status is `processing` as soon as the call returns, so a poll never reads the old `failed`. The run replaces the old index only after it has fetched the new files. Go back to step 3 or 4 to follow it.

Without the flag on a completed repository:

```json title="409 Conflict"
{"detail": "Repository is already processed; pass force_reprocess=true to reprocess it"}
```

## 9. Delete

```bash
curl -sS -X DELETE -H "X-API-Key: $CODESAGE_API_KEY" $BASE/api/v1/repositories/2
```

```json title="200 OK"
{"message": "Repository 2 deleted successfully"}
```

This removes the stored files, entities and Algolia records. It returns `409` while a run is active, so wait for `completed` or `failed` first. It returns `502` if Algolia refuses the delete, and the repository stays.

## 10. Handle errors and rate limits

Every error body has a `detail` key. Its shape depends on the status:

| Status | Body | What to do |
| --- | --- | --- |
| `401` | `{"detail": "Invalid or missing API key"}` | Check `$CODESAGE_API_KEY` |
| `403` | `{"detail": "Host not allowed"}` and similar | Use `127.0.0.1` or `localhost`, or add the host to `ALLOWED_HOSTS` |
| `404` | `{"detail": "Repository 99 not found"}` | Check the ID |
| `409` | `{"detail": "..."}`, with `repository_id` for a duplicate | Read the message. A duplicate tells you the existing ID |
| `422` | `{"detail": [{"type": ..., "loc": [...], "msg": ...}]}` or a string | Fix the field named in `loc`, or read the string |
| `429` | `{"detail": "Too many requests; try again in 60 seconds."}` | Wait for `Retry-After` seconds |
| `500` | `{"detail": "Internal server error", "request_id": "..."}` | Look up the `request_id` in the backend log |
| `502`, `503`, `504` | `{"detail": "..."}` | GitHub or Algolia problem. See the message |

A validation error from a bad URL looks like this. The 422 body below and the 409 further down are illustrative, because they come from the create call:

```bash
curl -sS -X POST $BASE/api/v1/repositories/ \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"url": "https://gitlab.com/group/project"}'
```

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

Adding the same URL twice returns the existing ID, which is handy in scripts:

```json title="409 Conflict"
{"detail": "pmndrs/zustand has already been added.", "repository_id": 2}
```

### Rate limits

Create and process allow 100 requests a minute per client address. MCP tool calls and resource reads allow 30 a minute. A rejected request returns `429` with a `Retry-After` header in seconds. This loop honors it:

```bash title="Retry after a 429"
call() {
  while true; do
    headers=$(mktemp)
    body=$(curl -sS -D "$headers" -X POST $BASE/api/v1/ai/mcp/tools/call \
      -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" -d "$1")
    if grep -q '^HTTP/[0-9.]* 429' "$headers"; then
      wait=$(awk 'tolower($1)=="retry-after:" {print $2+0}' "$headers")
      echo "rate limited; waiting ${wait:-60}s" >&2
      sleep "${wait:-60}"
    else
      echo "$body"; rm -f "$headers"; return
    fi
  done
}

call '{"tool_name": "list_repositories", "arguments": {}}'
```

A `503` from create can also carry `Retry-After`, when GitHub's API rate limit was reached. Set `GITHUB_TOKEN` to raise that limit. You can change the backend limits with `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_AI` and `ENABLE_RATE_LIMITING`; see [Configuration](/docs/reference/configuration/#rate-limits).

## Next steps

- [REST API reference](/docs/reference/rest-api/) for every field and status code.
- [MCP HTTP endpoints](/docs/reference/mcp-endpoints/) for the tool call envelope and the bridge.
- [Troubleshooting](/docs/troubleshooting/) if a call does not behave as shown.
