# CodeSage

[![CI](https://github.com/ntanwir10/codesage-algolia-challenge/actions/workflows/ci.yml/badge.svg)](https://github.com/ntanwir10/codesage-algolia-challenge/actions/workflows/ci.yml)

**Search and read codebases from any AI assistant.** CodeSage indexes a repository's functions, classes, imports, documentation and Terraform blocks into Algolia, then serves them to any MCP client (Claude Desktop, Cursor, VS Code, Windsurf and others) as eight tools. A web dashboard adds repositories from GitHub, GitLab, Bitbucket or any https git host, shows indexing progress live and searches the index. Your assistant can add them too.

Built for the [Algolia MCP Server Challenge](https://dev.to/challenges/algolia-2025-07-09).

```mermaid
flowchart TB
    you(["You"]) --> browser["Web dashboard<br/>React + Vite"]
    you --> claude["MCP client<br/>Claude Desktop, Cursor, VS Code, ..."]
    claude -- "tools/call over stdio" --> bridge["MCP bridge"]
    browser -- "REST and WebSocket" --> nginx["nginx, prod only<br/>HTTPS, login, adds the API key"]
    bridge -- "HTTP with the API key" --> nginx
    nginx --> api["CodeSage backend<br/>FastAPI: REST, WebSocket, MCP tools"]
    api -- "starts" --> job["Indexing job"]
    job -- "fetch files" --> github["GitHub API,<br/>or git clone"]
    job -- "store" --> db[("SQLite<br/>files and entities")]
    job -- "index" --> algolia[("Algolia<br/>search index")]
    api -- "search" --> algolia
    api -- "read files" --> db
```

With `make start` there is no nginx: the dashboard and the bridge call the backend directly. The dev Docker stack (`make up`) puts a plain-HTTP nginx in front, with no login.

## Contents

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Using CodeSage](#using-codesage)
- [Security](#security)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Development](#development)
- [Known limitations](#known-limitations)

## How it works

There are two ways in, and both end at the same FastAPI backend:

- **Web dashboard** (React + Vite). Add a repository from GitHub or another git host, watch it index, and search it.
- **MCP clients** such as Claude Desktop, Cursor, VS Code or Windsurf. The client starts `mcp_launcher.sh`, which runs a small stdio MCP bridge (`backend/codesage_mcp`). The bridge turns the assistant's tool calls into HTTP calls to the backend. The assistant can search, read and also add repositories, including public ones on GitLab, Bitbucket and other git hosts.
- **Remote MCP clients** such as ChatGPT, which connect to a URL. They use the backend's own MCP endpoint at `/mcp` (streamable HTTP), with the same tools; see [Connect over HTTP](docs/MCP_INTEGRATION_GUIDE.md#connect-over-http).

Indexing runs as a background job inside the backend. Search goes to Algolia; reading files and listing definitions go to SQLite.

### Inside the backend

```mermaid
flowchart TB
    request["HTTP request or WebSocket"] --> guard["Request guard<br/>origin and host checks"]
    guard --> repos["/repositories<br/>create, reprocess, delete"]
    guard --> mcp["/ai/mcp<br/>tool calls, resources"]
    guard --> ws["/ws<br/>live status"]
    repos -- "schedules" --> job["Indexing job<br/>at most 2 at once"]
    job --> github["Fetch<br/>GitHub API or git clone"]
    job --> parser["Code parser<br/>tree-sitter, Python ast"]
    job --> db[("SQLite")]
    job --> algolia[("Algolia")]
    job -- "progress" --> ws
    mcp --> tools["MCP tools"]
    tools -- "search_code" --> algolia
    tools -- "file and definition tools" --> db
```

### Adding a repository

```mermaid
flowchart TD
    add["POST /api/v1/repositories/"] --> valid{"Valid repository URL<br/>and branch?"}
    valid -- "no" --> bad["422"]
    valid -- "yes" --> known{"Already added?"}
    known -- "yes" --> dup["409"]
    known -- "no" --> ready{"Algolia set up and<br/>repo and branch readable?"}
    ready -- "no" --> refused["422, 502, 503 or 504<br/>nothing created"]
    ready -- "yes" --> create["Create the row<br/>status pending"]
    create --> created["201 with the repository"]
    create --> schedule["Start a background job"]
    again["POST /api/v1/repositories/{id}/process"] --> busy{"Job running, or completed<br/>without force_reprocess?"}
    busy -- "yes" --> conflict["409"]
    busy -- "no" --> schedule
    schedule --> processing["Mark it processing<br/>progress back to 0"]
    processing --> slot["Wait for a run slot"]
    slot --> run["Indexing run"]
```

The dashboard shows every refusal under the repository field, or under the Branch field when it is about the branch, and stays on the Home page. Nothing is created on any of them. The table lists GitHub's messages; other hosts get the ones in [Other git hosts](#other-git-hosts).

| You see | Status | Cause |
| --- | --- | --- |
| A message about the URL or branch | 422 | Not a usable https repository URL (credentials, ports, a query, localhost and private addresses are refused), or a branch name git wouldn't accept |
| "GitHub repository owner/repo was not found" | 422 | The repository doesn't exist, or it's private and the server's `GITHUB_TOKEN` can't read it |
| "Branch 'x' does not exist", "owner/repo is empty" or "GitHub denied access" | 422 | The branch is missing, the repository has no content, or GitHub refused access |
| "owner/repo has already been added", with an "Open it" link | 409 | Same URL as an existing repository. Case doesn't matter. The body also has `repository_id` |
| "GitHub's API rate limit was reached; try again in about N minutes" | 503 | GitHub is rate-limiting the server. `Retry-After` says how long |
| "GitHub rejected the server's GITHUB_TOKEN" or "Could not reach GitHub; try again" | 502 | The token is invalid, or GitHub is down or unreachable |
| "GitHub did not respond in time; try again" | 504 | A GitHub request took longer than 10 s. The check makes up to two, so it can take about 20 s |
| "Search indexing is not configured on the server" | 503 | `ALGOLIA_APP_ID` or `ALGOLIA_ADMIN_API_KEY` is unset |

The GitHub check makes one attempt per call, with no retries. A repository that passes can still fail later, during the run; the dashboard then shows the reason on its card.

### The indexing run

```mermaid
flowchart TD
    start(["Run starts"]) --> configured{"Algolia<br/>configured?"}
    configured -- "yes" --> fetch["List the repository<br/>GitHub API, or a shallow clone<br/>skip vendored and minified files, lockfiles"]
    fetch --> select["Keep files under 1 MB<br/>at most 1000 files and 100 MB"]
    select --> download["Download the files"]
    download --> batch["Next batch of 200 files"]
    batch --> parse["Parse each file<br/>a parse failure is counted"]
    parse --> store["Store files and entities<br/>a failed batch is rolled back"]
    store --> more{"More files?"}
    more -- "yes" --> batch
    more -- "no" --> index["Index the entities in Algolia<br/>tagged with this run's id"]
    index --> clear["Delete the previous run's<br/>rows and Algolia records"]
    clear --> skipped{"Anything left out?"}
    skipped -- "no" --> completed["completed"]
    skipped -- "yes" --> partial["completed<br/>error_message: Partially indexed"]
    configured -- "no" --> failed["failed<br/>error_message says why"]
    failed -. "a reprocess of a<br/>completed repository" .-> kept["completed, previous index kept<br/>error_message: Reprocessing failed"]
    fetch -. "GitHub or clone error" .-> failed
    index -. "nothing indexed,<br/>or Algolia rejects it" .-> failed
```

The previous run's rows and records stay searchable until the new run is complete. If a reprocess of a completed repository fails, they are kept: the repository goes back to `completed`, and `error_message` reads `Reprocessing failed: <reason>. Search still uses the previous index.` With an embeddings key, the run embeds its definitions before indexing them, so search never returns both runs' records for as long as embedding takes. The run completes once Algolia has applied the delete of the previous run's records.

Progress is pushed to the dashboard after every batch. A file that fails to parse is still stored, without entities. A repository too large for one GitHub tree call is also listed through the contents API, up to 300 directories; anything it never reaches counts as left out. Repositories on other hosts are read with a shallow `git clone` instead, and the same file rules apply.

### Repository status

```mermaid
stateDiagram-v2
    [*] --> pending: repository added
    pending --> processing: job starts
    processing --> completed: indexed
    processing --> failed: error, with no earlier index
    processing --> completed: reprocess failed, previous index kept
    completed --> processing: reprocess with force_reprocess
    failed --> processing: reprocess
    processing --> processing: server restart, runs again
    completed --> [*]: deleted
    failed --> [*]: deleted
    note right of completed: a partial index is noted in error_message
```

A repository can't be deleted while its job is running. Delete returns as soon as Algolia accepts the removal; it doesn't wait for Algolia to finish.

### Using the web dashboard

```mermaid
flowchart TB
    home["Home<br/>enter owner/repo or a URL"] --> page["Repository page<br/>live progress"]
    dashboard["Dashboard<br/>all repositories"] --> page
    dashboard --> delete["Delete"]
    page --> outcome{"Run ends"}
    outcome -- "completed or<br/>partially indexed" --> search["Search<br/>with suggestions"]
    outcome -- "failed, reason shown" --> reprocess["Reprocess"]
    reprocess --> page
    search --> github["Open the result at the<br/>exact line on its host"]
```

Progress arrives over the WebSocket. The page also polls, every 15 seconds while the WebSocket is connected and every 3 seconds while it isn't.

### Using it from an MCP client

```mermaid
flowchart TB
    install["make install-claude, install-cursor,<br/>install-vscode or install-windsurf"] --> restart["Restart the client"]
    restart --> ask["Ask about a repository"]
    ask --> tools["The assistant calls CodeSage tools"]
    tools --> answer["Answer with code and source links"]
```

Each tool call takes this path:

```mermaid
sequenceDiagram
    actor You
    participant Claude as MCP client
    participant Bridge as MCP bridge
    participant API as Backend
    participant Data as Algolia or SQLite
    You->>Claude: ask a question
    Claude->>Bridge: tools/call
    Bridge->>API: POST /ai/mcp/tools/call
    Note over API: checks key,<br/>origin, rate limit
    API->>Data: query
    Data-->>API: matches
    API-->>Bridge: result or error
    Bridge-->>Claude: tool result
    Claude-->>You: answer with code
```

- **Bridge.** It talks to the MCP client over stdio and checks the arguments first. It won't send the key over plain `http://` to a remote host.
- **nginx.** In prod the request goes through nginx, which checks your login and adds the API key.
- **Backend.** `search_code` queries Algolia; the other tools read SQLite.
- **Errors.** A rejected key or login (`401`), a refused host (`403`), a wrong URL (`404`), bad arguments (`422`), a rate limit (`429`), a backend error (`5xx`), a timeout or an unreachable backend comes back to the assistant as a tool error that says what to fix. Every tool also refuses a repository that failed or is still indexing, and says why or how far along it is.

More detail is in [docs/architecture.md](docs/architecture.md) (data model, search index, WebSocket protocol) and [docs/MCP_INTEGRATION_GUIDE.md](docs/MCP_INTEGRATION_GUIDE.md) (tools, arguments, troubleshooting).

### Supported languages

| Language | Parser | Entities |
| --- | --- | --- |
| Python | `ast`, with a line scanner for files `ast` can't parse | functions, classes, methods, imports |
| JavaScript, TypeScript, Java, Go, Rust, C (`.c`), C++ (`.cpp`), C#, PHP, Ruby | tree-sitter | functions, classes, methods, imports |
| Markdown | heading scanner | a `doc_section` per heading |
| Terraform (`.tf`, `.tfvars`), HCL (`.hcl`) | tree-sitter HCL grammar | a `terraform_block` per top-level block, named like `resource aws_s3_bucket.logs`, `module network`, `variable region` or `output api_url` |
| CSS, SCSS, HTML, JSON, YAML, XML, SQL | none | stored and readable, but no entities |

Files with any other extension are skipped. That includes C and C++ headers (`.h`, `.hpp`) and `.cc` sources.

## Quick start

You need:

- Python 3.13 and [`uv`](https://docs.astral.sh/uv/) (or any way to create `.venv` at the repo root)
- Node.js 22 and npm
- An Algolia application ID and Admin API key. Without them the backend still starts, but adding a repository returns `503` and `/health` reports `degraded`.
- A GitHub token. It's optional but recommended; without one, GitHub's low unauthenticated rate limit applies, and private repositories can't be read.

**1. Install.**

```bash
make setup
```

This copies `.env.example` to `backend/.env` if it's missing, creates `.venv` and installs the backend dependencies into it, and runs `npm ci` in `frontend/`. It stops with a message if Node 22 is missing, or if `.venv` doesn't exist yet and neither Python 3.13 nor `uv` is found. An existing `.venv` is reused without checking its Python version.

**2. Configure.** Edit `backend/.env`:

```bash
ALGOLIA_APP_ID=...
ALGOLIA_ADMIN_API_KEY=...
GITHUB_TOKEN=...
```

You don't need to create `CODESAGE_API_KEY`. `make setup`, `make start` and `make install-claude` generate it in `backend/.env` if it's missing, copy it to `frontend/.env` as `VITE_CODESAGE_API_KEY`, and keep the two in sync. To rotate it, delete the `CODESAGE_API_KEY` line in `backend/.env`, run `make setup` and `make install-claude` (or your client's target), and restart the client and Vite. They replace a key that is empty or a leftover `your-...-here` placeholder, and keep any other value. The backend itself doesn't treat a placeholder key as unset: if it starts without one of these targets running first, it uses the placeholder as the real key. See [Security](#security).

**3. Run.**

```bash
make start   # backend on http://127.0.0.1:8001, dashboard on http://localhost:5173
```

`make start` waits up to 15 seconds for the backend to answer `/health`, and exits with an error if it doesn't. The dashboard needs port 5173; if it's taken, Vite exits instead of picking another port. `make start-backend` and `make start-frontend` run them separately, `make stop` stops both, and `make health` reports whether the backend answers. `make health` needs `jq`; without it, it prints "Backend not responding" even when the backend is up. API docs are at http://127.0.0.1:8001/docs.

**4. Index a repository.** Open http://localhost:5173 and enter `owner/repo` (a pasted GitHub URL works too, and so does an https URL on GitLab, Bitbucket or another git host). The repository page shows progress live and turns searchable when it's done. If GitHub or Algolia refuses the repository, the form says why; see [Adding a repository](#adding-a-repository).

**5. Connect your MCP client.**

```bash
make install-claude                 # add CodeSage to the Claude Desktop config
make install-cursor                 # or Cursor (~/.cursor/mcp.json)
make install-vscode                 # or VS Code (your user mcp.json)
make install-windsurf               # or Windsurf (~/.codeium/windsurf/mcp_config.json)
make install-claude ARGS=--dry-run  # preview first: prints only the CodeSage entry, key masked (the key is still generated in .env if missing)
```

Restart the client and keep the backend running. Then ask your assistant something like *"Search the zustand repository for where the store is created"*.

## Using CodeSage

### Web dashboard

The dashboard follows your system's light or dark theme. The ☾ / ☀ button in the header switches it, and the browser remembers that choice.

| Page | What you can do |
| --- | --- |
| Home (`/`) | Add a repository. Type `owner/repo` or paste a GitHub URL, and it is trimmed to `owner/repo`, keeping a `/tree/<branch>` part: the server reads the branch from it. Any other URL whose first part is a host name, such as `gitlab.com/group/project` or `git@gitlab.com:group/project.git`, is sent as an https URL and checked by the server. The branch and a description have their own optional fields; the description shows on the repository page. |
| Repository (`/repository/:id`) | Watch indexing progress. Afterwards, search with suggestions (arrow keys and Enter work), filter by language and kind, and browse every definition by name and kind. With an embeddings key on the server, a third select switches search to **By meaning**: definitions are ranked by meaning, each hit shows its similarity (cosine, higher is closer), and suggestions come by meaning too. A result opens in the file viewer; "source ↗" opens it on the host at the indexed commit. The header shows that commit ("Indexed at abc1234") and whether the branch has moved since: "3 commits behind main" on GitHub, "main has changed since" elsewhere, or "Up to date with main", with a "Reprocess to update" link when it has moved. It asks once per visit, never on the status poll. Reprocess or delete the repository. |
| File viewer (`/repository/:id/file?path=…&line=…&end=…`) | Read an indexed file 400 lines at a time, with the target lines highlighted and the file's definitions listed beside it. |
| Search (`/search?q=…`) | Search every indexed repository at once. Each hit names its repository and opens in that repository's file viewer. As on the repository page, the query's words are highlighted in the results, and the query and a semantic mode stay in the URL. |
| Dashboard (`/dashboard`) | All repositories with their status and progress. Filter them by status and language; the filters stay in the URL (`?status=failed&language=python`), so reload, Back and a shared link keep them. Delete a repository from here. |

On the repository page, a finished repository shows a green card. It shows amber if it was only partially indexed and red if it failed; both say why. The Dashboard shows a partially indexed repository's note in amber, and a failed one's reason in red.

An unknown path shows "Page not found". A repository that doesn't exist says so; any other load error shows the message with "Try again". A failed repository says why on its page and on its dashboard card.

### MCP clients and tools

| Tool | What it returns |
| --- | --- |
| `list_repositories` | Indexed repositories with status and size |
| `search_code` | With `mode: "semantic"` and an embeddings key on the server, ranks definitions by meaning instead (see `EMBEDDING_API_KEY`). By default, full-text matches over functions, classes (with interfaces, type aliases and enums), doc sections and Terraform blocks, with source links. Imports only with `entity_type: "import"`. Part of a camelCase name matches, and source ranks before tests. A question in plain words returns the best partial matches |
| `get_file` | A file with line numbers: at most 400 lines and 100,000 characters per call |
| `list_definitions` | Definitions in a repository, by file and line |
| `analyze_repository` | File, line and entity counts, languages, top directories, largest files |
| `find_patterns` | Literal or regex line matches. Regex search stops after 10 s per call |
| `find_references` | Where a function, class or other name is defined and used: its definitions, then each whole-word use with the function or class it sits in, imports marked. Source comes before tests and docs. A text match, so comments and strings count too |
| `add_repository` | Adds a repository by https URL and starts indexing. Public repositories on any git host; needs the API key |

A successful tool call returns one JSON object as MCP `structuredContent`, described by an `outputSchema` in `tools/list`, and repeats it as text for older clients. See [Tools](docs/MCP_INTEGRATION_GUIDE.md#tools).

The bridge also offers two prompts: ready-made requests that an MCP client can list for you to pick. **Explain this repository** (`explain_repository`, takes `repository`) walks the assistant through `analyze_repository`, `list_definitions` and `get_file`. **Where is this implemented?** (`find_implementation`, takes `feature` and an optional `repository`) goes through `search_code`, `list_definitions`, `find_references` and `get_file`, and answers with file paths and line ranges. A resource template, `codesage://repositories/{id}/files`, lists one repository's indexed files; see [Resources](docs/MCP_INTEGRATION_GUIDE.md#resources).

The installer merges CodeSage into your client's config without touching other servers. It writes a backup first, and both files are mode 600. For a local backend the config holds no key: the launcher reads it from `backend/.env` each time it starts. Quit Claude Desktop before installing into it: it rewrites its config from memory when it saves its own settings, undoing the change. Any other client that runs stdio MCP servers takes the same `command` and `env`, and Codex adds it with `codex mcp add`; see [Manual install](docs/MCP_INTEGRATION_GUIDE.md#manual-install).

For the HTTPS prod stack, use `make install-claude ARGS="--server-url https://your-host --basic-auth <user>"`. The password goes to the macOS Keychain, and nginx supplies the API key. See [docs/MCP_INTEGRATION_GUIDE.md](docs/MCP_INTEGRATION_GUIDE.md) for manual setup and troubleshooting.

### Other git hosts

Paste `https://gitlab.com/group/project` into the Home page form, or ask your assistant: *"Add https://gitlab.com/group/project to CodeSage"*. The form, `POST /api/v1/repositories/` and the `add_repository` tool take the same URLs and run the same checks. In the form, `owner/repo` without a host still means GitHub.

- **Hosts.** GitHub, GitLab (nested groups too), Bitbucket and self-hosted servers. `http://` and `git@host:path` URLs are rewritten to `https://`, and git always fetches over https. Branch URLs such as `.../-/tree/dev` work.
- **Public only.** Private repositories are refused on every host but github.com, where the server's `GITHUB_TOKEN` can read them. The message is `... was not found or is private; only public repositories are supported on <host>.`
- **Rejected URLs.** Ports, credentials, `localhost`, private IP addresses, and host names that resolve to one. git then connects to the address that was checked.
- **Names and links.** Repositories on other hosts are named `<host>/<path>`. Search results link to the exact line on GitLab (gitlab.com, and any host whose name starts with `gitlab.`) and on bitbucket.org. Other hosts, including self-hosted Bitbucket, get no link.
- **Needs git.** The backend runs `git ls-remote` to check (10 s) and a shallow `git clone` to read (120 s). The prod Docker image includes git.

### REST API

Everything the dashboard does is plain HTTP under `/api/v1`. To index a repository from the command line:

```bash
curl -X POST http://127.0.0.1:8001/api/v1/repositories/ \
  -H "Content-Type: application/json" -H "X-API-Key: $CODESAGE_API_KEY" \
  -d '{"url": "https://github.com/owner/repo"}'
```

- **Create.** The repository is checked first, on GitHub's API or with `git ls-remote` for other hosts; see [Adding a repository](#adding-a-repository). The response is `201`, and a background job starts. A duplicate URL gets `409` with `{detail, repository_id}`; URLs match regardless of case. A bad URL or branch gets `422` with `loc` of `["body","url"]` or `["body","branch"]`. A missing or private repository, a missing branch or an empty repository gets `422` with a string `detail`. A GitHub or network problem gets `502`, `503` (with `Retry-After` on a rate limit) or `504`, and an unconfigured Algolia gets `503`. Other hosts get the messages in [Other git hosts](#other-git-hosts).
- **Status.** Poll `GET /api/v1/repositories/{id}/status`; it includes `error_message`. For push updates, connect to `/ws`, send `{"type": "subscribe", "repository_id": N}` and read `{type, data}` frames.
- **Freshness.** `GET /api/v1/repositories/{id}/freshness` compares the indexed commit with the branch now: `{branch, commits_behind, changed, checked_at}`. GitHub's compare API counts the new commits; other hosts run `git ls-remote` and report only `changed`, with `commits_behind` null. Answers are cached in the server for 10 minutes per repository and commit, so a reprocess asks again. It returns `409` before the first indexed commit, and the same `422`, `502`, `503` or `504` as the create check when the host can't be asked.
- **Reprocess.** `POST /api/v1/repositories/{id}/process?force_reprocess=true` re-runs indexing in full. `?incremental=true` (no `force_reprocess` needed) re-parses and re-indexes only files whose content changed since the last run: unchanged files are copied as they are and keep their search records, and removed files lose theirs. It still downloads every file. The dashboard's Reprocess button is a full run, so it picks up parser improvements. It returns `202` and sets a `pending` or `failed` repository to `processing` first; a `completed` one shows `processing` once its job starts. It returns `409` while a job is running, and `503` if Algolia isn't configured. The previous run's rows and search records stay until the new run is complete (each run tags its records with a `run_id`). If a reprocess of a `completed` repository fails, what the failed run wrote is removed, and the repository goes back to `completed` with its previous counts. Its `error_message` then reads "Reprocessing failed: … Search still uses the previous index."
- **Edit.** `PUT /api/v1/repositories/{id}` returns `409` if it would change `branch`, `language` or `framework` while a job or a delete holds the repository; other fields can change at any time. An empty `branch` means the default branch. Changing the branch of a `completed` or `failed` repository first checks that the branch exists (`422` if not), then reindexes it (`409` if a run started during that check).
- **Delete.** `DELETE /api/v1/repositories/{id}` sends the removal to Algolia and returns without waiting for Algolia to finish. That is safe because Algolia applies an index's tasks in order, so a later re-add that reuses the id still lands after the delete. It returns `409` while a job is running. If Algolia refuses the request it returns `502` and the repository stays.
- **GitHub push webhook.** `POST /api/v1/webhooks/github` starts the same incremental run as the scheduled refresh as soon as GitHub reports a push; see [Refresh on push](#refresh-on-push).
- **Restarts.** A server restart starts interrupted runs again, as full runs.
- **Errors.** Errors are `{"detail": "..."}`. Validation errors (`422`) carry a list instead, with the field in `loc`. An id or `skip` too large for the database is `422`. Rate limiting (`429`) sends `Retry-After`. A `500` has `{detail, request_id}`, the same ID as the `X-Request-ID` header and the server log, and carries CORS headers so a browser can read it.
- **Health.** `GET /health` is `200` `healthy`, `200` `degraded` when Algolia is unreachable or not configured, and `503` `unhealthy` when the database fails.

### Refresh on push

A GitHub webhook can keep an index current without waiting for `REFRESH_INTERVAL_MINUTES`. Each push to an indexed branch starts an incremental run for that repository at once. The run is the same one the scheduled refresh starts.

1. Make a secret and set it on the backend, then restart it:
   ```bash
   echo "GITHUB_WEBHOOK_SECRET=$(openssl rand -hex 32)" >> backend/.env
   ```
   For the Docker stacks, put it in the `.env` they read. Without it the endpoint answers `404`.
2. In the GitHub repository, open **Settings → Webhooks → Add webhook**:
   - **Payload URL:** `https://<your-host>/api/v1/webhooks/github`
   - **Content type:** `application/json`
   - **Secret:** the same value
   - **Events:** "Just the push event"

GitHub sends a `ping` first, which gets `202`. Each delivery's response, under **Recent Deliveries**, lists the repository IDs it `started` and any that were `busy`.

- **Which repositories.** A push starts a run for each `completed` repository with the pushed GitHub URL and branch. A repository with no branch follows the payload's default branch. Other branches, tags, other events and a push of the commit already indexed start nothing.
- **Authentication.** The signature in `X-Hub-Signature-256` (HMAC-SHA256 of the body with the secret) is checked first, and a missing or wrong one gets `401`. The endpoint needs no API key, since GitHub can't send one. The prod nginx exempts this one path from its login. The host check still applies when a key is set, so the host GitHub calls must be in `ALLOWED_HOSTS`.
- **Busy repositories.** A push that arrives while a run is going is not queued. The next push picks it up, or the scheduled refresh if it's on.
- **Locally.** Without a key, the backend serves only loopback clients that address it as `localhost`. A forwarder must therefore post from the same machine to `http://localhost:8001/api/v1/webhooks/github` with `Host: localhost`. It must also pass the body through byte for byte, since the signature covers the exact bytes GitHub sent.

## Security

- **API key.** When `CODESAGE_API_KEY` is set, it's required for:
  - every write: create, update, delete and process;
  - search suggestions, the MCP tool call and resource reads;
  - the `/ws` WebSocket.

  Send it as an `X-API-Key` header. Browsers send it on the WebSocket as a `codesage.key.<hex>` subprotocol, so it never appears in a URL or an access log. Other reads (repositories, status, stats, tool listings, `/health`) are public.
- **Running without a key** is allowed only on loopback. The backend refuses to start on a non-loopback `MCP_SERVER_HOST` without one. Even then, it serves only local clients that address it as `localhost`, `127.0.0.1` or `[::1]`, which blocks DNS rebinding and LAN access.
- **Hosts, when a key is set.** The API answers only to loopback hosts, the `CORS_ORIGINS` hosts and those listed in `ALLOWED_HOSTS`. Any other `Host` gets `403`, which blocks DNS rebinding even though the dev bundle embeds the key.
- **Cross-site requests.** Browser writes and WebSocket connections from an origin that is neither in `CORS_ORIGINS` nor the API's own origin are refused with `403`.
- **The key in the bundle.** `VITE_*` variables end up in the JavaScript bundle, so outside the prod stack anyone who can load the dashboard can read the key. Use that setup locally, for one user. The prod stack keeps the key in nginx behind basic auth instead.
- **The MCP bridge** refuses to send the key or a login over plain `http://` to a non-loopback host.

## Configuration

`backend/.env` (see `.env.example`):

| Variable | Default | Notes |
| --- | --- | --- |
| `CODESAGE_API_KEY` | generated by `make setup` | Required unless the server listens on loopback only or is read-only. Generated if missing and copied to `frontend/.env`; see [Configure](#quick-start) |
| `READ_ONLY` | `false` | `true` serves searches and reads to anyone on an allowed host (`CORS_ORIGINS`, `ALLOWED_HOSTS`), with no key, and refuses every write: adding, reprocessing, editing, deleting and the GitHub webhook return `403`, and `add_repository` is neither listed nor run. The database must already be at the latest migration; it is never migrated or written to, so a read-only SQLite file works. The dashboard swaps the add form for a notice and hides Reprocess and Delete. Made for a public demo |
| `MCP_SERVER_HOST`, `MCP_SERVER_PORT` | `127.0.0.1`, `8001` | A non-loopback host requires the key. They don't move the server: `make start-backend` always binds `127.0.0.1:8001` and the Docker images `0.0.0.0:8001`. They set the startup check, the server URL in the OpenAPI schema, and the bind address only for `python -m app.main` |
| `ALGOLIA_APP_ID`, `ALGOLIA_ADMIN_API_KEY` | unset | Required for indexing and search. Empty or `your-...-here` values count as unset: adding or reprocessing a repository returns `503`, MCP search says Algolia isn't configured, and `/health` is `degraded` |
| `ALGOLIA_INDEX_NAME` | `codesage_code_entities` | One index per database; the Compose files use their own |
| `GITHUB_TOKEN` | unset | Raises GitHub rate limits and allows private github.com repositories. If GitHub rejects it, adding a repository returns `502` |
| `DATABASE_URL` | `sqlite:///./codesage.db` | SQLite, or Postgres with `postgresql://user:password@host:5432/db` (the psycopg driver is installed). The migrations run on either at startup. Use Postgres to run `INDEX_WORKERS=external` workers on more than one machine |
| `CORS_ORIGINS` | localhost ports 3000, 5173, 5174 (`.env.example`, which `make setup` copies, sets only 3000 and 5173) | Comma-separated list of origins; `*` is rejected. Also decides which browser origins may write |
| `ALLOWED_HOSTS` | unset | With a key set, extra hostnames the API answers to, besides loopback and the `CORS_ORIGINS` hosts. Comma-separated; `*.example.com` allows subdomains, `*` allows any host |
| `API_WORKERS` | `1` | API processes: `Dockerfile.prod` passes it to uvicorn's `--workers`. Above 1 needs `INDEX_WORKERS=external` and `RATE_LIMIT_STORAGE_URL`, or the API refuses to start. Processes starting together take turns applying the migrations, under a Postgres advisory lock or a lock file next to the SQLite database |
| `RATE_LIMIT_STORAGE_URL` | unset (this process's memory) | Where rate-limit counters live. `redis://host:6379` shares them between API processes, so a client gets one limit, not one per process |
| `INDEX_WORKERS` | `inline` | Who runs indexing jobs. `inline`: the API process. `external`: the API only queues them in the database (the `jobs` table), and one or more `python -m app.worker` processes run them, so heavy parsing and embedding never slow the API. Start workers after the API, which applies the migrations. With Compose: `INDEX_WORKERS=external docker compose -f deployment/docker-compose.yml --profile workers up -d --scale worker=2` |
| `EMBEDDING_API_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL` | OpenAI's endpoint, unset, `text-embedding-3-small` | Semantic search, bring your own key: any OpenAI-compatible `/v1/embeddings` (OpenAI, Voyage, a gateway, or a local Ollama with any key). Off while the key is unset. Each run then embeds its definitions (not imports) and stores the vectors in the database; definitions and queries are sent to that provider. The dashboard offers **By meaning** search only while it's set, and each semantic suggestion costs one embeddings call |
| `GITHUB_WEBHOOK_SECRET` | unset (off) | The secret of a GitHub push webhook pointed at `/api/v1/webhooks/github`; see [Refresh on push](#refresh-on-push) |
| `REFRESH_INTERVAL_MINUTES` | `0` (off) | Every N minutes, check each completed repository's branch (the same check as the freshness line) and run an incremental reindex of those that moved. Answers are cached for 10 minutes, so a shorter interval adds nothing |
| `ENVIRONMENT`, `LOG_LEVEL` | `development`, `INFO` | `production` hides `/docs` and `/redoc`. `/openapi.json` stays on; the prod stack's nginx doesn't route it |

Rate limits are per client address: 100 per minute for repository create, process and freshness and for search suggestions, and 30 per minute for MCP tool calls and resource reads.

## Deployment

| Stack | Command | What you get |
| --- | --- | --- |
| Dev | `export CODESAGE_API_KEY=...` then `make up` | nginx on http://localhost and the backend on :8001, both bound to 127.0.0.1 |
| Prod | `make prod-build && make prod-up` | HTTPS on 443 behind basic auth, with nginx adding the API key. Port 80 answers `/health` and redirects everything else |

Prod needs a certificate in `deployment/ssl/`, a login in `deployment/htpasswd`, and your domain in `CORS_ORIGINS`. If the site is also reached under another name or by IP, export those hostnames in `ALLOWED_HOSTS`, or they get `403`. See [deployment/DOCKER.md](deployment/DOCKER.md) for setup, and for why each stack uses its own Algolia index.

## Development

```bash
make test                         # backend tests
.venv/bin/ruff check backend      # backend lint
cd frontend && npm test           # frontend unit tests
cd frontend && npm run test:e2e   # Playwright end-to-end tests (first: npx playwright install chromium)
cd frontend && npm run lint
cd frontend && npm run build      # type-check and production build
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs on pushes to `master` and on every pull request. It runs the backend lint and tests, the Postgres tests against Postgres 16, the frontend lint, build and tests, and the Playwright end-to-end tests. It also validates both Compose files and both nginx configs (`nginx -t`), checks that every proxied location in the prod template overwrites `X-Forwarded-For`, and builds the prod backend image. It then starts the dev stack (`deployment/docker-compose.yml`) with a throwaway `backend/.env` and fake Algolia keys, and checks that the backend answers `/health`, that nginx serves the app at `/`, and that nginx proxies `/health` and an API call to the backend. The stack is torn down afterwards, and its logs are printed if a check fails.

```
backend/app/            FastAPI app: api/ (routes), core/ (config, auth, database), models/, schemas/, services/
backend/codesage_mcp/   stdio MCP bridge your MCP client runs (python -m codesage_mcp)
backend/alembic/        database migrations, applied at startup
backend/tests/          pytest suite
frontend/src/           React dashboard: pages/, components/, services/ (API and WebSocket clients)
deployment/             Compose files, dev nginx.conf and the prod nginx template
docs/                   architecture notes and the MCP guide
scripts/                install_claude_desktop.py (the installer for every client, --client picks it)
mcp_launcher.sh         what the MCP client launches
```

## Known limitations

- **More than one API process needs Redis and workers.** With `API_WORKERS` above 1 the API refuses to start unless `INDEX_WORKERS=external` and `RATE_LIMIT_STORAGE_URL` (Redis) are set, because jobs and rate-limit counters would otherwise live in each process's memory. Caches stay per process, and each process runs the scheduled refresh, so the GitHub checks happen once per process (the `jobs` table still queues one run per repository). The prod Compose `scale` profile adds Redis and workers.
- **Interrupted runs.** A restart during a run starts it again, as a full run. With external workers, a job whose worker stops sending heartbeats for 5 minutes is queued again for another worker.
- **SQLite by default.** Postgres works through `DATABASE_URL`, and CI runs migrations, column types and the job claim against Postgres 16. The rest of the test suite runs on SQLite. Migrations run at startup, and a database from before Alembic is stamped first.
- **Synchronous Algolia client.** Its calls run in worker threads.
- **Tests and CI.** The Playwright end-to-end tests run in Chromium only, against a seeded database with no Algolia or GitHub, so they cover the Home form, the dashboard, the repository page and the file viewer, but not search, freshness or indexing. CI starts the dev Docker stack with fake Algolia keys and checks that it answers, but never indexes a repository in it. The prod stack (HTTPS, basic auth) is only config-checked and built; it was last run by hand.
- **Search scope.** Searching across all repositories includes ones that are being reprocessed.
- **Git redirects.** For hosts other than github.com, git follows the host's first HTTP redirect without re-checking where it points. A hostile public host could send it to an internal address. If that matters, route the backend's traffic through an egress proxy that refuses private addresses.
