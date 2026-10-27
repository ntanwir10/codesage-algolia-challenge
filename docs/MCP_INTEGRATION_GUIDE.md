# MCP integration guide

How to connect Claude Desktop (or any MCP client) to CodeSage: the installer, the stdio bridge's settings, the seven tools and the resources it serves, the backend endpoints behind them, and what to do when a call fails. For the end-to-end picture, including the tool-call sequence diagram, see the [root README](../README.md#using-it-from-claude-desktop).

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
- **Backend config.** `backend/.env` has your Algolia credentials, and `CODESAGE_API_KEY`, which `make setup`, `make start` and `make install-claude` generate if it is missing (and copy to `frontend/.env`). To rotate it, delete the line, run `make setup` and `make install-claude`, then restart Claude Desktop. Those targets also replace a leftover `your-...-here` key, but the backend itself uses such a key as is. For `ALGOLIA_APP_ID`, `ALGOLIA_ADMIN_API_KEY` and `GITHUB_TOKEN`, an empty value or a `your-...-here` placeholder counts as unset; without Algolia, search fails with a clear message.
- **Backend running.** `make start-backend`, with at least one repository in status `completed`. Every tool refuses a repository that is `failed`, `pending` or `processing`.

## Install into Claude Desktop

```bash
make install-claude                 # merge CodeSage into the Claude Desktop config
make install-claude ARGS=--dry-run  # print the merged config with the key masked; the Claude config is not written
```

`make install-claude` runs `.venv/bin/python scripts/install_claude_desktop.py $(ARGS)`. It uses only the standard library.

### Options

| Option | Default | Notes |
| --- | --- | --- |
| `--config PATH` | Per-OS location, see below | The Claude Desktop config file to merge into |
| `--name NAME` | `codesage` | Key under `mcpServers` |
| `--server-url URL` | `MCP_SERVER_URL` from your shell, else `http://127.0.0.1:8001` | Backend base URL. Must be an `http(s)` URL with a host. A URL containing a password is refused |
| `--api-key KEY` | `CODESAGE_API_KEY` from `backend/.env` | Written into the config's `env` block |
| `--basic-auth USER` | unset | For the prod stack behind nginx. Prompts for the password and stores it in the macOS Keychain (service `codesage-mcp`). No API key is written |
| `--dry-run` | off | Print the merged config (`CODESAGE_API_KEY` shown as `********`) and don't write the Claude Desktop config. `make install-claude` still runs `scripts/ensure_api_key.py` first, so a missing key is generated in `backend/.env` and copied to `frontend/.env` even on a dry run |

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
- **Backs up first.** If the config exists, it writes `claude_desktop_config.json.bak-<YYYYMMDD-HHMMSS>-<pid>` next to it (a `-1`, `-2` suffix if the name is taken), a byte-exact copy.
- **Protects the key.** Both files are written atomically (temp file, then rename) at mode 600, because they can hold the API key.
- **Refuses to overwrite a bad file.** If the config is not valid JSON, or not a JSON object, it exits with an error and changes nothing. A config it can't read, or a folder it can't write to, is also a one-line error, and it checks this before touching the Keychain, so a failed run leaves no stray item.
- **Warns when Claude Desktop looks missing.** If the default config folder doesn't exist, it prints a warning and creates the folder anyway. It doesn't warn when you pass `--config`.
- **Reads the key from `backend/.env`.** `--api-key` wins. With `--basic-auth` it does not copy the backend's key, because nginx adds it. `make install-claude` first generates the key if `backend/.env` has none. Run directly with no key found and no `--basic-auth`, it warns and writes an empty `CODESAGE_API_KEY`.
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

- **Finds Python.** It exits with `.venv/bin/python not found. Run `make setup`...` if the virtualenv is missing, and with "the Python dependencies are missing" if `codesage_mcp` or `mcp` can't be imported. Both messages say to run `make setup`.
- **Looks up the basic-auth password.** If `CODESAGE_BASIC_AUTH_USER` is set, `CODESAGE_BASIC_AUTH_PASSWORD` is not, and `security` exists, it reads the password from the Keychain (`security find-generic-password -s codesage-mcp -a <user> -w`). A missing entry gives an empty password and a warning on stderr.
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
- **URL check.** `MCP_SERVER_URL` must start with `http://` or `https://` and have a host. Otherwise the call errors and sends nothing.
- **Retry.** A failed connection (refused, or no connection within 5 seconds) is retried once. After the second failure the call errors with "not reachable".
- **Timeout.** 30 seconds per request. A slow answer errors with "did not answer within 30 s" and is not retried.
- **Redaction.** Messages and logs show the URL without any `user:password@`. The startup log line records only whether a key is set, never its value.

