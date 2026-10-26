---
title: Troubleshooting
description: Symptoms, causes and fixes for setup, the dashboard, indexing, Claude Desktop, both Docker stacks and Algolia, plus where to look first.
---

Find your symptom in the section for the part that is failing. Messages are quoted as the code writes them, so you can search this page for what you see. If nothing matches, go to [Where to look](#where-to-look).

## Setup and startup

| Symptom | Cause | Fix |
| --- | --- | --- |
| `make setup` stops with "Python 3.13 (or uv) is required" | No Python 3.13 and no `uv` on the path | Install Python 3.13 or `uv`, then run `make setup` again |
| `make setup` stops with "Node.js 22 or newer is required" | Node is missing or older than 22 | Install Node 22, then run `make setup` again |
| `make start` prints "A backend is already running on port 8001" | Something already answers `/health` on that port, and its answer would pass for yours | `make stop`, or run `make start-frontend` to use the running backend |
| `make start` prints "The backend did not start; see its output above." | The backend did not answer `/health` within 15 seconds, or it exited | Read the backend output above the message. A settings error is the usual cause (next rows) |
| The dashboard does not start and Vite exits | Port 5173 is taken. Vite is set to fail instead of picking 5174, which the example `CORS_ORIGINS` does not allow | Free port 5173, or add the new origin to `CORS_ORIGINS` |
| Backend exits with "CORS_ORIGINS must not contain '*' because credentials are allowed" | `CORS_ORIGINS` contains `*` | List the allowed origins explicitly |
| Backend exits with "CODESAGE_API_KEY is required when MCP_SERVER_HOST is not a loopback address" | The host is not `127.0.0.1`, `localhost` or `::1` and no key is set | Set a key, or bind to loopback |
| Log line "CODESAGE_API_KEY is not set; write endpoints are unauthenticated" | No key on loopback. It is a warning, not an error | Run `make setup`, which generates one |
| Log line "Algolia credentials not configured - MCP server cannot function properly" | `ALGOLIA_APP_ID` or `ALGOLIA_ADMIN_API_KEY` is empty or still a `your-...-here` placeholder | Set both in `backend/.env` and restart. See [Algolia](#algolia) |
| `make health` prints "Backend not responding" | The backend is down or answered with an error | `make start-backend`. `make health` also needs `jq` |
| `403` with `{"detail": "Host not allowed"}` | The `Host` header is not loopback, in `CORS_ORIGINS` or in `ALLOWED_HOSTS` | Use `localhost` or `127.0.0.1`, or add the name to `ALLOWED_HOSTS` |
| `403` with "Only local clients are served without an API key" | No key is set and the client is not on the same machine | Set `CODESAGE_API_KEY`, or call from the same machine |
| `403` with "Cross-origin request refused" | A write or WebSocket came from an origin that is not the API's own and not in `CORS_ORIGINS` | Add the full origin (for example `https://host`) to `CORS_ORIGINS` |
| `401` with "Invalid or missing API key" | The `X-API-Key` is missing or wrong | Send the key from `backend/.env`. See the dashboard rows below |
| `429` with "Too many requests; try again in N seconds." | A per-address rate limit. Create and process allow 100 a minute, tool calls and resource reads 30 | Wait for `Retry-After`. Everything behind one address shares the count |
| `/docs` returns `404` | `ENVIRONMENT=production` turns the docs off | Use the dev stack or a local run |

## Dashboard and adding repositories

| Symptom | Cause | Fix |
| --- | --- | --- |
| Dashboard actions fail with `401`, or an auth notice appears | The key in the dashboard differs from `backend/.env`. The dev bundle reads `VITE_CODESAGE_API_KEY` | Run `make setup` so `frontend/.env` matches, then restart Vite. In Docker dev, re-export `CODESAGE_API_KEY` and run `make build && make up` |
| Add form shows a message about the URL or branch (`422`) | Not a GitHub repository URL, or an invalid branch name | Use `owner/repo` or a github.com URL. Branch names cannot contain `..` or start with `-` |
| "Invalid GitHub URL (host must be github.com)" | The dashboard and `POST /api/v1/repositories/` take github.com only | Add other hosts from Claude with the `add_repository` tool |
| "GitHub repository owner/repo was not found" (`422`) | The repository does not exist, or it is private and `GITHUB_TOKEN` cannot read it | Check the URL. For a private repository, give the token access |
| "Branch 'x' does not exist in owner/repo." or "owner/repo is empty; there is nothing to index." (`422`) | The branch is missing, or the repository has no content | Fix the branch, or leave it empty for the default |
| "GitHub denied access to owner/repo." (`422`) | GitHub answered `403` for a reason other than a rate limit | Check the token's access |
| "owner/repo has already been added." (`409`) | Same URL as an existing repository, matched without regard to case | Use the "Open it" link, or reprocess the existing one |
| "GitHub's API rate limit was reached; try again in about N minutes." (`503`) | GitHub is rate-limiting the server. `Retry-After` says how long | Wait, or set `GITHUB_TOKEN` for a higher limit |
| "GitHub rejected the server's GITHUB_TOKEN" or "Could not reach GitHub; try again." (`502`) | The token is invalid, or GitHub is down or unreachable | Replace the token, or retry later |
| "GitHub did not respond in time; try again." (`504`) | A check request took longer than 10 s | Retry |
| "Search indexing is not configured on the server" (`503`) | Algolia credentials are missing | See [Algolia](#algolia) |
| Reprocess returns `409` "Repository is already processed; pass force_reprocess=true to reprocess it" | The repository is `completed` | Use `?force_reprocess=true`. The dashboard does this for you |
| Reprocess or delete returns `409` "is already being processed" or "is being processed" | A job is running for that repository | Wait for it to finish |
| Delete returns `502` "Could not remove the repository's records from Algolia; nothing was deleted" | Algolia refused the delete request | Fix the Algolia connection and delete again. The repository is still there |
| Progress does not move live | The WebSocket was refused (key or origin), or the server is full | The page also polls every 3 seconds, so progress still updates. Check the browser console for "WebSocket rejected by the server" |
| WebSocket closes with 1008 | Missing or wrong key, or a refused `Host` or `Origin` | Fix the key or `CORS_ORIGINS`. The client does not retry on 1008 |
| WebSocket closes with 1013 | 200 connections in total, or 20 from one address | The client retries with backoff. Close extra tabs |
| Search suggestions never appear | The request needs the key, and the dashboard has none or the wrong one. Suggestions also stay empty when Algolia fails | Fix the key. Check the backend log for "Suggestions unavailable" |
| "Page not found" | The path is not `/`, `/dashboard` or `/repository/:id` | Go to the Home page |
| `422` on an ID or `skip` | The number is larger than the database allows | Use a smaller number |

## Indexing failures and partial indexes

The reason is in `error_message`. The dashboard card, `GET /api/v1/repositories/{id}/status` and `list_repositories` all show it.

| Message | Cause | Fix |
| --- | --- | --- |
| "Processing was interrupted by a server restart; reprocess the repository" | The server stopped, or hot reload restarted it, during a run | Reprocess. Nothing retries on its own |
| "Processing stopped unexpectedly; reprocess the repository" | The background task died | Reprocess. The backend log has "Background repository job crashed" |
| "Algolia credentials not configured. Set ALGOLIA_APP_ID and ALGOLIA_ADMIN_API_KEY." | The credentials went away after the run was scheduled | Set them and reprocess |
| "No supported code files found in repository" | Every file was filtered out: denied folders, lockfiles, unknown extensions, files of 1 MB or more | Check the [file rules](/docs/concepts/indexing-pipeline/#file-selection-rules) |
| "No code entities were indexed from N files (M failed to process)" | Files were found but none produced entities. CSS, HTML, JSON, YAML, XML and SQL have no parser | Add a repository that has source files in a [supported language](/docs/reference/languages/) |
| "Algolia rejected the indexing request" | `save_objects` raised an error | Read the backend log for "Failed to index entities in Algolia" |
| "Could not remove previously indexed records from Algolia" | The delete before a reprocess failed or timed out after 120 s | Check Algolia, then reprocess |
| "Database error while storing the repository" | A SQLAlchemy error. The real text stays in the log | Read the backend log for "Repository processing failed" |
| "GitHub API rate limit exceeded (403) while reading owner/repo; try again in about N minutes" | The limit was hit mid-run, and the wait would be over 60 s or a second limit followed | Wait, set `GITHUB_TOKEN`, reprocess |
| "GitHub rejected the token (401) for owner/repo; check GITHUB_TOKEN" | The token is wrong or revoked | Replace it |
| "Branch 'x' not found in owner/repo" | The branch was deleted after the check | Edit the branch or reprocess |
| "GitHub repository or path not found (404): ...; it may be private or misspelled" | The repository was removed or made private | Check access |
| "GitHub download failed (404) for path" or "GitHub download timed out (504) for path" | One file could not be fetched after 3 attempts. One failed download fails the run | Reprocess. The failure is never partial on purpose |
| "GitHub did not respond in time while reading ..." or "Could not reach GitHub while reading ..." | Timeouts or connection errors after 3 attempts | Retry later |
| "Could not clone host/path from host" (502), "host did not respond in time while cloning ..." (504), "Could not run git to clone ..." (503) | The clone failed, took over 120 s, or git is not installed | Check the host and that the image or machine has `git` |
| "host/path was not found or is private; only public repositories are supported on host" | A non-GitHub repository is missing or needs a login | Make it public |
| "... The previous index was removed; reprocess to rebuild it." at the end of a message | A reprocess cleared the old index and then failed | The repository has nothing searchable until you reprocess |
| Status `completed` with "Partially indexed: N of M files could not be stored" | A database commit failed for a batch of 200 files | Read the log for "Failed to store file batch" |
| "Partially indexed: N files could not be parsed" | A parser raised an error on those files. They are stored, but have no entities | Read the log for "Failed to parse code file" |
| "Partially indexed: N files over the 1000-file or 100 MB limit were skipped" | The repository is over a cap. The files that sort last by path are the ones left out | Index a smaller branch or accept it |
| "Partially indexed: the repository is too large to list in full, so some directories were not indexed" | The contents-API walk hit its 300-request cap | Accept it, or index a smaller repository |
| Stays `processing` with progress 0 | Two runs are already active and this one waits for a slot | Wait |
| Stays `processing` although the server was killed | The process died before it could record a failure | Start the backend. Start-up marks the row `failed`. Then reprocess |
| Some C or C++ files are missing | `.h`, `.hpp` and `.cc` are not in the extension map. Only `.c` and `.cpp` are | Known limit. See [Known limitations](/docs/limitations/) |

## Claude Desktop and the bridge

The bridge writes to stderr, which Claude Desktop saves in its MCP log. See [Where to look](#where-to-look).

| Symptom | Cause | Fix |
| --- | --- | --- |
| Server missing in Claude Desktop | The config was not reloaded | Restart Claude Desktop |
| `.venv/bin/python not found` or "the Python dependencies are missing" (launcher) | No virtualenv, or the dependencies are not installed in it | `make setup` |
| "no Keychain password found for ..." (launcher) | `CODESAGE_BASIC_AUTH_USER` is set but its Keychain entry is missing | Re-run the installer with `--basic-auth USER` |
| "CodeSage backend not reachable at ..." | Backend not running, or `MCP_SERVER_URL` is wrong. `tools/list` still works | `make start-backend`, or correct the URL |
| "rejected the API key (401)" | `CODESAGE_API_KEY` in the Claude config differs from `backend/.env` | Re-run `make install-claude`, then restart Claude Desktop |
| "No API key is configured; set CODESAGE_API_KEY in the MCP server's env ..." | The backend needs a key and the Claude config has none | Re-run `make install-claude` |
| "The proxy in front of CodeSage rejected the login (401)" | Wrong user, or no Keychain entry for it | Re-run the installer with `--basic-auth USER` and enter the password |
| "Refusing to send the CodeSage key or login over plain http to ..." | A remote `http://` URL with a key or login | Use `https://`, or set `CODESAGE_ALLOW_INSECURE_AUTH=1` on a trusted network |
| "refused the request (403)" | The backend runs on another host and its `Host` is not allowed | Add the host to `ALLOWED_HOSTS` on the backend and check `MCP_SERVER_URL` |
| "The backend returned 404 for ..." | `MCP_SERVER_URL` points at the wrong place | Point it at the backend root, without `/api/v1` |
| "MCP_SERVER_URL must start with http:// or https:// (got '...')" | The URL has no scheme or host | Fix the URL. Nothing was sent |
| "did not answer within 30 s" | The backend is overloaded or something in front of it is stuck | Check the backend log, then retry |
| "CodeSage backend error (500) ... (request id)" | An unexpected backend error | Search the backend log for that request ID |
| "CodeSage backend error (502)" with no detail | The proxy in front of the backend returned an HTML page and the body is not echoed | Check nginx and the backend |
| "rate limit exceeded (429)" | More than 30 tool calls or resource reads a minute from one address | Wait and retry |
| "returned an unexpected response; check MCP_SERVER_URL" | The URL points at something that is not the CodeSage backend | Point it at the backend root |
| "Invalid arguments for ..." | A wrong or unknown argument. Unknown arguments are rejected | Match the [tool arguments](/docs/reference/mcp-tools/) |
| "Repository '...' failed to index: ..." | The repository has status `failed`; the text is the reason | Fix the cause, then reprocess from the dashboard |
| "Repository '...' is still indexing (n/m files)" | Status is `pending` or `processing` | Wait for it |
| "Repository '...' not found. Available repositories: ..." | The name or ID does not match | Use an ID from `list_repositories` |
| "Repository '...' is ambiguous: ..." | Two repositories match the name | Use the numeric ID |
| "url: ..." from `add_repository` | Not an https repository URL (port, credentials, `localhost` and private IPs are refused) | Use the plain https URL |
| Tools are listed but searches return nothing | No repository has finished indexing | Check `GET /api/v1/repositories/` for status |

## Docker dev

| Symptom | Cause | Fix |
| --- | --- | --- |
| Backend exits immediately | `CODESAGE_API_KEY` is empty and the container binds `0.0.0.0` | Set the key, then `make logs-backend` |
| Dashboard shows `401`, or the WebSocket is rejected | The key in the bundle differs from the backend's | Re-export `CODESAGE_API_KEY`, then `make build && make up` |
| Empty reply on another hostname | The dev nginx drops unknown `Host` values with `444` | Use `localhost` or `127.0.0.1` |
| Port 80 already in use | The prod stack, or another service | `docker compose -f <file> down` for the other stack |
| Brief `502` right after `make up` | nginx starts as soon as the backend container starts, not when it is healthy | Wait a few seconds and reload |
| A run failed with "interrupted by a server restart" after you saved a file | `--reload` restarted the server | Reprocess, and avoid saving files during a run |
| Changes to the dashboard code do not appear | The bundle is built into the nginx image | `make build && make up`, or use `make start` for front-end work |

## Docker prod

| Symptom | Cause | Fix |
| --- | --- | --- |
| `make prod-up` fails on a bind mount | `deployment/htpasswd` or `deployment/ssl/` is missing (`create_host_path: false`) | Create them as in [Production deployment](/docs/guides/production/) |
| nginx exits with an SSL error | `cert.pem` or `key.pem` is missing or does not match | Regenerate the pair and read `docker compose -f deployment/docker-compose.prod.yml logs nginx` |
| Backend is unhealthy and nginx never starts | nginx waits for the backend healthcheck, which fails on a non-2xx `/health`. The usual cause is a missing key; a database failure is the other | Export `CODESAGE_API_KEY` in the shell and read the backend logs |
| `403` from the API | The `Host` is not loopback, in `CORS_ORIGINS` or in `ALLOWED_HOSTS` | Add the name or IP to `ALLOWED_HOSTS` (no port) and restart |
| Writes or the WebSocket get `403` from a browser | The origin is neither the API's own nor in `CORS_ORIGINS` | Add the full origin, such as `https://host`, to the Compose file and restart |
| Browser asks for a login on every request | Wrong user or password in `htpasswd` | Recreate the file and restart nginx |
| Browser shows a certificate warning | The certificate is self-signed | Trust it, or use a real certificate |
| Claude Desktop cannot reach prod | The bridge refuses plain `http://`, or does not trust a self-signed certificate | Use `https://`, and add `SSL_CERT_FILE` to the bridge's `env` |
| `429` for everyone at once | Limits count per client address. Clients that reach the backend through a proxy that does not forward the real address share one count | Behind the prod nginx the address comes from `X-Forwarded-For`, which nginx sets. Do not publish the backend port |

## Algolia

| Symptom | Cause | Fix |
| --- | --- | --- |
| `/health` says `degraded` with `not_configured` | `ALGOLIA_APP_ID` or `ALGOLIA_ADMIN_API_KEY` is unset. Empty values and `your-...-here` placeholders count as unset. It is still HTTP `200` | Set both in `backend/.env` and restart |
| `/health` says `degraded` with "Algolia is unreachable" | The probe (`list_indices`, 5 s) failed. The result is cached for 30 s | Check the network and the credentials. The log has "Algolia health check failed" |
| Adding or reprocessing returns `503` | Algolia is not configured | As above |
| "Search is not configured on the server (ALGOLIA_APP_ID / ALGOLIA_ADMIN_API_KEY are missing)." | Same cause, seen from a tool | As above |
| "Search is unavailable; try again later." | Algolia is unreachable or rejected the query. The detail is in the log only | Read the backend log for "MCP search failed" |
| Searches return nothing | The repository is not `completed`, the index name changed, or the index is shared and was cleaned | Check the status, and `ALGOLIA_INDEX_NAME` |
| Records of one repository vanish after another is deleted | Two databases share one index and both number repositories from 1 | Give each database its own `ALGOLIA_INDEX_NAME`. The Compose files already do |
| Log says "Algolia indexing still publishing" | A task was not published within 300 s. The records were accepted | Results appear shortly. No action |
| Log says "Failed to configure Algolia index settings" | `set_settings` failed. The run continues | Check the admin key's permissions |
| Results appear in the wrong order | Ranking breaks ties with `rank_weight`. Names rank above bodies | See [Search](/docs/concepts/search/#ranking) |

## Where to look

- **Backend log.** structlog writes one JSON object per line, with `timestamp`, `level`, `event` and any context such as `request_id`. Locally it is the terminal where uvicorn runs (`make start-backend`). In Docker use `make logs-backend` for dev, or `docker compose -f deployment/docker-compose.prod.yml logs -f backend` for prod. Set `LOG_LEVEL=DEBUG` for more.
- **`X-Request-ID`.** Every response has this header, including `403` responses. A `500` also returns it as `request_id` in the body. Search the backend log for that ID to find the traceback. You can send your own `X-Request-ID` and it will be reused.
- **The MCP log.** Claude Desktop saves the bridge's stderr. On macOS it is `~/Library/Logs/Claude/mcp-server-codesage.log`. The file is named after the key under `mcpServers`, so an entry made with `--name` has its own log. Set `CODESAGE_MCP_LOG_LEVEL=DEBUG` in the entry's `env` for more detail.
- **`/health`.** `curl http://127.0.0.1:8001/health` (or `curl -k https://your-host/health` in prod). The body lists `database` and `algolia` components. `unhealthy` is `503`; `degraded` is `200`.
- **The status endpoint.** `GET /api/v1/repositories/{id}/status` returns `status`, `processed_files`, `total_files`, `progress` and `error_message`. `GET /api/v1/repositories/` lists all of them.
- **MCP checks.** `make test-mcp` calls the capabilities and tool-list endpoints. The MCP Inspector (`npx @modelcontextprotocol/inspector ./mcp_launcher.sh`) lets you call a tool by hand.
- **nginx.** In Docker, `docker compose -f <file> logs nginx`. The dev nginx logs the client address, request, status and user agent. Prod adds the login name.
- **Browser console.** The dashboard logs "WebSocket rejected by the server: check VITE_CODESAGE_API_KEY" when the key is wrong.

Still stuck? See [Known limitations](/docs/limitations/) in case what you hit is by design, or the [FAQ](/docs/faq/).
