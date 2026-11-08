# MCP integration guide

How to connect an MCP client (Claude Desktop, Cursor, VS Code, Windsurf or any other) to CodeSage: the installer, the stdio bridge's settings, the eight tools and the resources it serves, the backend endpoints behind them, and what to do when a call fails. For the end-to-end picture, including the tool-call sequence diagram, see the [root README](../README.md#using-it-from-an-mcp-client).

## Contents

- [How the pieces fit](#how-the-pieces-fit)
- [Prerequisites](#prerequisites)
- [Install into an MCP client](#install-into-an-mcp-client)
- [Manual install](#manual-install)
- [Connect over HTTP](#connect-over-http)
- [Bridge settings](#bridge-settings)
- [Tools](#tools)
- [Resources](#resources)
- [Prompts](#prompts)
- [HTTP endpoints](#http-endpoints)
- [How failures reach your assistant](#how-failures-reach-your-assistant)
- [Troubleshooting](#troubleshooting)
- [Checking the bridge with the MCP Inspector](#checking-the-bridge-with-the-mcp-inspector)
- [Known limitations](#known-limitations)

## How the pieces fit

Your MCP client starts `mcp_launcher.sh`. The launcher runs `python -m codesage_mcp` (the bridge) from `backend/`, using `.venv/bin/python` at the repo root. The bridge is built on the `mcp` Python SDK (pinned in `backend/requirements.txt`) and forwards each tool call as an HTTP request to the backend.

- **Schemas live in the bridge.** `tools/list` is answered from `backend/codesage_mcp/schemas.py`, so it works while the backend is down. Only tool calls, `resources/list` and resource reads need the backend.
- **Arguments are checked twice.** The bridge validates them first, then the backend validates them again. Unknown arguments are rejected in both places.
- **Logs go to stderr.** stdout carries the protocol only.

## Prerequisites

- **Virtualenv.** `.venv` exists at the repo root (`make setup`).
- **Backend config.** `backend/.env` has your Algolia credentials, and `CODESAGE_API_KEY`, which `make setup`, `make start` and `make install-claude` generate if it is missing (and copy to `frontend/.env`). To rotate it, delete the line, run `make setup` and `make install-claude`, then restart your client. Those targets also replace a leftover `your-...-here` key, but the backend itself uses such a key as is. For `ALGOLIA_APP_ID`, `ALGOLIA_ADMIN_API_KEY` and `GITHUB_TOKEN`, an empty value or a `your-...-here` placeholder counts as unset; without Algolia, search fails with a clear message.
- **Backend running.** `make start-backend`, with at least one repository in status `completed`. Every tool refuses a repository that is `failed`, `pending` or `processing`.

## Install into an MCP client

```bash
make install-claude                 # merge CodeSage into the Claude Desktop config
make install-cursor                 # the same for Cursor
make install-vscode                 # the same for VS Code
make install-windsurf               # the same for Windsurf
make install-claude ARGS=--dry-run  # print the CodeSage entry with the key masked; nothing is written
```

`make install-claude` runs `.venv/bin/python scripts/install_claude_desktop.py $(ARGS)`; the other targets add `--client cursor`, `vscode` or `windsurf`. It uses only the standard library. Only Claude Desktop has been tested end to end; the others write the format their docs describe.

### Options

| Option | Default | Notes |
| --- | --- | --- |
| `--client NAME` | `claude` | `claude` (Claude Desktop), `cursor`, `vscode` or `windsurf`. Picks the default config path and the key servers are listed under |
| `--config PATH` | Per client and OS, see below | The config file to merge into |
| `--name NAME` | `codesage` | The server's name in the config |
| `--server-url URL` | `MCP_SERVER_URL` from your shell, else `http://127.0.0.1:8001` | Backend base URL. Must be an `http(s)` URL with a host. A URL containing a password is refused |
| `--api-key KEY` | None for a local `http://` backend, whose key the launcher reads from `backend/.env`; otherwise `CODESAGE_API_KEY` from `backend/.env` | Written into the config's `env` block |
| `--basic-auth USER` | unset | For the prod stack behind nginx. Prompts for the password and stores it in the macOS Keychain (service `codesage-mcp`). No API key is written |
| `--dry-run` | off | Print only the CodeSage entry (`CODESAGE_API_KEY` shown as `********`; other servers are never printed, since their `env` blocks often hold tokens) and write nothing. `make install-claude` still runs `scripts/ensure_api_key.py` first, so a missing key is generated in `backend/.env` and copied to `frontend/.env` even on a dry run |

```bash
make install-claude ARGS="--server-url https://your-host --basic-auth alice"  # prod behind nginx
make install-claude ARGS="--name codesage-dev --api-key abc123"               # a second entry with an explicit key
```

Options go through `ARGS`. Restart the client afterwards.

### Config file locations

| Client | Servers key | macOS | Windows | Linux |
| --- | --- | --- | --- | --- |
| Claude Desktop | `mcpServers` | `~/Library/Application Support/Claude/claude_desktop_config.json` | `%APPDATA%\Claude\claude_desktop_config.json` | `~/.config/Claude/claude_desktop_config.json` |
| Cursor | `mcpServers` | `~/.cursor/mcp.json` | `%USERPROFILE%\.cursor\mcp.json` | `~/.cursor/mcp.json` |
| VS Code (user profile) | `servers`, with `"type": "stdio"` | `~/Library/Application Support/Code/User/mcp.json` | `%APPDATA%\Code\User\mcp.json` | `~/.config/Code/User/mcp.json` |
| Windsurf | `mcpServers` | `~/.codeium/windsurf/mcp_config.json` | `%USERPROFILE%\.codeium\windsurf\mcp_config.json` | `~/.codeium/windsurf/mcp_config.json` |

`%APPDATA%` falls back to `~\AppData\Roaming`. VS Code allows comments in `mcp.json`; the installer refuses a file it can't parse as plain JSON, so add the entry by hand there.

`--basic-auth` needs the `security` command, so it works on macOS only.

### What the installer does

- **Merges one entry.** It adds or replaces `<servers key>.<name>` (`mcpServers`, or `servers` for VS Code) and keeps every other key and server. It refuses a config whose servers key is not an object.
- **Backs up first.** If the config exists, it writes `<config file>.bak-<YYYYMMDD-HHMMSS>-<pid>` next to it (a `-1`, `-2` suffix if the name is taken), a byte-exact copy.
- **Protects the key.** Both files are written atomically (temp file, flushed to disk, then rename) at mode 600, because they can hold the API key. A config that is a symlink, such as one kept in a dotfiles repository, stays a link: the installer writes to the file it points to.
- **Refuses to overwrite a bad file.** If the config is not valid JSON, or not a JSON object, it exits with an error and changes nothing. A config it can't read, or a folder it can't write to, is also a one-line error, and it checks this before touching the Keychain, so a failed run leaves no stray item.
- **Warns when the client looks missing.** If the default config folder doesn't exist, it prints a warning and creates the folder anyway. It doesn't warn when you pass `--config`.
- **Warns when Claude Desktop is running** (macOS). Claude Desktop keeps its config in memory and rewrites the file whenever it saves its own settings, which undoes the installer's change. Quit Claude Desktop, run the installer, then reopen it.
- **Leaves a local key out.** For a local `http://` backend (`127.0.0.1`, `localhost` or `[::1]`, the launcher's own test) it writes no key: the launcher reads it from `backend/.env` on every start, so a regenerated key can't leave the client behind, and the client never displays it. For any other URL it copies `CODESAGE_API_KEY` from `backend/.env`. `--api-key` wins either way, and with `--basic-auth` it copies none, because nginx adds it. `make install-claude` first generates the key if `backend/.env` has none. Run directly for a non-local URL with no key found, it warns and writes none.
- **Keeps passwords out of the config.** A password in `--server-url` is refused, and the `--basic-auth` password is never in argv or the file.

## Manual install

Copy `claude_desktop_config.example.json` into your client's config and set the absolute launcher path and key. VS Code lists servers under `servers` and wants `"type": "stdio"` in the entry; Claude Desktop, Cursor and Windsurf use `mcpServers` as below. Other stdio clients take the same `command` and `env` in their own format. For a local backend you can leave `CODESAGE_API_KEY` out, and the launcher reads it from `backend/.env`:

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

Codex (its CLI and its app share `~/.codex/config.toml`) adds it with its own command. It rewrites the whole file in its own format, so back the file up first:

```bash
codex mcp add codesage --env MCP_SERVER_URL=http://127.0.0.1:8001 -- /absolute/path/to/codesage-algolia-challenge/mcp_launcher.sh
```

ChatGPT connects only to remote MCP servers set up in ChatGPT's settings, so it can't run this local stdio bridge. It can reach a backend on the internet at `/mcp`; see [Connect over HTTP](#connect-over-http).

### More MCP clients

These clients were checked against a local backend, with no key in their config. Back up the config file before adding the entry.

| Client | Config file | Add it with |
| --- | --- | --- |
| Claude Code | `~/.claude.json` (user scope) | `claude mcp add -s user codesage -e MCP_SERVER_URL=http://127.0.0.1:8001 -- /absolute/path/to/codesage-algolia-challenge/mcp_launcher.sh` |
| Gemini CLI | `~/.gemini/settings.json` (user scope) | `gemini mcp add -s user codesage /absolute/path/to/codesage-algolia-challenge/mcp_launcher.sh -e MCP_SERVER_URL=http://127.0.0.1:8001` |
| Qwen Code | `~/.qwen/settings.json` (user scope) | `qwen mcp add -s user codesage /absolute/path/to/codesage-algolia-challenge/mcp_launcher.sh -e MCP_SERVER_URL=http://127.0.0.1:8001` |
| LM Studio | `~/.lmstudio/mcp.json` | No command: put the JSON from [Manual install](#manual-install) in the file, without `CODESAGE_API_KEY`. A running LM Studio picks it up |

To check it:

- **CLIs:** `claude mcp list`, `gemini mcp list` and `qwen mcp list` show `codesage` as Connected.
- **Gemini CLI:** with folder trust on (`security.folderTrust.enabled`), it loads MCP servers only in a trusted folder. Elsewhere `gemini mcp list` shows `codesage` as Disabled.
- **LM Studio:** open a chat, open the right sidebar's Integrations tab, and turn on `mcp/codesage`. It lists the eight tools.

### The launcher

`mcp_launcher.sh` does four things:

- **Finds Python.** It exits with `.venv/bin/python not found. Run `make setup`...` if the virtualenv is missing, and with "the Python dependencies are missing" if `codesage_mcp` or `mcp` can't be imported. Both messages say to run `make setup`.
- **Fills in a local key.** If neither `CODESAGE_API_KEY` nor `CODESAGE_BASIC_AUTH_USER` is set and `MCP_SERVER_URL` is a loopback `http://` address (the default), it reads `CODESAGE_API_KEY` from `backend/.env`, so a regenerated key can't leave the client behind. A remote server keeps its own key.
- **Looks up the basic-auth password.** If `CODESAGE_BASIC_AUTH_USER` is set, `CODESAGE_BASIC_AUTH_PASSWORD` is not, and `security` exists, it reads the password from the Keychain (`security find-generic-password -s codesage-mcp -a <user> -w`). A missing entry gives an empty password and a warning on stderr.
- **Starts the bridge.** `cd backend && exec .venv/bin/python -m codesage_mcp`.

## Connect over HTTP

Clients that connect to a URL instead of starting a program, such as ChatGPT or a remote agent, use the backend's own MCP endpoint at `/mcp` (MCP's streamable HTTP transport). It serves the same tools, resources and prompts as the bridge, with the same answers, from inside the backend. Each request stands alone, so no session is kept between them.

- **Key.** With `CODESAGE_API_KEY` set, send it as `Authorization: Bearer <key>` or as `X-API-Key`; without it the answer is `401`. Behind the prod nginx, sign in with basic auth (`Authorization: Basic ...`) and nginx adds the key.
- **Read-only.** On a `READ_ONLY=true` server no key is needed, and `tools/list` leaves out `add_repository`. The public demo is one: `https://codesage-demo.vercel.app/mcp`.
- **Limit.** `RATE_LIMIT_AI` (30 per minute) per client address. Every request counts, `initialize` and `tools/list` included.
- **Host.** The `Host` header must be allowed, as for the rest of the API: loopback, a `CORS_ORIGINS` host or an `ALLOWED_HOSTS` entry.

```bash
curl -X POST https://your-host/mcp -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" -H "Authorization: Bearer $CODESAGE_API_KEY" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

**ChatGPT.** Add the server under Settings, Plugins, then Add, then **Add custom MCP server**. Give it the `/mcp` URL and set Authentication to **No authentication**. ChatGPT's other choices are OAuth, which CodeSage doesn't serve, and both together. ChatGPT can't send a key or a basic-auth login, so it can connect only to a read-only server such as the demo. Its "Allow read-only tools" permission follows the tools' `readOnlyHint`. Checked on the demo: asked to find `createStore`, ChatGPT called `search_code` and answered with zustand's `src/vanilla.ts`, lines 99–100. Its requests carry the User-Agent `openai-mcp/1.0.0 (Codex)`, which the backend logs with each tool call.

**Codex.** `codex mcp add <name> --url https://your-host/mcp` adds it as a streamable HTTP server. Checked on the demo: Codex (`codex-mcp-client`) connects and lists the tools. Calling one needs a Codex model turn, which hasn't been tested.

## Bridge settings

All settings come from the environment, which the MCP client fills from the `env` block.

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

A successful tool call answers with one JSON object, sent twice: as `structuredContent`, which matches the tool's `outputSchema` in `tools/list`, and as the same JSON in a text block for clients that predate structured results. The schemas live in `backend/codesage_mcp/schemas.py` next to the argument models. They list the top-level fields and allow extra ones, so a new field in a later version doesn't break a client that validates. A failed call is text only, with `isError` set; see [How failures reach your assistant](#how-failures-reach-your-assistant). `GET /mcp/tools` returns the same `outputSchema` beside each `inputSchema`.

`repository` accepts the numeric ID, the name, or `owner/name`; `list_repositories` shows them. Matching on name and `owner/name` ignores case.

- **Not ready.** Every tool except `list_repositories` and `add_repository` refuses a repository that isn't `completed`. A failed one gives the reason from `error_message` and says to reprocess it. A `pending` or `processing` one shows progress, such as "still indexing (120/400 files)".
- **Ambiguous names.** If more than one repository matches, the call errors, lists the candidates with their IDs, and asks for the numeric ID.
- **Unknown or out-of-range IDs.** The error lists the available repositories. IDs longer than 19 digits are treated as not found.

### `list_repositories`

Lists indexed repositories with `id`, `name`, `url`, `branch`, `commit_sha`, `status`, `total_files`, `total_entities`, `error_message` and `processed_at`. No arguments.

### `search_code`

Full-text search over functions, classes (including interfaces, type aliases and enums), doc sections and Terraform blocks. Imports are searched only when `entity_type` is `"import"`. The query is at most 512 bytes. Each result has its repository (`repository_id` and `repository`, the name), the entity name and type, file path, line range, language, a signature, a snippet and a source link.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `query` | string, required | | At least 1 character |
| `repository` | string | all repositories | A named repository must have status `completed` |
| `language` | string | | For example `python` |
| `entity_type` | `function`, `class`, `import`, `doc_section`, `terraform_block` | | |
| `limit` | integer 1-50 | 10 | Results per page |
| `page` | integer >= 0 | 0 | Zero-based |
| `mode` | `keyword`, `semantic` | `keyword` | `semantic` ranks definitions by meaning; it needs `EMBEDDING_API_KEY` on the server |

- **Semantic mode.** The query is embedded with the server's provider and compared (cosine) with the stored vectors of definitions from the same model. Hits have the same fields plus `score`, and an empty `snippet`. Without a repository it searches every `completed` repository, leaving out one being reindexed. Without a key it fails with a message naming `EMBEDDING_API_KEY`. Vectors exist only for repositories indexed since the key was set: reprocess older ones.
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

### `find_references`

Finds where a function, class or other name is defined and used. Ask *"Where is `createStore` used in zustand?"*.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `repository` | string, required | | |
| `name` | string, required | | One identifier: letters, digits, `_` and `$`, not starting with a digit, at most 200 characters. No dots; for a method, pass the method's name |
| `path_glob` | string | | As in `find_patterns` |
| `max_results` | integer 1-500 | 100 | `truncated: true` when more uses exist |

- **Definitions.** Functions and classes with exactly that name, in the files `path_glob` matches: `entity_type`, `file_path`, `line_start`, `line_end` and `signature`. Their first lines are not counted as uses.
- **Uses.** Each one is `file_path`, `line`, `text`, `kind` (`import` when the line is inside an indexed import, else `reference`) and `in`, the innermost function or class containing it (`null` at the top level or in docs). `total_references` and `files` count them.
- **Matching.** Case-sensitive and whole-word, where `$` counts as part of a name, so `store` doesn't match `$store` or `storeKey`. It is a text match, so comments, strings and Markdown count too.
- **Order.** Source files first, then tests, then Markdown and other files, each in path order. That's the indexer's order, so with `max_results` the code comes first.
- **Limits.** The same time limits and skipped-file reporting as a regex `find_patterns`.

### `add_repository`

Adds a repository and starts indexing it. It returns `repository_id`, `name`, `status` and a message; indexing runs in the background, so follow it with `list_repositories` and search once the status is `completed`.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `url` | string, required | | https URL of the repository |
| `branch` | string | default branch | A branch in the URL (`/tree/dev`) is understood too |
| `description` | string | | Optional note |

- **Same checks as the dashboard.** A duplicate URL (case-insensitive), a missing Algolia setup, and a missing repository or branch are refused before anything is created.
- **Needs the API key,** like every tool call, and counts toward the 30 per minute limit.
- **Errors.** A bad URL gives a message that starts with `url:` and says why (a scheme other than https, credentials or a port, `localhost` or a private IP address). `http://` and `git@host:path` URLs are rewritten to `https://` first, so they are accepted. A duplicate gives `<name> is already added as repository <id>.` Other refusals use the messages below.

| Message | Cause |
| --- | --- |
| `<host>/<path> was not found or is private; only public repositories are supported on <host>.` | The repository doesn't exist, or it is private on a host other than github.com that has no token in `GIT_HOST_CREDENTIALS` |
| `<host> rejected the token in GIT_HOST_CREDENTIALS or it lacks access to <path>.` | The host has a token, but the token is wrong or expired, can't read that repository, or the repository doesn't exist |
| `<host> redirected <path>; with a token CodeSage doesn't follow redirects, so use its current address.` | The repository moved; add it at its new URL |
| `Branch '<b>' does not exist in <host>/<path>.` | The branch is missing |
| `<host>/<path> is empty; there is nothing to index.` | No commits |
| `<host> did not respond in time; try again.` | The 10 s check timed out |
| `Could not reach <host>; try again.` | The host or git failed in some other way |
| `Search indexing is not configured on the server (Algolia credentials are missing).` | `ALGOLIA_APP_ID` or `ALGOLIA_ADMIN_API_KEY` is unset |

### Other git hosts

Ask your assistant: *"Add https://gitlab.com/group/project to CodeSage"*, then *"Search it for where requests are retried"*.

- **Hosts.** GitHub, GitLab (nested groups too), Bitbucket and self-hosted servers, over https. `http://` and `git@host:path` URLs are rewritten to `https://`. Branch URLs such as `.../-/tree/dev` or Bitbucket's `/src/<branch>` work.
- **Private repositories.** The tool takes no token. The backend reads one per host from `GIT_HOST_CREDENTIALS` in `backend/.env`, as comma-separated `host=user:token` pairs: `gitlab.com=oauth2:<token>` for GitLab (a token with `read_repository`), `bitbucket.org=x-token-auth:<token>` for Bitbucket Cloud (a repository access token), and `<host>=<user>:<token>` for Gitea and Forgejo. Restart the backend after changing it. github.com uses `GITHUB_TOKEN` instead. See the README's [Other git hosts](../README.md#other-git-hosts).
- **How it reads.** For a host other than github.com the backend runs `git ls-remote` (10 s) to check and a shallow `git clone` (120 s) to read. Git runs without a shell, a credential helper or prompts, over https only, and skips symlinks. github.com keeps the REST API path.
- **Names.** Repositories on other hosts are named `<host>/<path>`, which you can pass as `repository` to the other tools.
- **Also in the dashboard.** The Home page form and `POST /api/v1/repositories/` take the same URLs.

## Resources

The bridge also answers `resources/list` and `resources/read`. Reading needs the API key, because the file list is not exposed by any public endpoint.

| URI | Content |
| --- | --- |
| `codesage://repositories` | The same data as `list_repositories` |
| `codesage://repositories/{id}/files` | `repository`, `total_files`, `truncated`, and `files` with path, language and line count. At most the first 5000 files; `truncated` is true when there are more |

`resources/list` advertises `codesage://repositories`. `resources/templates/list` advertises `codesage://repositories/{id}/files` as a template, so a client can fill in an ID that `list_repositories` returns. The bridge builds the template list itself; the resource list and reads go through the backend.

`{id}` is the numeric ID only. An unknown URI fails with `Unknown resource '<uri>'` and an unknown ID with `Repository <id> not found`. The bridge prefixes both with `Resource or repository not found: `.

## Prompts

`prompts/list` and `prompts/get` are answered by the bridge alone (`codesage_mcp/prompts.py`), so they work with the backend down and need no key. Each prompt returns one user message that tells the assistant which tools to call, in what order, and what to answer with.

| Prompt | Arguments | Steers the assistant to |
| --- | --- | --- |
| `explain_repository` ("Explain this repository") | `repository` (required) | `analyze_repository`, then `list_definitions` (with `path_prefix`, and `entity_type: "doc_section"` for docs), then `get_file` on the README and central files. The answer covers what the repository does, its layout and main parts, and where to start, citing paths and lines |
| `find_implementation` ("Where is this implemented?") | `feature` (required), `repository` (optional; empty searches every repository) | `search_code`, then `list_definitions` around the best hits and `find_references` on a key function or class, then `get_file` to confirm. The answer gives files, line ranges and source links, or says nothing matched |

A missing required argument fails with `Prompt '<name>' needs the '<argument>' argument`, and an unknown name with `Unknown prompt '<name>'`.

## HTTP endpoints

The bridge uses these under `/api/v1/ai`. You can call them directly. "Key" means the `X-API-Key` header, required when the backend has `CODESAGE_API_KEY` set. Limits are per client address.

| Endpoint | Key | Rate limit | Purpose |
| --- | --- | --- | --- |
| `GET /mcp/capabilities` | no | none | Server name, version, tool names, and `semantic_search` (whether an embeddings key is set) |
| `GET /mcp/tools` | no | none | Tool list with JSON Schemas |
| `POST /mcp/tools/call` | yes | 30/minute | Run a tool |
| `GET /mcp/resources` | no | none | Resource list |
| `GET /mcp/resources/read?uri=...` | yes | 30/minute | Read a resource |
| `GET /search/suggestions` | yes | 100/minute | Entity names for auto-complete; `mode=semantic` names the definitions closest in meaning |

```bash
curl -X POST http://127.0.0.1:8001/api/v1/ai/mcp/tools/call \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"tool_name": "search_code", "arguments": {"query": "parse", "limit": 3}}'  # response: {"tool", "result", "is_error", "error"}
```

- **Tool failure.** A failure such as an unknown repository, or a repository that failed or is still indexing, returns 200 with `is_error: true` and the message in `error`.
- **Status codes.** Unknown tool is 404, invalid arguments are 422, a missing or wrong key is 401, and too many requests is 429 with `Retry-After`. An unknown resource is 404. An unexpected failure is 500 with `{detail, request_id}`.
- **Other guards.** The request guard still applies: with a key set, a `Host` that is not allowed gets 403. See [Security in the README](../README.md#security).

## How failures reach your assistant

| Backend result | Tool error text |
| --- | --- |
| `MCP_SERVER_URL` is not `http(s)://host` | `MCP_SERVER_URL must start with http:// or https:// (got '<url>')`, nothing is sent |
| Not reachable after one retry | `CodeSage backend not reachable at <url>; start it with `make start-backend``. For a host other than loopback: `...; check MCP_SERVER_URL and that the host is up` |
| No answer in 30 s | `CodeSage backend did not answer within 30 s.` |
| Other transport error | `CodeSage backend request failed: <type>: <message>` |
| 401 with a Basic `WWW-Authenticate` | `The proxy in front of CodeSage rejected the login (401)...` |
| 401, no key configured | `No API key is configured; set CODESAGE_API_KEY in the MCP server's env in your MCP client's config (run `make install-claude`, or install-cursor, install-vscode or install-windsurf).` For a local backend the launcher reads the key from `backend/.env` when the config leaves it empty, so this means that file has no key either |
| 401, key sent | `CodeSage backend rejected the API key (401); check CODESAGE_API_KEY in the MCP server config` |
| 403 | `CodeSage refused the request (403): <detail>. If the backend runs on another host, add that host to ALLOWED_HOSTS on the backend and check MCP_SERVER_URL.` |
| 404 | `The backend returned 404 for <path>; check that MCP_SERVER_URL points at the backend root (no /api/v1).` Unknown tool names never get this far: the bridge answers `Unknown tool '<name>'. Available tools: ...` itself |
| 422 | `Invalid arguments for '<name>' (422)` with the details |
| 429 | `CodeSage backend rate limit exceeded (429); wait a moment and retry` |
| 5xx with a JSON body | `CodeSage backend error (<status>): <detail>`, plus `(request <id>)` when there is a request ID. A 500 always has one |
| 5xx without JSON (a proxy's HTML page) | `CodeSage backend error (<status>); the backend or the proxy in front of it may be down.` The body is not echoed |
| Any other non-200 | `Unexpected response from CodeSage backend (<status>): <detail>` |
| 200 that is not a JSON object, or whose `result` is not one | `CodeSage backend returned an unexpected response; check MCP_SERVER_URL` |
| 200 with `is_error: true` | The backend's message, for example `Repository 'x' failed to index: <reason>. Reprocess it from the dashboard.` |
| 200 with `is_error: true` from `add_repository` | The refusal text, such as `<host>/<path> was not found or is private; only public repositories are supported on <host>.`; see [`add_repository`](#add_repository) |
| Bad arguments, caught by the bridge | `Invalid arguments for '<name>': <field>: <reason>`, nothing is sent |

Resource reads fail as MCP protocol errors instead of tool errors, with the same wording. The one difference is a 404 with a JSON body, which reads `Resource or repository not found: <detail>`.

## Troubleshooting

Read the bridge's stderr in your client's MCP log for the `codesage` server (Cursor and VS Code show it in the Output panel). For Claude Desktop on macOS, that is `~/Library/Logs/Claude/mcp-server-codesage.log`; the file is named after the key under `mcpServers`, so a second entry made with `--name` has its own log.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `CodeSage backend not reachable at ...` | Backend not running, or `MCP_SERVER_URL` is wrong | `make start-backend`, or correct the URL in the config. `tools/list` still works meanwhile |
| `rejected the API key (401)` | `CODESAGE_API_KEY` in the client's config differs from `backend/.env` | Re-run `make install-claude` (or your client's target) |
| `The proxy ... rejected the login (401)` | Wrong user, or no Keychain entry for it | Re-run the installer with `--basic-auth USER` and enter the password again |
| `Refusing to send the CodeSage key or login over plain http` | A remote `http://` URL with a key or login | Use `https://`, or set `CODESAGE_ALLOW_INSECURE_AUTH=1` on a trusted network |
| `refused the request (403)` | The backend runs on another host, and its `Host` isn't allowed | Add the host to `ALLOWED_HOSTS` on the backend, and check `MCP_SERVER_URL` |
| `The backend returned 404 for ...` | `MCP_SERVER_URL` points at the wrong place | Point it at the backend root, without `/api/v1` |
| `did not answer within 30 s` | The backend is overloaded, or something in front of it is stuck | Check the backend log, then retry |
| `CodeSage backend error (500) ... (request <id>)` | An unexpected backend error | Find the request ID in the backend log |
| `No API key is configured` | The backend needs a key, and the client's config has none | Re-run `make install-claude` (or your client's target), or set `CODESAGE_API_KEY` in the server's `env` |
| `rate limit exceeded (429)` | More than 30 tool calls or resource reads a minute from one address | Wait and retry |
| `returned an unexpected response; check MCP_SERVER_URL` | The URL points at something that is not the CodeSage backend | Point `MCP_SERVER_URL` at the backend root, without `/api/v1` |
| `Invalid arguments for ...` | A wrong or unknown argument | Match the argument tables above |
| `Repository '...' failed to index: ...` | Indexing failed; the message is the reason | Fix the cause, then reprocess it from the dashboard |
| `Repository '...' is still indexing (n/m files)` | It is `pending` or `processing`. Every tool except `list_repositories` and `add_repository` refuses it | Wait for it to complete |
| `... was not found or is private; only public repositories are supported on <host>.` | `add_repository` on a private or missing repository, on a host other than github.com | Check the URL, or add a token for the host to `GIT_HOST_CREDENTIALS` and restart the backend |
| `<host> rejected the token in GIT_HOST_CREDENTIALS ...` | The host's token is wrong, expired or lacks read access, or the repository doesn't exist | Check the URL, the token's scope (GitLab: `read_repository`) and the entry's `user:` part |
| `url: ...` from `add_repository` | The URL isn't an https repository URL (port, credentials, `localhost` and private IPs are refused) | Use the plain https URL |
| `Search is not configured on the server` | `ALGOLIA_APP_ID` or `ALGOLIA_ADMIN_API_KEY` is empty or still a placeholder | Set them in `backend/.env` and restart the backend |
| `Search is unavailable; try again later.` | Algolia is unreachable or rejected the query | Check the backend log; the detail is logged there only |
| Tools are listed but searches return nothing | No repository has finished indexing | Check `GET /api/v1/repositories/` for status and `error_message` |
| `.venv/bin/python not found` or `Python dependencies are missing` (launcher) | No virtualenv, or the dependencies aren't installed in it | `make setup` |
| `no Keychain password found for ...` (launcher) | `CODESAGE_BASIC_AUTH_USER` is set but its Keychain entry is missing | Re-run the installer with `--basic-auth USER` |
| Server missing in the client | Config not reloaded | Restart the client |

## Checking the bridge with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector ./mcp_launcher.sh  # run from the repo root
```

Set `MCP_SERVER_URL` and `CODESAGE_API_KEY` in the Inspector's environment fields, or export them first. You should see eight tools under Tools, each with an output schema. With the backend running, calling one returns JSON, both as structured content and as text.

## Known limitations

- **Backend must be running.** The bridge does not start it.
- **More than one API process needs Redis.** Rate limits and, with `INDEX_WORKERS=inline`, job state live in each process's memory. So `API_WORKERS` above 1 needs `INDEX_WORKERS=external` and `RATE_LIMIT_STORAGE_URL` (Redis), or the backend refuses to start.
- **Rate limits are per address.** The 30 per minute on tool calls and resource reads is shared by everything behind one IP, such as nginx in the prod stack.
- **One token per host.** Private repositories on other hosts need the backend's `GIT_HOST_CREDENTIALS`, which holds one token for each host. `add_repository` and the dashboard can't pass a token of their own.
- **Cross-repository search.** `search_code` without `repository` includes repositories that are being reprocessed.