## Tools

`repository` accepts the numeric ID, the name, or `owner/name`; `list_repositories` shows them. Matching on name and `owner/name` ignores case.

- **Not ready.** Every tool except `list_repositories` and `add_repository` refuses a repository that isn't `completed`. A failed one gives the reason from `error_message` and says to reprocess it. A `pending` or `processing` one shows progress, such as "still indexing (120/400 files)".
- **Ambiguous names.** If more than one repository matches, the call errors, lists the candidates with their IDs, and asks for the numeric ID.
- **Unknown or out-of-range IDs.** The error lists the available repositories. IDs longer than 19 digits are treated as not found.

### `list_repositories`

Lists indexed repositories with `id`, `name`, `url`, `branch`, `status`, `total_files`, `total_entities`, `error_message` and `processed_at`. No arguments.

### `search_code`

Full-text search over functions, classes (including interfaces, type aliases and enums), doc sections and Terraform blocks. Imports are searched only when `entity_type` is `"import"`. The query is at most 512 bytes. Each result has the entity name and type, file path, line range, language, a signature, a snippet and a source link.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `query` | string, required | | At least 1 character |
| `repository` | string | all repositories | A named repository must have status `completed` |
| `language` | string | | For example `python` |
| `entity_type` | `function`, `class`, `import`, `doc_section`, `terraform_block` | | |
| `limit` | integer 1-50 | 10 | Results per page |
| `page` | integer >= 0 | 0 | Zero-based |

- **Plain-words queries.** If no result matches every word, Algolia drops the words that miss, ignores stop words and plurals, and returns the best partial matches. A question works as a query.
- **Source links.** Links point at the commit that was indexed (`list_repositories` reports it as `commit_sha`), so their line numbers stay right after the branch moves on. A repository indexed before commits were recorded links to its branch until it is reprocessed. GitHub gets `#L<start>-L<end>`, GitLab `/-/blob/...#L<start>-<end>` and Bitbucket `/src/...#lines-<start>:<end>`. GitLab links go to gitlab.com and to any host whose name starts with `gitlab.`; Bitbucket links only to bitbucket.org. A repository on any other host has no link.
- **Truncation.** Snippets are cut at 600 characters, and signatures and descriptions at 300.
- **Errors.** A repository that is `failed`, `pending` or `processing` is refused, as for every tool. If Algolia isn't configured, the error says `ALGOLIA_APP_ID` and `ALGOLIA_ADMIN_API_KEY` are missing. Any other Algolia failure becomes the generic "Search is unavailable; try again later." The detail is logged on the backend only, because it can name the Algolia host or app ID.

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
| `entity_type` | `function`, `class`, `import`, `doc_section`, `terraform_block` | | |
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

### `add_repository`

Adds a repository and starts indexing it. It returns `repository_id`, `name`, `status` and a message; indexing runs in the background, so follow it with `list_repositories` and search once the status is `completed`.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `url` | string, required | | https URL of the repository |
| `branch` | string | default branch | A branch in the URL (`/tree/dev`) is understood too |
| `description` | string | | Optional note |

- **Same checks as the dashboard.** A duplicate URL (case-insensitive), a missing Algolia setup, and a missing repository or branch are refused before anything is created.
- **Needs the API key,** like every tool call, and counts toward the 30 per minute limit.
- **Errors.** A bad URL gives a message that starts with `url:` and says why (a scheme other than https, credentials or a port, `localhost` or a private IP address). `http://` and `git@host:path` URLs are rewritten to `https://` first, so they are accepted. A duplicate gives "<name> is already added as repository <id>." Other refusals use the messages below.

| Message | Cause |
| --- | --- |
| `<host>/<path> was not found or is private; only public repositories are supported on <host>.` | The repository doesn't exist, or it is private (on a host other than github.com) |
| `Branch '<b>' does not exist in <host>/<path>.` | The branch is missing |
| `<host>/<path> is empty; there is nothing to index.` | No commits |
| `<host> did not respond in time; try again.` | The 10 s check timed out |
| `Could not reach <host>; try again.` | The host or git failed in some other way |
| `Search indexing is not configured on the server (Algolia credentials are missing).` | `ALGOLIA_APP_ID` or `ALGOLIA_ADMIN_API_KEY` is unset |

### Other git hosts

Ask Claude: *"Add https://gitlab.com/group/project to CodeSage"*, then *"Search it for where requests are retried"*.

