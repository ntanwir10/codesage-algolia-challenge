# CodeSage frontend

The React dashboard for CodeSage: pages, commands, configuration, and how it talks to the backend over REST and WebSocket. It is for anyone changing the frontend code. For the project overview and quick start, see the [root README](../README.md).

The stack is React 19, TypeScript, Vite 7, Tailwind CSS, TanStack Query, React Router 7 and Axios.

## Pages

Three routes, all rendered inside a shared layout (header, footer and a connection-status badge). They are defined in `src/App.tsx`.

| Route | Page | What you can do |
| --- | --- | --- |
| `/` | `HomePage` | Add a repository from a GitHub URL (optionally with a branch), then land on its repository page. |
| `/dashboard` | `DashboardPage` | List all repositories with status and progress. Open one with "View Details", delete one, or go to `/` through "Add Repository". There is no reprocess here. |
| `/repository/:id` | `RepositoryPage` | See status, progress and statistics. When the repository is `completed`, search it with suggestions and open hits on GitHub. Reprocess or delete it. |

- **Search.** It has query suggestions and paging (10 hits per page). There is no filter UI. Search is enabled only once the repository is `completed`.
- **Reprocess.** It is offered on the repository page for a completed or failed repository. It calls `POST /repositories/{id}/process?force_reprocess=true`.
- **Delete.** Both pages ask for confirmation first. The backend refuses to delete a repository while its job is running.
- **Not found.** Any other path renders nothing inside the layout, because `App.tsx` has no catch-all route.

## Commands

Run these from `frontend/`. From the repo root, `make start-frontend` runs `npm run dev`.

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server on http://localhost:5173 |
| `npm run build` | `tsc -b && vite build`, output in `dist/` |
| `npm run preview` | Serves the built `dist/` locally |
| `npm run lint` | ESLint |
| `npm test` | `vitest run`, one pass, jsdom |

The dev server proxies `/api`, `/ws` (with WebSocket upgrade) and `/health` to `127.0.0.1:8001`, so start the backend first (`make start-backend`). The app therefore uses same-origin `/api/v1` and `/ws` in development. In Docker, nginx does the same proxying.

## Configuration

Put these in `frontend/.env.local` for development (see `.env.example`). In Docker they are build arguments; see [deployment/DOCKER.md](../deployment/DOCKER.md).

| Variable | Default | Notes |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | A trailing slash is dropped, and `/api/v1` is appended if missing, so a bare backend origin works. |
| `VITE_CODESAGE_API_KEY` | unset | Must equal `CODESAGE_API_KEY` in `backend/.env`. Sent as `X-API-Key` and in a WebSocket subprotocol. |
| `VITE_WS_URL` or `VITE_WEBSOCKET_URL` | unset | WebSocket URL. Unset means same-origin `/ws`, using `wss:` on https pages and `ws:` otherwise. `VITE_WS_URL` wins if both are set. |
| `VITE_ENABLE_DEV_TOOLS` | unset | `true` shows the React Query devtools. |

- **The key is public.** Vite inlines `VITE_*` values into the JavaScript bundle, so anyone who can load the app can read the API key. Use this setup for local, single-user work. The prod stack keeps the key in nginx instead; see [Security](../README.md#security) in the root README.
- **Rebuild after changes.** The values are fixed at build time, so restart `npm run dev` or rebuild after editing them.

## Talking to the backend

`src/services/api.ts` exports one `CodeSageAPI` instance on top of Axios, with a 30 s timeout.

- **Base URL.** It comes from `VITE_API_BASE_URL`, as above. Request paths are relative and must not repeat `/api/v1`.
- **API key.** A request interceptor sets `X-API-Key` when `VITE_CODESAGE_API_KEY` is set.
- **401 responses.** A response interceptor calls `notifyAuthError()`. The layout listens for it and shows an "API key rejected" toast. Notices are throttled to one per 5 s.
- **Retries.** TanStack Query does not retry 4xx responses. Other failures retry up to 3 times.
- **Coverage.** It wraps repository CRUD, status and stats, reprocess, search, search suggestions and the MCP tool endpoints under `/ai/mcp`.

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
- **Code 1008.** The server rejected the key. The client stops retrying, logs a hint to check `VITE_CODESAGE_API_KEY`, and raises the same toast as an HTTP 401.
- **Idle close.** The socket opens only while something is subscribed. One second after the last unsubscribe it closes with 1000. A tab that becomes visible again with subscribers and no socket reconnects at once.
- **Cache updates.** Each `repository_status` frame patches the cached repository, and the repository list, with the new status and file counts. A status change, or a move to `completed` or `failed`, also invalidates the repository, status, stats and list queries, so they refetch.
- **Subscriptions.** The repository page subscribes to its own repository. The dashboard subscribes to the repositories that are `pending` or `processing`.
- **Toasts.** `Layout` runs one global listener (`useStatusToasts.ts`) that shows completion and failure toasts. The connection badge also lives in `Layout`.
- **Polling.** WebSocket frames are not the only source. `src/lib/polling.ts` makes TanStack Query refetch every 3 s (`POLL_INTERVAL_MS`) while a repository is `pending` or `processing`, and stop once it is `completed` or `failed`. The repository, status and stats queries use `pollWhileActive`; the dashboard list uses `pollWhileAnyActive`.

## Layout

```
src/
  App.tsx             routes, providers, optional React Query devtools
  main.tsx            entry point
  pages/              HomePage, DashboardPage, RepositoryPage
  components/
    features/         search-interface, repository-stats
    forms/            github-form (URL and branch validation)
    layout/           Layout (header, footer, global toasts)
    ui/               buttons, cards, toast, status badge, connection badge, dialogs
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
| Pages | `HomePage`, `DashboardPage`, `RepositoryPage` |
| Services | `api` (key header, base URL, 401 handling), `websocket` (welcome-based status, subscriptions, heartbeat, backoff, 1008 and 1013, key subprotocol) |
| Components | `search-interface`, `github-form`, `animated-progress`, `toast` |
| Lib | `polling`, `queryClient` |

They are unit tests only. Nothing runs against a real backend or browser.
