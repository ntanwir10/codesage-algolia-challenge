# CodeSage frontend

The React dashboard for CodeSage: pages, commands, configuration, and how it talks to the backend over REST and WebSocket. It is for anyone changing the frontend code. For the project overview and quick start, see the [root README](../README.md).

The stack is React 19, TypeScript, Vite 7, Tailwind CSS, TanStack Query, React Router 7 and Axios.

## Pages

Five routes, all rendered inside a shared layout (header with Home, Dashboard, Search and a theme toggle, footer, and a connection-status badge). They are defined in `src/App.tsx`. The navigation stays visible on phones, and header rows wrap at narrow widths.

| Route | Page | What you can do |
| --- | --- | --- |
| `/` | `HomePage` | Add a repository. Type `owner/repo` or paste a GitHub URL (it becomes `https://github.com/owner/repo`, keeping a `/tree/<branch>` part), or any other https or `git@host:path` URL whose first part is a host name. Optional Branch and Description fields sit below. On success, land on its repository page. |
| `/dashboard` | `DashboardPage` | List every repository with status and progress, loaded 500 at a time. A failed card shows why in red; a completed one with a note shows it in amber. Open one with "View Details", delete one, or go to `/` through "Add Repository". There is no reprocess here. |
| `/repository/:id` | `RepositoryPage` | See status, progress, statistics, the indexed commit and whether the branch has moved since. When the repository is `completed`, search it with suggestions and filters, browse its definitions (`definitions-browser`), and open hits in the file viewer; "source ↗" opens the host. Reprocess (after a confirmation dialog) or delete it. |
| `/repository/:id/file` | `FileViewerPage` | Read an indexed file 400 lines at a time, with the target lines highlighted and the file's definitions beside it. |
| `/search` | `SearchPage` | Search every indexed repository at once; each hit names its repository and opens in its file viewer. |

- **Add errors.** The form checks the input first ("Enter owner/repo for GitHub, or a repository's https URL"). A GitHub `.../tree/<branch>` URL passes, and the server reads the branch from it. Every error from the server appears inline, with no redirect and no toast, and the input is kept: under the Branch field when it is about the branch, otherwise under the repository field. Editing the URL clears the error. The text is the server's message, or a fixed one for a timeout ("took too long"), no connection, `401` and `500` (with the request ID); a `429` shows the server's text, which says how long to wait. A `409` adds an "Open it" link to the existing repository. The field is tied to its error with `aria-invalid` and `aria-describedby`. Only success shows a toast.
- **Search.** It has query suggestions, paging (10 hits per page), and language and kind filters. With an embeddings key on the server, a third select switches to **By meaning**, which ranks definitions by meaning and suggests by meaning too. Matched words are highlighted (`highlight`). Search is enabled only once the repository is `completed`. For a `failed` repository it says indexing failed and to reprocess; for a `pending` one it shows progress. A failed page change keeps the current results.
- **Reprocess.** It is offered on the repository page for a completed or failed repository, and opens a confirmation dialog first. It calls `POST /repositories/{id}/process?force_reprocess=true`. If a reprocess of a completed repository fails, the page shows "Reprocessing failed; the previous index is still searchable" in amber.
- **Delete.** Both pages ask for confirmation first. The backend refuses to delete a repository while its job is running.
- **Repository errors.** A `404`, or an id that isn't all digits, shows "not found", even if the repository was cached. Any other load error shows the message with "Try again". A failed background refresh keeps the data it has. Deleting a repository that is already gone counts as deleted.
- **Page not found.** Any other path shows "Page not found" with a link home, inside the layout.
- **Render crashes.** An `ErrorBoundary` around the routes catches them and keeps the navigation up. It is keyed by path, so moving to another page clears it.
- **Dashboard errors.** A load error shows the real message. If a refresh fails, the page says it is showing the last loaded data and retries. `pending` counts as processing.

## Commands

Run these from `frontend/`. From the repo root, `make start-frontend` runs `npm run dev`.

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server on http://localhost:5173 |
| `npm run build` | `tsc -b && vite build`, output in `dist/` |
| `npm run preview` | Serves the built `dist/` locally |
| `npm run lint` | ESLint |
| `npm test` | `vitest run`, one pass, jsdom |
| `npm run test:e2e` | Playwright end-to-end tests in Chromium (first: `npx playwright install chromium`) |