- **Hosts.** GitHub, GitLab (nested groups too), Bitbucket and self-hosted servers, over https. `http://` and `git@host:path` URLs are rewritten to `https://`. Branch URLs such as `.../-/tree/dev` or Bitbucket's `/src/<branch>` work.
- **Public only.** Private repositories are refused on every host but github.com, where the backend's `GITHUB_TOKEN` can read them.
- **How it reads.** For a host other than github.com the backend runs `git ls-remote` (10 s) to check and a shallow `git clone` (120 s) to read. Git runs without a shell, a credential helper or prompts, over https only, and skips symlinks. github.com keeps the REST API path.
- **Names.** Repositories on other hosts are named `<host>/<path>`, which you can pass as `repository` to the other tools.
- **Only here.** The web dashboard and `POST /api/v1/repositories/` take github.com only.

## Resources

The bridge also answers `resources/list` and `resources/read`. Reading needs the API key, because the file list is not exposed by any public endpoint.

| URI | Content |
| --- | --- |
| `codesage://repositories` | The same data as `list_repositories` |
| `codesage://repositories/{id}/files` | `repository`, `total_files`, `truncated`, and `files` with path, language and line count. At most the first 5000 files; `truncated` is true when there are more |

`resources/list` advertises only `codesage://repositories`. The files resource is readable but not listed, so build its URI from an ID that `list_repositories` returns.

`{id}` is the numeric ID only. An unknown URI fails with `Unknown resource '<uri>'` and an unknown ID with `Repository <id> not found`. The bridge prefixes both with `Resource or repository not found: `.

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

