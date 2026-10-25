# CodeSage frontend

React 19 + TypeScript dashboard built with Vite, Tailwind CSS, TanStack Query, React Router and Axios. It lets you add GitHub repositories, watch indexing progress, and search the indexed code.

## Pages

- `/` home page
- `/dashboard` repository list and add form
- `/repository/:id` status, statistics and search for one repository

## Commands

```bash
npm install
npm run dev       # Vite dev server on http://localhost:5173
npm test          # vitest unit tests (jsdom)
npm run lint      # eslint
npm run build     # tsc -b && vite build, output in dist/
```

From the repo root, `make start-frontend` runs `npm run dev`.

## Talking to the backend

In development, `vite.config.ts` proxies `/api`, `/ws` and `/health` to `127.0.0.1:8001`, so start the backend first (`make start-backend`). The app uses same-origin `/api/v1` and `/ws`; in Docker, nginx does the same proxying.

| Variable | Purpose |
| --- | --- |
| `VITE_CODESAGE_API_KEY` | Sent as `X-API-Key` on requests and in a WebSocket subprotocol (never in the URL). Must equal `CODESAGE_API_KEY` in `backend/.env`. |
| `VITE_API_BASE_URL` | Overrides the API base URL (default `/api/v1`) |
| `VITE_WS_URL` (or `VITE_WEBSOCKET_URL`) | Overrides the WebSocket URL (default: same origin, `ws:` or `wss:` following the page) |

Put them in `frontend/.env.local` for development. In Docker they are build arguments (see `deployment/DOCKER.md`).

Warning: Vite inlines `VITE_*` values into the bundle, so the API key is visible to anyone who can load the app. Use this setup for local, single-user work only.

## Live updates

The app subscribes to `/ws` for repository status frames (`{type, data}`) and also polls the status endpoint while a repository is `pending` or `processing`. The client counts as connected, and sends its subscriptions, only once the server's `connected` frame arrives. If the server rejects the key (close code 1008), the WebSocket client stops retrying and logs a hint to check `VITE_CODESAGE_API_KEY`. Any other close, including 1013 from a full server, is retried with exponential backoff (capped at 30 s), which resets only after a `connected` frame.

## Layout

```
src/pages/        route components
src/components/   features, forms, layout, ui
src/services/     api.ts (HTTP + MCP tool calls), websocket.ts
src/hooks/        realtime status and toast hooks
src/lib/          polling, query client, error helpers
src/types/        API types
src/test/         vitest setup
```

Tests sit next to the code as `*.test.ts(x)`. They are unit tests only.