The dev server uses `strictPort`: if port 5173 is taken it exits instead of moving to the next port. The dev server proxies `/api`, `/ws` (with WebSocket upgrade) and `/health` to `127.0.0.1:8001`, so start the backend first (`make start-backend`). The app therefore uses same-origin `/api/v1` and `/ws` in development. In Docker, nginx does the same proxying.

## Configuration

Put these in `frontend/.env` for development (see `.env.example`). In Docker they are build arguments; see [deployment/DOCKER.md](../deployment/DOCKER.md).

| Variable | Default | Notes |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | A trailing slash is dropped, and `/api/v1` is appended if missing, so a bare backend origin works. |
| `VITE_CODESAGE_API_KEY` | unset | Must equal `CODESAGE_API_KEY` in `backend/.env`. `make setup`, `make start` and `make install-claude` write it to `frontend/.env` and keep it in sync; restart `npm run dev` after it changes. Sent as `X-API-Key` and in a WebSocket subprotocol. |
| `VITE_WS_URL` or `VITE_WEBSOCKET_URL` | unset | WebSocket URL. Unset means same-origin `/ws`, using `wss:` on https pages and `ws:` otherwise. `VITE_WS_URL` wins if both are set. |
| `VITE_ENABLE_DEV_TOOLS` | unset | `true` shows the React Query devtools. |

