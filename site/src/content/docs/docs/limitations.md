---
title: Known limitations
description: Every known limit of CodeSage, why it exists and what you can do about it.
---

These are limits of the current code, not bugs waiting for a fix. Each row says what is limited, why it was built that way and the nearest workaround. Numbers were checked against the code. If you need one of these lifted, the "Why" column tells you what else has to change.

## Deployment and scale

| Limitation | Why | Workaround |
| --- | --- | --- |
| **Exactly one backend worker.** | Job state (`_jobs`), the two-run limit, WebSocket subscriptions and rate-limit counters live in the process. SQLite allows one writer. A second worker would not see the first one's jobs or broadcasts | Use a bigger machine, not more workers. Do not raise `--workers` |
| **SQLite only.** `DATABASE_URL` must be a SQLite URL. | The migrations use SQLite batch mode, the engine sets SQLite pragmas, and the single-writer limit matches the single worker | None. Moving to another database means changing the engine setup and the migrations |
| **No high availability.** | One process, one file | Back up the database volume, and keep in mind that reprocessing rebuilds everything from the source host |
| **No automatic retry.** A failed or interrupted run waits for you to reprocess it. | A restart cannot know whether a half-finished run is safe to continue. Start-up marks it `failed` | Reprocess from the dashboard, or `POST /api/v1/repositories/{id}/process` |
| **No sync with upstream.** Changes pushed to a repository are not picked up. | Nothing watches the source host. There are no webhooks or schedules | Reprocess when you want fresh data |
| **Rate limits are per client address and in memory.** They reset on restart. | slowapi default storage, with no shared store | Everything behind one address shares one count. 30 per minute applies to tool calls |
| **Dev and prod stacks cannot run together.** | Both publish port 80 | Stop one before starting the other |
| **Dev hot reload kills a running index.** | `--reload` restarts the process, and start-up marks open runs `failed` | Reprocess, and avoid saving files during a run |

## Indexing limits

| Limitation | Why | Workaround |
| --- | --- | --- |
| **At most 1000 files and 100 MB per repository, and each file under 1 MB.** Files that sort last by path are dropped. | A run holds every file in memory, and two runs can be active. The caps are constants in `FileSelector` | Index a smaller branch or a fork, or change `max_files` and `max_total_bytes` in `backend/app/services/github_service.py` and watch memory. The run says what it skipped in `error_message` |
| **Very large GitHub repositories are listed in part.** | When GitHub truncates the tree, a breadth-first walk of the contents API stops after 300 directory requests, to protect the hourly API quota | Accept it, or index a smaller repository. The run says "too large to list in full" |
| **Only 25 file extensions are indexed.** | The extension map in `github_service.py` is the allow list | See [Supported languages](/docs/reference/languages/) |
| **C and C++ headers are not indexed.** `.h`, `.hpp` and `.cc` are not in the map. | The map has `c` and `cpp` only | None short of adding the extensions |
| **CSS, SCSS, HTML, SQL, JSON, YAML and XML produce no entities.** They are stored and readable with `get_file`, but not searchable. A repository made only of these fails with "No code entities were indexed". | There is no parser for them | Use `find_patterns` for literal text in stored files |
| **Skipped without notice:** `node_modules`, `dist`, `build`, `vendor`, `third_party`, `.git`, `__pycache__`, `.next`, `coverage`, minified files, source maps and lockfiles. | They are generated or third-party code | Only cap overflow is reported in the `Partially indexed` note |
| **Empty files and files with a NUL byte are skipped.** | They are treated as binary | None |
| **Symlinks are never listed or followed.** Submodules are not fetched. | Safety, and the trees API lists blobs only | Add the submodule's repository separately |
| **One branch per repository, and a URL can be added once.** | The URL is stored without the branch and is unique, so the same repository on two branches is a duplicate (`409`) | Change the branch with the update endpoint when no run is active, then reprocess. That replaces the index |
| **Entity bodies are cut.** A parsed body keeps 60 lines and 2000 characters. `content` in Algolia keeps 2000 characters of body, and a record is trimmed to 9000 bytes. | Algolia rejects batches with a record over 10 KB | Use `get_file` for the full text. SQLite keeps the whole file |
| **Markdown sections use ATX headings only** (`#` to `######`). | The heading scanner matches ATX syntax | Use ATX headings |
| **Python files `ast` cannot parse use a line scanner.** | Python 2 sources, templates and very deep nesting fail `ast` | None needed. They are still indexed |
| **Framework detection is best effort.** It reads `package.json` and Python imports only. | A guess from two sources | Set the framework with the update endpoint if it matters |
| **A failed download fails the whole run.** | Skipping a file could replace a complete index with a partial one | Reprocess |

## Hosts and access

