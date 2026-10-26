---
title: FAQ
description: Short, accurate answers to the questions people ask most about running and using CodeSage.
---

## The basics

### Is there a hosted version?

No. CodeSage is self-hosted. You run the backend and dashboard yourself, with your own Algolia account. There is no hosted demo and no CodeSage service to sign up for. This documentation site is static pages only.

### What does it cost?

CodeSage itself has no fee in these sources. What you pay for is on your side: your Algolia plan (CodeSage writes one record per code entity and sends search requests to your index), your Claude plan, and your own machine or server. Check Algolia's current plan limits before you index a very large repository.

### Do I need Claude Desktop?

No. The dashboard works on its own for adding, watching and searching repositories. Claude Desktop (or another MCP client) is how you get the seven tools. See [Introduction](/docs/introduction/).

### Do I need Docker?

No. `make setup` and `make start` run everything locally with Python and Node. Docker is for the dev and prod Compose stacks. See [Docker](/docs/guides/docker/).

### Does CodeSage run my code?

No. It reads files as text, parses them into entities and stores them. It never executes, builds or tests the code it indexes.

### Which operating systems work?

The sources describe macOS and Linux paths for everything. The Claude Desktop installer also knows the Windows config path, but the launcher is a bash script that runs `.venv/bin/python`, and the `--basic-auth` flow needs the macOS Keychain. Treat Windows as untested.

## Requirements and credentials

### Does it work without Algolia?

Only in part. The backend starts, `/health` reports `degraded`, and the tools that read SQLite (`list_repositories`, `get_file`, `list_definitions`, `analyze_repository`, `find_patterns`) work on repositories that were indexed earlier. But you can't index anything new: adding or reprocessing a repository returns `503` with `Search indexing is not configured on the server (Algolia credentials are missing).`, and `search_code` returns `Search is not configured on the server (ALGOLIA_APP_ID / ALGOLIA_ADMIN_API_KEY are missing).` Empty values and `your-...-here` placeholders count as unset. See [Installation](/docs/installation/#get-algolia-credentials).

### Why does the backend need the Admin API key?

It creates the index settings, saves records, deletes records by filter, lists indexes for the health check and runs every search. A search-only key can do none of the writes. Keep the Admin key in `backend/.env` only.

### Does it work without a GitHub token?

Yes, for public repositories. Without `GITHUB_TOKEN`, GitHub's low unauthenticated rate limit applies, so a big repository can hit a rate-limit message, and the backend logs `GitHub token not found. Rate limits will be lower.` A token also lets you read private github.com repositories.

### Can I index private repositories?

On github.com, yes, if the server's `GITHUB_TOKEN` can read the repository. On GitLab, Bitbucket and self-hosted servers, no: only public repositories are supported because git can't ask for credentials. CodeSage has one shared API key and no per-user permissions, so anyone who can use your instance can search every repository the token reached.

### Can I use a search-only or restricted Algolia key?

The project sources only describe the Admin key. Nothing in them says a narrower key works.

## What it indexes

### Which languages are supported?

Entities are extracted for Python, JavaScript, TypeScript, Java, Go, Rust, C, C++, C#, PHP and Ruby (functions, classes, methods, imports), Markdown (one `doc_section` per `#` heading) and Terraform or HCL (one `terraform_block` per top-level block). CSS, SCSS, HTML, SQL, JSON, YAML and XML files are stored and readable but produce no entities. See [Languages](/docs/reference/languages/).

### Why are some of my files missing?

The file must have a known extension. Only `.c` and `.cpp` count for C and C++, so `.h`, `.hpp` and `.cc` files aren't indexed. Files in `node_modules`, `dist`, `build`, `vendor`, `third_party`, `.git`, `__pycache__`, `.next` and `coverage` are skipped, as are minified files, source maps, lockfiles, symlinks, empty or binary files, and files of 1 MB or more.

### How big a repository can I index?

At most 1000 files and 100 MB per repository, with each file under 1 MB. Files are sorted by path and the first ones are kept. A body stored in Algolia is capped at 2000 characters per entity. For a GitHub repository too large for one tree call, the backend lists directories through the contents API, up to 300 directories. Anything beyond the limits is left out and the repository is marked partially indexed.

### Why does my repository say "Partially indexed"?

The run finished and the repository is searchable, but something was left out. The `error_message` names each cause, joined by semicolons:

- `N of M files could not be stored` (a database batch failed);
- `N files could not be parsed` (stored without entities);
- `N files over the 1000-file or 100 MB limit were skipped`;
- `the repository is too large to list in full, so some directories were not indexed`.