- **Tool failure.** A failure such as an unknown repository, or a repository that failed or is still indexing, returns 200 with `is_error: true` and the message in `error`.
- **Status codes.** Unknown tool is 404, invalid arguments are 422, a missing or wrong key is 401, and too many requests is 429 with `Retry-After`. An unknown resource is 404. An unexpected failure is 500 with `{detail, request_id}`.
- **Other guards.** The request guard still applies: with a key set, a `Host` that is not allowed gets 403. See [Security in the README](../README.md#security).

## How failures reach Claude

| Backend result | Tool error text |
| --- | --- |
| `MCP_SERVER_URL` is not `http(s)://host` | `MCP_SERVER_URL must start with http:// or https:// (got '<url>')`, nothing is sent |
| Not reachable after one retry | `CodeSage backend not reachable at <url>; start it with `make start-backend``. For a host other than loopback: `...; check MCP_SERVER_URL and that the host is up` |
| No answer in 30 s | `CodeSage backend did not answer within 30 s.` |
| Other transport error | `CodeSage backend request failed: <type>: <message>` |
| 401 with a Basic `WWW-Authenticate` | `The proxy in front of CodeSage rejected the login (401)...` |
| 401, no key configured | `No API key is configured; set CODESAGE_API_KEY in the MCP server's env in your MCP client's config (for Claude Desktop, run `make install-claude`).` For a local backend the launcher reads the key from `backend/.env` when the config leaves it empty, so this means that file has no key either |
| 401, key sent | `CodeSage backend rejected the API key (401); check CODESAGE_API_KEY in the MCP server config` |
| 403 | `CodeSage refused the request (403): <detail>. If the backend runs on another host, add that host to ALLOWED_HOSTS on the backend and check MCP_SERVER_URL.` |
| 404 | `The backend returned 404 for <path>; check that MCP_SERVER_URL points at the backend root (no /api/v1).` Unknown tool names never get this far: the bridge answers `Unknown tool '<name>'. Available tools: ...` itself |
| 422 | `Invalid arguments for '<name>' (422)` with the details |
| 429 | `CodeSage backend rate limit exceeded (429); wait a moment and retry` |
| 5xx with a JSON body | `CodeSage backend error (<status>): <detail>`, plus `(request <id>)` when there is a request ID. A 500 always has one |
| 5xx without JSON (a proxy's HTML page) | `CodeSage backend error (<status>); the backend or the proxy in front of it may be down.` The body is not echoed |
| Any other non-200 | `Unexpected response from CodeSage backend (<status>): <detail>` |
| 200 that is not a JSON object | `CodeSage backend returned an unexpected response; check MCP_SERVER_URL` |
| 200 with `is_error: true` | The backend's message, for example `Repository 'x' failed to index: <reason>. Reprocess it from the dashboard.` |
| 200 with `is_error: true` from `add_repository` | The refusal text, such as `<host>/<path> was not found or is private; only public repositories are supported on <host>.`; see [`add_repository`](#add_repository) |
| Bad arguments, caught by the bridge | `Invalid arguments for '<name>': <field>: <reason>`, nothing is sent |

Resource reads fail as MCP protocol errors instead of tool errors, with the same wording. The one difference is a 404 with a JSON body, which reads `Resource or repository not found: <detail>`.

## Troubleshooting

Read the bridge's stderr in Claude Desktop's MCP log for the `codesage` server. On macOS that is `~/Library/Logs/Claude/mcp-server-codesage.log`; the file is named after the key under `mcpServers`, so a second entry made with `--name` has its own log.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `CodeSage backend not reachable at ...` | Backend not running, or `MCP_SERVER_URL` is wrong | `make start-backend`, or correct the URL in the config. `tools/list` still works meanwhile |
| `rejected the API key (401)` | `CODESAGE_API_KEY` in the Claude config differs from `backend/.env` | Re-run `make install-claude` |
| `The proxy ... rejected the login (401)` | Wrong user, or no Keychain entry for it | Re-run the installer with `--basic-auth USER` and enter the password again |
| `Refusing to send the CodeSage key or login over plain http` | A remote `http://` URL with a key or login | Use `https://`, or set `CODESAGE_ALLOW_INSECURE_AUTH=1` on a trusted network |
| `refused the request (403)` | The backend runs on another host, and its `Host` isn't allowed | Add the host to `ALLOWED_HOSTS` on the backend, and check `MCP_SERVER_URL` |
| `The backend returned 404 for ...` | `MCP_SERVER_URL` points at the wrong place | Point it at the backend root, without `/api/v1` |
| `did not answer within 30 s` | The backend is overloaded, or something in front of it is stuck | Check the backend log, then retry |
| `CodeSage backend error (500) ... (request <id>)` | An unexpected backend error | Find the request ID in the backend log |
| `No API key is configured` | The backend needs a key, and the Claude config has none | Re-run `make install-claude`, or set `CODESAGE_API_KEY` in the server's `env` |
| `rate limit exceeded (429)` | More than 30 tool calls or resource reads a minute from one address | Wait and retry |
| `returned an unexpected response; check MCP_SERVER_URL` | The URL points at something that is not the CodeSage backend | Point `MCP_SERVER_URL` at the backend root, without `/api/v1` |
| `Invalid arguments for ...` | A wrong or unknown argument | Match the argument tables above |
| `Repository '...' failed to index: ...` | Indexing failed; the message is the reason | Fix the cause, then reprocess it from the dashboard |
| `Repository '...' is still indexing (n/m files)` | It is `pending` or `processing`. Every tool except `list_repositories` and `add_repository` refuses it | Wait for it to complete |
| `... was not found or is private; only public repositories are supported on <host>.` | `add_repository` on a private or missing repository, on a host other than github.com | Make the repository public, or check the URL |
| `url: ...` from `add_repository` | The URL isn't an https repository URL (port, credentials, `localhost` and private IPs are refused) | Use the plain https URL |
| `Search is not configured on the server` | `ALGOLIA_APP_ID` or `ALGOLIA_ADMIN_API_KEY` is empty or still a placeholder | Set them in `backend/.env` and restart the backend |
| `Search is unavailable; try again later.` | Algolia is unreachable or rejected the query | Check the backend log; the detail is logged there only |
| Tools are listed but searches return nothing | No repository has finished indexing | Check `GET /api/v1/repositories/` for status and `error_message` |
| `.venv/bin/python not found` or `Python dependencies are missing` (launcher) | No virtualenv, or the dependencies aren't installed in it | `make setup` |
| `no Keychain password found for ...` (launcher) | `CODESAGE_BASIC_AUTH_USER` is set but its Keychain entry is missing | Re-run the installer with `--basic-auth USER` |
| Server missing in Claude Desktop | Config not reloaded | Restart Claude Desktop |

## Checking the bridge with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector ./mcp_launcher.sh  # run from the repo root
```

Set `MCP_SERVER_URL` and `CODESAGE_API_KEY` in the Inspector's environment fields, or export them first. You should see seven tools under Tools. With the backend running, calling one returns JSON.

## Known limitations

- **Backend must be running.** The bridge does not start it.
- **Single process.** The backend keeps job state in memory, so run one worker.
- **Rate limits are per address.** The 30 per minute on tool calls and resource reads is shared by everything behind one IP, such as nginx in the prod stack.
- **Other hosts are public only.** `add_repository` can't read private repositories except on github.com, and the dashboard can't add other hosts at all.
- **Cross-repository search.** `search_code` without `repository` includes repositories that are being reprocessed.
- **No prompts.** The server offers tools and resources only.