- **The key is public.** Vite inlines `VITE_*` values into the JavaScript bundle, so anyone who can load the app can read the API key. Use this setup for local, single-user work. The prod stack keeps the key in nginx instead; see [Security](../README.md#security) in the root README.
- **Rebuild after changes.** The values are fixed at build time, so restart `npm run dev` or rebuild after editing them.

## Talking to the backend

`src/services/api.ts` exports one `CodeSageAPI` instance on top of Axios, with a 30 s timeout.

- **Base URL.** It comes from `VITE_API_BASE_URL`, as above. Request paths are relative and must not repeat `/api/v1`.
- **API key.** A request interceptor sets `X-API-Key` when `VITE_CODESAGE_API_KEY` is set.
- **401 responses.** A response interceptor calls `notifyAuthError()`. The layout listens for it and shows an "API key rejected" toast. It fires once, then stays quiet until a request succeeds or the WebSocket's `connected` frame arrives, because polling keeps getting `401`. A `401` with nginx's `WWW-Authenticate: Basic` challenge is the prod login, not the key, so it raises no toast; the browser asks for the login again.
- **Messages.** `describeError` in `src/lib/errors.ts` turns an error into text: the server's `detail` for most statuses, a fixed line for `401` (the API key, or the site's login when nginx refused it) and `500`, and the server's own message for `429`, `502`, `503` and `504`. A timeout reads "took too long"; no response, or a `500` without the backend's request ID (the Vite proxy's answer when the backend is down), reads "Cannot reach the CodeSage server".
- **Retries.** TanStack Query does not retry 4xx responses. Other failures retry up to 3 times.
- **Coverage.** Repositories (create, list a page, get, delete, reprocess, freshness, stats), search suggestions, capabilities, and the MCP tool call endpoint under `/ai/mcp`, which backs `searchCode`, `getFile` and `listDefinitions`.

## Live updates

`src/services/websocket.ts` holds a single shared `WebSocketService`. `src/hooks/useRealtimeStatus.ts` subscribes pages to it and mirrors each update into the TanStack Query cache.

```mermaid
flowchart TB
    open["Open /ws<br/>key in subprotocol"] --> wait["Status: connecting"]
    wait -- "connected frame" --> up["Status: connected<br/>subscribe, start heartbeat"]
    up -- "no reply to a ping" --> drop["Close with 4000"]
    up -- "socket closes" --> close{"Close code"}
    drop --> backoff["Wait, then reconnect<br/>1 s doubling to 30 s, jittered"]
    close -- "1008" --> stop["Stop retrying<br/>show key-rejected toast"]
    close -- "other, including 1013" --> backoff
    backoff --> open
```

- **Auth.** Browsers cannot set headers on a WebSocket, so the socket offers two subprotocols: `codesage` and `codesage.key.<hex>`, where `<hex>` is the hex-encoded API key. The key never appears in the URL. With no key set, only `codesage` is offered.
- **Connected status.** An open socket still counts as `connecting`. It becomes `connected`, resets the backoff and subscribes only after the server's `connected` frame. A full server accepts the socket and then closes it with 1013, so that is not a connection.
- **Messages.** The client sends `subscribe` and `unsubscribe` with a `repository_id`, and `ping`. The server sends `repository_status` frames shaped `{type, data}`, plus `connected`, `subscribed`, `unsubscribed`, `pong` and `error`.
- **Heartbeat.** The client pings every 25 s. Any incoming frame counts as proof of life. If a whole interval passes with none, the connection is treated as half-open, closed with code 4000 and reconnected.
- **Backoff.** Reconnect delays start at 1 s and double up to 30 s, scaled by 50-100% jitter. Code 1013 has no special handling: it takes this path like any other close. The attempt counter resets on the next `connected` frame.
- **Close reasons.** The server now sends text with its close codes: 1008 "Invalid or missing API key", 1013 "Too many connections; try again later" and 1011 "Internal error". The client does not show the text; it acts on the code.
- **Code 1008.** The server rejected the key. The client stops retrying, logs a hint to check `VITE_CODESAGE_API_KEY`, and raises the same toast as an HTTP 401.
- **Idle close.** The socket opens only while something is subscribed. One second after the last unsubscribe it closes with 1000. A tab that becomes visible again with subscribers and no socket reconnects at once.
- **Cache updates.** Each `repository_status` frame patches the cached repository, and the repository list, with the new status and file counts. A status change, or a move to `completed` or `failed`, also invalidates the repository, stats and list queries, so they refetch.
- **Subscriptions.** The repository page subscribes to its own repository. The dashboard subscribes to the repositories that are `pending` or `processing`, at most 100 (the server's cap per connection).
- **Toasts.** `Layout` runs one global listener (`useStatusToasts.ts`) that shows completion and failure toasts. A reprocess that fails but keeps the previous index gets a yellow "Reprocessing failed" toast. Toasts sit in a live region, and errors use the alert role. The connection badge also lives in `Layout`. It shows "Live updates unavailable." with Reconnect and Dismiss once a connection with subscribers is lost, and stays up between retries until one succeeds.
- **Polling.** WebSocket frames are not the only source. `src/lib/polling.ts` makes TanStack Query refetch while a repository is `pending` or `processing`, and stop once it is `completed` or `failed`: every 15 s (`LIVE_POLL_INTERVAL_MS`) while the WebSocket is connected, every 3 s (`POLL_INTERVAL_MS`) while it isn't. The repository and stats queries use `pollWhileActive`; the dashboard list uses `pollWhileAnyActive`, and every 3 s when more than 100 repositories are active.

## Layout

```
src/
  App.tsx             routes, providers, optional React Query devtools
  main.tsx            entry point
  pages/              HomePage, DashboardPage, RepositoryPage, FileViewerPage, SearchPage
  components/
    ErrorBoundary.tsx  catches render crashes
    features/         search-interface, repository-stats, definitions-browser
    forms/            github-form (URL and branch validation)
    layout/           Layout (header, footer, global toasts), theme-toggle
    ui/               buttons, cards, toast, status badge, connection badge, dialogs, highlight, empty-state
  services/           api.ts (HTTP client), websocket.ts (live-update client)
  hooks/              useRealtimeStatus, useStatusToasts, usePageTitle
  lib/                polling, queryClient, errors, utils
  types/              repository.ts, mcp.ts (API types)
  test/               setup.ts (vitest setup)
```

## Testing

Tests use vitest with jsdom and Testing Library. The config is in `vite.config.ts` (globals on, CSS off, setup in `src/test/setup.ts`). They sit next to the code as `*.test.ts(x)`.

| Area | Test files |
| --- | --- |
| Pages | `HomePage`, `DashboardPage`, `RepositoryPage`, `FileViewerPage` |
| Hooks | `useRealtimeStatus` |
| Services | `api` (key header, base URL, 401 handling), `websocket` (welcome-based status, subscriptions, heartbeat, backoff, 1008 and 1013, key subprotocol) |
| Components | `search-interface`, `definitions-browser`, `github-form`, `animated-progress`, `toast`, `ErrorBoundary`, `connection-status`, `delete-confirmation-dialog`, `highlight`, `theme-toggle` |
| Lib | `polling`, `queryClient`, `errors` |

The Playwright tests in `e2e/` start their own backend on port 8011, with a database seeded by `e2e/seed.py` and no Algolia, GitHub or API key, and Vite on 5183 proxying to it. They cover the Home form's validation and refusal, the dashboard, the repository page and the file viewer, but not search, freshness or indexing.