The dashboard shows an amber card on the repository page. See [Web dashboard](/docs/guides/web-dashboard/#status-badge-and-card-colors).

### Can I index two branches of the same repository?

No. The stored URL has no branch and must be unique, so a second add of the same repository, even with another branch, is refused as already added. Delete the repository and add it again with the other branch, or change the branch of the existing one (`PUT /api/v1/repositories/<id>` with a new `branch`, refused with `409` while a run is active) and reprocess it.

### How do I refresh an index after the repository changes?

Reprocess it. CodeSage doesn't watch repositories. Use **Reprocess** on the repository page, or:

```bash
curl -X POST "http://127.0.0.1:8001/api/v1/repositories/1/process?force_reprocess=true" \
  -H "X-API-Key: $CODESAGE_API_KEY"
```

A reprocess fetches first and clears the old records only after the fetch succeeds.

## Privacy and data

### Does CodeSage send my code anywhere?

Your code touches these places, and the backend code contacts nothing else:

- **GitHub.** The backend downloads files from `api.github.com` and `raw.githubusercontent.com`, with your token if set. Other hosts are cloned with `git`.
- **Algolia.** One record per entity is sent to your index. A record holds `objectID`, `repository_id`, `file_path`, `entity_type`, `entity_name`, `description`, `parameters`, `return_type`, `line_start`, `line_end`, `language`, `signature`, `content`, `rank_weight`, `parameter_count` and `lines_of_code`. `content` is the signature plus at most 2000 characters of the entity body, and each record is trimmed to 9000 bytes. Whole files are not sent to Algolia.
- **Your local SQLite file.** It holds the full text of every indexed file at `backend/codesage.db`.
- **Claude.** What a tool returns, such as snippets or numbered file lines, becomes part of your conversation with Claude.

The backend makes outbound calls only to GitHub, Algolia and git remotes. It has no analytics or telemetry calls.

### Where is my data stored?

Full file contents and entities are in `backend/codesage.db`. Search records are in your Algolia index (`ALGOLIA_INDEX_NAME`, default `codesage_code_entities`). Your keys are in `backend/.env` and `frontend/.env`, both mode 600.

### Is the API key in the dashboard a secret?

Not in the local setup. Vite inlines `VITE_CODESAGE_API_KEY` into the JavaScript, so anyone who can load the dashboard can read it. That's fine on localhost for one user. The prod Docker stack keeps the key in nginx behind a login instead. See [Security](/docs/concepts/security/).

## Using it with Claude

### Which MCP clients work?

The bridge is a standard stdio MCP server, so any client that can launch a command with environment variables can use it. Point the client at `mcp_launcher.sh` and set `MCP_SERVER_URL` and `CODESAGE_API_KEY`. Only Claude Desktop has an installer. You can test the bridge with `npx @modelcontextprotocol/inspector ./mcp_launcher.sh`. See [Claude Desktop](/docs/guides/claude-desktop/#check-the-bridge-with-the-mcp-inspector).

### Why does Claude say a repository is "still indexing" or "failed to index"?

Every tool except `list_repositories` and `add_repository` refuses a repository that isn't `completed`. A `pending` or `processing` one says `is still indexing (n/m files)`. A failed one gives the reason and says to reprocess it from the dashboard.

### Why does search return results that don't contain all my words?

If no result matches every word, Algolia drops the words that miss, ignores stop words and plurals, and returns the best partial matches. That is what lets a plain question work as a query.

### Why does `find_patterns` stop early?

A regex search gives each file 1 second and the whole call 10 seconds, and skips files over 1,000,000 characters. A call that runs out of time returns `truncated: true` with the skipped files listed. Literal search has no time limit.

### I hit a rate limit. What are the limits?

Per client address: 30 per minute for MCP tool calls and resource reads, and 100 per minute for repository create, process and search suggestions. Dashboard searches count toward the 30. The error is `429` with a `Retry-After` header.

## Running it

### Can I run it on a server?

Yes, with the prod Docker stack: HTTPS on port 443, basic auth in nginx and the API key held by nginx. The backend refuses to start on a non-loopback `MCP_SERVER_HOST` without `CODESAGE_API_KEY`. Add any extra hostnames to `ALLOWED_HOSTS` or they get `403`. The stack was last run by hand; CI builds the images but never starts them. See [Production deployment](/docs/guides/production/).

### Why only one worker?

Job state, the two-runs-at-once limit, WebSocket subscriptions and rate-limit counters live in the process's memory, and SQLite allows one writer. A second worker would not see the first one's jobs. Both Compose stacks run exactly one.

### What happens if the backend restarts during indexing?

At startup every repository left `pending` or `processing` is marked `failed` with `Processing was interrupted by a server restart; reprocess the repository`. There is no automatic retry. Reprocess it.

### Why do I get `403 Host not allowed`?

With an API key set, the backend answers only to loopback hosts, the hosts in `CORS_ORIGINS` and the hosts in `ALLOWED_HOSTS`. Browser writes and WebSocket handshakes from another origin get `Cross-origin request refused`. This blocks DNS rebinding. Add your hostname (no port) to `ALLOWED_HOSTS`, or your origin to `CORS_ORIGINS`.

### Why does `make health` print "Backend not responding" when the backend is up?

`make health` pipes the answer through `jq`. Without `jq` installed, it prints that message anyway. Install `jq`, or call `curl http://127.0.0.1:8001/health` yourself.

### How do I rotate the API key?

Delete the `CODESAGE_API_KEY` line in `backend/.env`, run `make setup`, run `make install-claude`, then restart the backend, Vite and Claude Desktop. See [Installation](/docs/installation/#rotate-the-key).

### How do I delete everything?

1. Delete each repository in the dashboard. That removes its Algolia records and database rows.
2. Run `make db-reset` to delete `backend/codesage.db` and its `-journal`, `-wal` and `-shm` files.
3. Delete the Algolia index in your Algolia dashboard, if you no longer need it. `make db-reset` and `make clean` don't touch Algolia.
4. Remove the `codesage` entry from the Claude Desktop config (the installer left `.bak-*` backups next to it that you can delete too).
5. On macOS, if you used `--basic-auth`, remove the Keychain item for service `codesage-mcp`.
6. Optionally delete `.venv`, `frontend/node_modules` and the cloned folder. For Docker, `make clean` deletes the dev stack's containers, network and volume.

### Can several people share one instance?

Technically yes, but there is one shared API key and no per-user permissions. Everyone with access can search, add and delete every repository. Use the prod stack's login and keep it to people you trust.

## Related pages

- [Troubleshooting](/docs/troubleshooting/)
- [Limitations](/docs/limitations/)
- [Configuration reference](/docs/reference/configuration/)
