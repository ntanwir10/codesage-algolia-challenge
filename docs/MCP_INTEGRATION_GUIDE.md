# MCP integration guide

CodeSage exposes six tools to MCP clients. Claude Desktop starts a local stdio server (`mcp_launcher.sh`), which forwards tool calls to the CodeSage backend over HTTP.

```
Claude Desktop --stdio--> mcp_launcher.sh --> python -m codesage_mcp --HTTP--> backend :8001 --> SQLite / Algolia
```

The stdio server is built on the official `mcp` Python SDK (2.3.0, see `backend/requirements.txt`). The launcher runs `python -m codesage_mcp` from `backend/` using `.venv/bin/python` at the repo root.

## Prerequisites

1. The Python environment exists at `.venv` (see the README quick start).
2. `backend/.env` has your Algolia credentials and `CODESAGE_API_KEY`.
3. The backend is running (`make start-backend`) and at least one repository is indexed (status `completed`).

## Install into Claude Desktop

```bash
make install-claude                 # merge into the config
make install-claude ARGS=--dry-run  # print the merged config (key masked), write nothing
```

`scripts/install_claude_desktop.py`:

- finds the config file for your OS (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`; Windows: `%APPDATA%\Claude\...`; Linux: `~/.config/Claude/...`)
- adds or replaces only `mcpServers.codesage` and keeps every other key
- backs up the existing file as `claude_desktop_config.json.bak-<timestamp>`
- writes atomically and sets mode 600 on the file and its backup, because they hold the API key
- refuses to touch a file that is not valid JSON
- reads `CODESAGE_API_KEY` from `backend/.env`

Options go through `ARGS`, for example `make install-claude ARGS="--server-url http://127.0.0.1:8001 --name codesage"`. Others: `--config PATH`, `--api-key KEY`, and `--basic-auth USER` for the prod stack behind nginx (the password goes to the macOS Keychain; nginx adds the API key, so none is written). Restart Claude Desktop afterwards.

### Manual install

Copy `claude_desktop_config.example.json` into your Claude Desktop config and fix the path and key:

```json
{
  "mcpServers": {
    "codesage": {
      "command": "/absolute/path/to/this/repo/mcp_launcher.sh",
      "env": {
        "MCP_SERVER_URL": "http://127.0.0.1:8001",
        "CODESAGE_API_KEY": "your-api-key"
      }
    }
  }
}
```

The bridge reads `MCP_SERVER_URL` (default `http://127.0.0.1:8001`), `CODESAGE_API_KEY` (sent as `X-API-Key`), `CODESAGE_BASIC_AUTH_USER` and `CODESAGE_BASIC_AUTH_PASSWORD` (a login for the prod nginx; the launcher reads the password from the Keychain), and `CODESAGE_ALLOW_INSECURE_AUTH`. It refuses to send the key or login over plain `http://` to a non-loopback host unless `CODESAGE_ALLOW_INSECURE_AUTH=1`. Set `CODESAGE_MCP_LOG_LEVEL` to change its log level (default `INFO`).

## Tools

Arguments are validated; unknown arguments are rejected. `repository` accepts a numeric ID, a name, or `owner/name`; use `list_repositories` to see them.

### `list_repositories`
List the repositories indexed by CodeSage with their status and size. No arguments.

### `search_code`
Full-text search over indexed functions, classes, imports and doc sections. Returns ranked hits with file locations, snippets and GitHub links.

| Argument | Type | Notes |
| --- | --- | --- |
| `query` | string, required | Matched against names, descriptions and code |
| `repository` | string | Omit to search all indexed repositories |
| `language` | string | For example `python` |
| `entity_type` | `function`, `class`, `import`, `doc_section` | |
| `limit` | integer 1-50, default 10 | Results per page |
| `page` | integer >= 0, default 0 | Zero-based |

### `get_file`
Read a file with line numbers. Returns at most 400 lines, and 100,000 characters, per call.

| Argument | Type | Notes |
| --- | --- | --- |
| `repository` | string, required | |
| `path` | string, required | Exact file path in the repository |
| `start_line` | integer >= 1 | First line (1-based) |
| `end_line` | integer >= 1 | Last line |

### `list_definitions`
List functions, classes, imports and doc sections in a repository, ordered by file and line.

| Argument | Type | Notes |
| --- | --- | --- |
| `repository` | string, required | |
| `path_prefix` | string | Only files whose path starts with this |
| `entity_type` | `function`, `class`, `import`, `doc_section` | |
| `name` | string | Substring of the entity name |
| `limit` | integer 1-500, default 100 | |

### `analyze_repository`
Measured facts about a repository: file, line and entity counts, languages, top directories and the largest files.

| Argument | Type |
| --- | --- |
| `repository` | string, required |

### `find_patterns`
Find lines in a repository's files that match a literal string or a regular expression.

| Argument | Type | Notes |
| --- | --- | --- |
| `repository` | string, required | |
| `pattern` | string, required | 1-200 characters |
| `regex` | boolean, default false | Treat `pattern` as a regular expression |
| `path_glob` | string | For example `src/*.py` |
| `max_results` | integer 1-500, default 100 | |

A regex search spends at most 1 second per file and 10 seconds per call; files it could not finish are listed in `skipped_files` (the first 50) with `skipped_count`, and a call that ran out of time is marked `truncated`.

### Resources

The bridge also serves `resources/list` and `resources/read`. `codesage://repositories` lists repositories, and `codesage://repositories/{id}/files` lists the files of one repository (the first 5000, with `total_files` and `truncated`).

## HTTP endpoints

The bridge uses these; you can call them directly (for example for testing). All are under `/api/v1/ai`.

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `GET /mcp/capabilities` | none | Server name, version, tool names |
| `GET /mcp/tools` | none | Tool list with JSON Schemas |
| `POST /mcp/tools/call` | `X-API-Key` | Run a tool |
| `GET /mcp/resources` | none | Resource list |
| `GET /mcp/resources/read?uri=...` | `X-API-Key` | Read a resource |

```bash
curl -X POST http://127.0.0.1:8001/api/v1/ai/mcp/tools/call \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"tool_name": "search_code", "arguments": {"query": "parse", "limit": 3}}'
```

The response is `{"tool", "result", "is_error", "error"}`. A tool failure (for example an unknown repository) returns 200 with `is_error: true` and the message in `error`. An unknown tool is 404, invalid arguments are 422, a bad key is 401, and the endpoint is limited to 30 requests per minute.

## Troubleshooting

- The bridge writes logs to stderr, never stdout (stdout carries the protocol). In Claude Desktop, open its MCP log for the `codesage` server to read them.
- "CodeSage backend not reachable at ...": the backend is not running or `MCP_SERVER_URL` is wrong. Start it with `make start-backend`. While it is down, `tools/list` still works because the schemas are bundled with the bridge; only tool calls fail.
- "rejected the API key (401)": `CODESAGE_API_KEY` in the Claude Desktop config differs from `backend/.env`. Re-run `make install-claude`.
- "429": the rate limit was hit; retry shortly.
- Tools are listed but searches return nothing: no repository has finished indexing. Check `GET /api/v1/repositories/` for status and `error_message`.
- Launcher says `.venv/bin/python not found`: create the virtualenv as described in the README.

### Optional: check the bridge with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector ./mcp_launcher.sh
```

Pass `MCP_SERVER_URL` and `CODESAGE_API_KEY` as environment variables in the Inspector's UI (or export them first). You should see the six tools under Tools; calling one with the backend running returns JSON.

## Known limitations

- Tool calls need the backend running; the bridge does not start it.
- The backend is single-process, with in-memory job state.