| Limitation | Why | Workaround |
| --- | --- | --- |
| **The dashboard and `POST /api/v1/repositories/` take github.com only.** | The REST schema checks the host. Other hosts go through the `add_repository` tool, which the dashboard has no form for | Ask Claude to add the repository. It then appears in the dashboard |
| **Other hosts are public only, over https, with no port or credentials.** | Git runs without prompts or a credential helper, so a private repository cannot authenticate | Make the repository public, or mirror it on github.com |
| **Private repositories work on github.com only**, with one server-wide `GITHUB_TOKEN`. | The token belongs to the server, so every user sees what it can read | Use a token with the narrowest access you can |
| **Source links exist for GitHub, GitLab and Bitbucket only.** GitLab means `gitlab.com` or a host starting with `gitlab.`. | The link format is host specific | Other hosts get results without a `url` |
| **Other hosts need `git` in the image or on the machine.** | The clone uses the git command line | Both backend images install it |
| **The URL check reads the URL text and does not resolve DNS.** | It refuses `localhost`, `.localhost` names and non-public IP literals | Run CodeSage where it should not reach internal hosts, or restrict egress |

## Security model

| Limitation | Why | Workaround |
| --- | --- | --- |
| **One shared API key and no user accounts.** Whoever holds the key, or passes nginx's login, sees every repository. | The design is single-user first | Keep access to people who may see all of it |
| **In the dev setup the key is inside the JavaScript bundle.** | Vite inlines `VITE_*` variables | Dev stays on loopback. Use the prod stack for sharing |
| **Search queries appear in the backend log.** | The search code logs the query text | Treat the log as sensitive |
| **`ALLOWED_HOSTS=*` turns off DNS-rebinding protection.** | It allows any `Host` | List exact names |
| **No audit trail.** | Logs record requests, not who made them | Add logging at nginx |

## Search

| Limitation | Why | Workaround |
| --- | --- | --- |
| **Searching all repositories includes ones being reprocessed.** | A named repository must be `completed`, but a search without a name only filters on the query | Name the repository |
| **A reprocess briefly leaves a repository with no records.** | The old records are deleted before the new ones are indexed | Wait for `completed` |
| **Ranking is relevance first.** `rank_weight` only breaks ties. | It is the index's `customRanking` | See [Search](/docs/concepts/search/#ranking) |
| **Plain-words queries are English.** `queryLanguages` is `["en"]`. | Stop-word and plural rules are English | Use keywords in other languages |
| **Delete returns before Algolia finishes.** | Algolia applies tasks in order, so a later re-add still lands after the delete | None needed |
| **Suggestions need at least 2 characters** and return nothing on any error. | A broken suggestion box should not break the page | Use search |
| **A synchronous Algolia client.** Calls run in worker threads. | The v3 client has no async API | None |

## MCP tools and the bridge

| Limitation | Why | Workaround |
| --- | --- | --- |
| **The backend must be running.** The bridge does not start it. | The bridge holds no data | `make start-backend` |
| **`get_file` returns at most 400 lines and 100,000 characters per call.** | A minified file could otherwise return megabytes | Call again with a later `start_line` |
| **`find_patterns` has time limits.** A regex gets 1 s per file and 10 s per call. Files over 1,000,000 characters are skipped. A pattern is at most 200 characters. | The `regex` module's timeouts guard against catastrophic patterns | Use a literal search, which has no time limit, or a narrower `path_glob` |
| **`list_definitions` returns at most 500 definitions** and `search_code` at most 50 per page. | Argument limits in the schema | Page through, or narrow the filters |
| **The files resource lists the first 5000 files.** | `MAX_RESOURCE_FILES` | `truncated` tells you |
| **Tools and resources only.** No prompts. | The server declares `prompts: false` | None |
| **`--basic-auth` and the Keychain are macOS only.** | They use the `security` command | Set `CODESAGE_BASIC_AUTH_PASSWORD` in the bridge's `env` |
| **Tool calls are limited to 30 a minute per address.** | `RATE_LIMIT_AI` | Raise `RATE_LIMIT_AI` or wait |

## WebSocket

| Limitation | Why | Workaround |
| --- | --- | --- |
| 200 connections in total, 20 per client address, 100 subscriptions per connection. | Each holds a socket and a task | Close unused tabs |
| A client that stalls for 5 seconds is dropped. | A stuck tab must not slow a run | The page also polls every 3 seconds |

## Tests and CI

| Limitation | Why | Workaround |
| --- | --- | --- |
| **Frontend tests are unit tests only.** | Vitest with jsdom | Test the dashboard in a browser |
| **CI never runs the Docker stacks.** It validates the Compose files and nginx configs, and builds the prod backend image and the frontend image. It does not build the dev backend image. | A full stack needs Algolia and GitHub access | Test your own deployment. The prod stack was last run by hand with a self-signed certificate |

See also [Troubleshooting](/docs/troubleshooting/) and the [FAQ](/docs/faq/).
