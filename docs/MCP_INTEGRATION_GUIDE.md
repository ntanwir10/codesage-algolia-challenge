# MCP integration guide

How to connect Claude Desktop (or any MCP client) to CodeSage: the installer, the stdio bridge's settings, the six tools and two resources it serves, the backend endpoints behind them, and what to do when a call fails. For the end-to-end picture, including the tool-call sequence diagram, see the [root README](../README.md#using-it-from-claude-desktop).

## Contents

- [How the pieces fit](#how-the-pieces-fit)
- [Prerequisites](#prerequisites)
- [Install into Claude Desktop](#install-into-claude-desktop)
- [Manual install](#manual-install)
- [Bridge settings](#bridge-settings)
- [Tools](#tools)
- [Resources](#resources)
- [HTTP endpoints](#http-endpoints)
- [How failures reach Claude](#how-failures-reach-claude)
- [Troubleshooting](#troubleshooting)
- [Checking the bridge with the MCP Inspector](#checking-the-bridge-with-the-mcp-inspector)
- [Known limitations](#known-limitations)

## How the pieces fit

Claude Desktop starts `mcp_launcher.sh`. The launcher runs `python -m codesage_mcp` (the bridge) from `backend/`, using `.venv/bin/python` at the repo root. The bridge is built on the `mcp` Python SDK (pinned in `backend/requirements.txt`) and forwards each tool call as an HTTP request to the backend.

- **Schemas live in the bridge.** `tools/list` is answered from `backend/codesage_mcp/schemas.py`, so it works while the backend is down. Only tool calls and resource reads need the backend.
- **Arguments are checked twice.** The bridge validates them first, then the backend validates them again. Unknown arguments are rejected in both places.
- **Logs go to stderr.** stdout carries the protocol only.

## Prerequisites

- **Virtualenv.** `.venv` exists at the repo root (`make setup`).
- **Backend config.** `backend/.env` has your Algolia credentials, and `CODESAGE_API_KEY` if you set one.
- **Backend running.** `make start-backend`, with at least one repository in status `completed`.

## Install into Claude Desktop

```bash
make install-claude                 # merge CodeSage into the Claude Desktop config
make install-claude ARGS=--dry-run  # print the merged config with the key masked; write nothing
```

`make install-claude` runs `.venv/bin/python scripts/install_claude_desktop.py $(ARGS)`. It uses only the standard library.

### Options

| Option | Default | Notes |
| --- | --- | --- |
| `--config PATH` | Per-OS location, see below | The Claude Desktop config file to merge into |
| `--name NAME` | `codesage` | Key under `mcpServers` |
| `--server-url URL` | `MCP_SERVER_URL` from your shell, else `http://127.0.0.1:8001` | Backend base URL. A URL containing a password is refused |
| `--api-key KEY` | `CODESAGE_API_KEY` from `backend/.env` | Written into the config's `env` block |
| `--basic-auth USER` | unset | For the prod stack behind nginx. Prompts for the password and stores it in the macOS Keychain (service `codesage-mcp`). No API key is written |
| `--dry-run` | off | Print the merged config (`CODESAGE_API_KEY` shown as `********`) and write nothing |

```bash
make install-claude ARGS="--server-url https://your-host --basic-auth alice"  # prod behind nginx
make install-claude ARGS="--name codesage-dev --api-key abc123"               # a second entry with an explicit key
```

Options go through `ARGS`. Restart Claude Desktop afterwards.

### Config file locations

| OS | Path |
| --- | --- |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` (falls back to `~\AppData\Roaming`) |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

`--basic-auth` needs the `security` command, so it works on macOS only.

### What the installer does

- **Merges one entry.** It adds or replaces `mcpServers.<name>` and keeps every other key and server. It refuses a config whose `mcpServers` is not an object.
- **Backs up first.** If the config exists, it writes `claude_desktop_config.json.bak-<YYYYMMDD-HHMMSS>` next to it, a byte-exact copy.
- **Protects the key.** Both files are written atomically (temp file, then rename) at mode 600, because they can hold the API key.
- **Refuses to overwrite a bad file.** If the config is not valid JSON, or not a JSON object, it exits with an error and changes nothing.
- **Reads the key from `backend/.env`.** `--api-key` wins. With `--basic-auth` it does not copy the backend's key, because nginx adds it. With no key found and no `--basic-auth`, it warns and writes an empty `CODESAGE_API_KEY`.
- **Keeps passwords out of the config.** A password in `--server-url` is refused, and the `--basic-auth` password is never in argv or the file.

## Manual install

Copy `claude_desktop_config.example.json` into your Claude Desktop config and set the absolute launcher path and key:

```json
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

### The launcher

`mcp_launcher.sh` does three things:

- **Finds Python.** It exits with `.venv/bin/python not found` if the virtualenv is missing.
- **Looks up the basic-auth password.** If `CODESAGE_BASIC_AUTH_USER` is set, `CODESAGE_BASIC_AUTH_PASSWORD` is not, and `security` exists, it reads the password from the Keychain (`security find-generic-password -s codesage-mcp -a <user> -w`). A missing entry gives an empty password.
- **Starts the bridge.** `cd backend && exec .venv/bin/python -m codesage_mcp`.

## Bridge settings

All settings come from the environment, which Claude Desktop fills from the `env` block.

| Variable | Default | Notes |
| --- | --- | --- |
| `MCP_SERVER_URL` | `http://127.0.0.1:8001` | Backend base URL. Trailing `/` is removed; requests go to `/api/v1/ai/...` |
| `CODESAGE_API_KEY` | unset | Sent as `X-API-Key` |
| `CODESAGE_BASIC_AUTH_USER` | unset | Login for the prod nginx |
| `CODESAGE_BASIC_AUTH_PASSWORD` | unset | Normally supplied by the launcher from the Keychain |
| `CODESAGE_ALLOW_INSECURE_AUTH` | unset | `1` allows the key or login over plain `http://` to a non-loopback host |
| `CODESAGE_MCP_LOG_LEVEL` | `INFO` | Python log level for stderr |

Request behaviour:

- **Plain-http refusal.** If a key, a login or a `user:password@` in the URL would go over `http://` to a host other than `127.0.0.1`, `localhost` or `::1`, a tool call or resource read returns an error and sends nothing. Use an `https://` URL, or set `CODESAGE_ALLOW_INSECURE_AUTH=1` on a trusted network.
- **Retry.** A failed connection (refused, or a connect timeout) is retried once. After the second failure the call errors with "not reachable".
- **Timeout.** 30 seconds per request.
- **Redaction.** Messages and logs show the URL without any `user:password@`. The startup log line records only whether a key is set, never its value.

## Tools

`repository` accepts the numeric ID, the name, or `owner/name`; `list_repositories` shows them. Matching on name and `owner/name` ignores case.

- **Ambiguous names.** If more than one repository matches, the call errors, lists the candidates with their IDs, and asks for the numeric ID.
- **Unknown or out-of-range IDs.** The error lists the available repositories. IDs longer than 19 digits are treated as not found.

### `list_repositories`

Lists indexed repositories with `id`, `name`, `url`, `branch`, `status`, `total_files`, `total_entities`, `error_message` and `processed_at`. No arguments.

### `search_code`

Full-text search over functions, classes, imports and doc sections. Each result has the entity name and type, file path, line range, language, a signature, a snippet and a GitHub link.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `query` | string, required | | At least 1 character |
| `repository` | string | all repositories | A named repository must have status `completed` |
| `language` | string | | For example `python` |
| `entity_type` | `function`, `class`, `import`, `doc_section` | | |
| `limit` | integer 1-50 | 10 | Results per page |
| `page` | integer >= 0 | 0 | Zero-based |

- **Truncation.** Snippets are cut at 600 characters, and signatures and descriptions at 300.
- **Errors.** Any Algolia failure becomes the generic "Search is unavailable; try again later". The detail is logged on the backend only, because it can name the Algolia host or app ID.

### `get_file`

Reads a file with line numbers, as `   12| code`.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `repository` | string, required | | |
| `path` | string, required | | Exact path; a miss suggests up to 10 close paths |
| `start_line` | integer >= 1 | 1 | |
| `end_line` | integer >= 1 | end of file | |

- **Caps.** At most 400 lines and 100,000 characters per call. The result has `total_lines`, the returned `start_line` and `end_line`, and `truncated: true` if either cap cut it short. Call again with a later `start_line` for the rest.
- **Errors.** `start_line` past the end of the file, or `end_line` before `start_line`.

### `list_definitions`

Lists definitions ordered by file path, then line.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `repository` | string, required | | |
| `path_prefix` | string | | Only files whose path starts with this |
| `entity_type` | `function`, `class`, `import`, `doc_section` | | |
| `name` | string | | Case-insensitive substring of the entity name |
| `limit` | integer 1-500 | 100 | `total` in the result counts all matches |

Signatures and descriptions are cut at 300 characters.

### `analyze_repository`

Counts and layout, no interpretation.

| Argument | Type |
| --- | --- |
| `repository` | string, required |

The result has file, line and entity totals, `entities_by_type`, `files_by_language`, `definitions_by_language`, the 10 `top_directories` by file count and the 10 `largest_files` by line count.

### `find_patterns`

Finds lines that match a literal string or a regular expression, in file path order.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `repository` | string, required | | |
| `pattern` | string, required | | 1-200 characters |
| `regex` | boolean | false | An invalid expression is an error |
| `path_glob` | string | | Matched against the whole path, case-sensitive, for example `src/*.py` |
| `max_results` | integer 1-500 | 100 | `truncated: true` when more matches exist |

- **Match text.** Each match is `file_path`, `line` and `text` (trimmed, cut at 300 characters).
- **Regex limits.** A file gets 1 second and the whole call gets 10 seconds. Files over 1,000,000 characters are skipped. A call that runs out of time returns `truncated: true`.
- **Skipped files.** They appear as `skipped_files` (the first 50) with `skipped_count` for the total. Both are absent when nothing was skipped.
- **Literal search** has no time limits.

## Resources

The bridge also answers `resources/list` and `resources/read`. Reading needs the API key, because the file list is not exposed by any public endpoint.

| URI | Content |
| --- | --- |
| `codesage://repositories` | The same data as `list_repositories` |
| `codesage://repositories/{id}/files` | `repository`, `total_files`, `truncated`, and `files` with path, language and line count. At most the first 5000 files; `truncated` is true when there are more |

`{id}` is the numeric ID only. An unknown URI or ID is a "Resource not found" error.

## HTTP endpoints

The bridge uses these under `/api/v1/ai`. You can call them directly. "Key" means the `X-API-Key` header, required when the backend has `CODESAGE_API_KEY` set. Limits are per client address.

| Endpoint | Key | Rate limit | Purpose |
| --- | --- | --- | --- |
| `GET /mcp/capabilities` | no | none | Server name, version, tool names |
| `GET /mcp/tools` | no | none | Tool list with JSON Schemas |
| `POST /mcp/tools/call` | yes | 30/minute | Run a tool |
| `GET /mcp/resources` | no | none | Resource list |
| `GET /mcp/resources/read?uri=...` | yes | 30/minute | Read a resource |
| `GET /search/suggestions` | yes | 100/minute | Entity names for auto-complete |

```bash
curl -X POST http://127.0.0.1:8001/api/v1/ai/mcp/tools/call \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"tool_name": "search_code", "arguments": {"query": "parse", "limit": 3}}'  # response: {"tool", "result", "is_error", "error"}
```

- **Tool failure.** A failure such as an unknown repository returns 200 with `is_error: true` and the message in `error`.
- **Status codes.** Unknown tool is 404, invalid arguments are 422, a missing or wrong key is 401, and too many requests is 429. An unknown resource is 404.
- **Other guards.** The request guard still applies: with a key set, a `Host` that is not allowed gets 403. See [Security in the README](../README.md#security).

## How failures reach Claude

| Backend result | Tool error text |
| --- | --- |
| Not reachable after one retry | `CodeSage backend not reachable at <url>; start it with `make start-backend`` |
| Other transport error | `CodeSage backend request failed: <type>: <message>` |
| 401 with a Basic `WWW-Authenticate` | `The proxy in front of CodeSage rejected the login (401)...` |
| 401 | `CodeSage backend rejected the API key (401)...` |
| 404 | `Unknown tool '<name>' (404)` |
| 422 | `Invalid arguments for '<name>' (422)` with the details |
| 429 | `CodeSage backend rate limit exceeded (429); wait a moment and retry` |
| 5xx | `CodeSage backend error (<status>)` with the detail |
| 200 that is not a JSON object | `CodeSage backend returned an unexpected response; check MCP_SERVER_URL` |
| Bad arguments, caught by the bridge | `Invalid arguments for '<name>': <field>: <reason>`, nothing is sent |

Resource reads fail as MCP protocol errors instead of tool errors, with the same causes.

## Troubleshooting

Read the bridge's stderr in Claude Desktop's MCP log for the `codesage` server.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `CodeSage backend not reachable at ...` | Backend not running, or `MCP_SERVER_URL` is wrong | `make start-backend`, or correct the URL in the config. `tools/list` still works meanwhile |
| `rejected the API key (401)` | `CODESAGE_API_KEY` in the Claude config differs from `backend/.env` | Re-run `make install-claude` |
| `The proxy ... rejected the login (401)` | Wrong user, or no Keychain entry for it | Re-run the installer with `--basic-auth USER` and enter the password again |
| `Refusing to send the CodeSage key or login over plain http` | A remote `http://` URL with a key or login | Use `https://`, or set `CODESAGE_ALLOW_INSECURE_AUTH=1` on a trusted network |
| `rate limit exceeded (429)` | More than 30 tool calls or resource reads a minute from one address | Wait and retry |
| `returned an unexpected response; check MCP_SERVER_URL` | The URL points at something that is not the CodeSage backend | Point `MCP_SERVER_URL` at the backend root, without `/api/v1` |
| `Invalid arguments for ...` | A wrong or unknown argument | Match the argument tables above |
| `Repository '...' is not searchable yet (status: ...)` | The repository is still indexing, or failed | Wait, or reprocess it; `error_message` in `list_repositories` says why |
| `Search is unavailable; try again later` | Algolia failed or is not configured | Check `ALGOLIA_*` in `backend/.env` and the backend log |
| Tools are listed but searches return nothing | No repository has finished indexing | Check `GET /api/v1/repositories/` for status and `error_message` |
| `.venv/bin/python not found` (launcher) | No virtualenv | `make setup` |
| Server missing in Claude Desktop | Config not reloaded | Restart Claude Desktop |

## Checking the bridge with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector ./mcp_launcher.sh  # run from the repo root
```

Set `MCP_SERVER_URL` and `CODESAGE_API_KEY` in the Inspector's environment fields, or export them first. You should see six tools under Tools. With the backend running, calling one returns JSON.

## Known limitations

- **Backend must be running.** The bridge does not start it.
- **Single process.** The backend keeps job state in memory, so run one worker.
- **Rate limits are per address.** The 30 per minute on tool calls and resource reads is shared by everything behind one IP, such as nginx in the prod stack.
- **Cross-repository search.** `search_code` without `repository` includes repositories that are being reprocessed.
- **No prompts.** The server offers tools and resources only.
