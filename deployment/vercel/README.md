# Public demo on Vercel

https://codesage-demo.vercel.app is CodeSage with `READ_ONLY=true`, on Vercel's free Hobby plan and Algolia's free plan. Anyone can search and browse three indexed repositories (pmndrs/zustand, pallets/click and CodeSage itself), and any MCP client can use them at https://codesage-demo.vercel.app/mcp with no key. Nothing can be added, reprocessed or deleted.

## Build and deploy

```bash
make demo-build                  # index the repositories and lay out build/demo/
make demo-build ARGS=--reindex   # rebuild the data too, then redeploy
make demo-deploy                 # vercel deploy --prod from build/demo/
```

`scripts/build_demo.py` does the work:

1. **Index.** It indexes the repositories into a fresh SQLite file and their own Algolia index, both built aside (`demo.db.building`, `codesage_demo_build`). Only when every repository is complete does it move the index onto `codesage_demo` and rename the file to `build/demo/demo.db`, so a failed rebuild leaves the live demo as it was. It uses the Algolia admin key and GitHub token from `backend/.env`, or from `--env-file`. Search by meaning is off, so no embeddings key is used. It folds the WAL into the file, since the demo opens it read-only and can't replay one. This step runs only when `demo.db` is missing or you pass `--reindex`. Otherwise an existing `demo.db` is brought to the latest migration, which leaves its data as it is, since the demo refuses to start on an older schema.
2. **Lay out.** It copies `backend/app`, `codesage_mcp`, `alembic` and `requirements.txt`, plus the files in this folder. It builds the dashboard into `public/` with no API key and copies its `index.html` to `dashboard.html`.

The files here:
- **`vercel.json`.** Selects Vercel's FastAPI preset.
- **`index.py`.** The entry point. It is the CodeSage app plus two additions:
  - It answers the dashboard's routes (`/dashboard`, `/search`, `/repository/...`) with the dashboard page. Vercel serves `public/` only for paths that are files, and a rewrite would reach the function, not `public/`.
  - It takes each request's client address from `x-real-ip`, which Vercel's edge sets itself, so rate limits count each visitor on their own.
- **`.python-version`.** Pins Python 3.13.

## One-time setup

The project is `codesage-demo` on Vercel; `vercel link --project codesage-demo` in `build/demo/` links it. Its production environment variables:

| Variable | Value |
| --- | --- |
| `READ_ONLY` | `true` |
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | `sqlite:///file:demo.db?mode=ro&immutable=1&uri=true` (the function's working directory is the project root) |
| `ALGOLIA_APP_ID` | your app ID |
| `ALGOLIA_INDEX_NAME` | `codesage_demo` |
| `ALGOLIA_ADMIN_API_KEY` | a key with only the `search` and `listIndexes` ACLs, restricted to `codesage_demo`, stored as a sensitive variable. The backend reads its Algolia key from this name, and read-only mode never writes |
| `CORS_ORIGINS` | `https://codesage-demo.vercel.app` |

There is no `CODESAGE_API_KEY`: a read-only server needs none. Delete the `.env.local` that `vercel link` writes, so a Vercel token can't end up in a deployment.

## What to expect

- **Size and speed.** The function bundle is about 73 MB, under Vercel's 500 MB limit. A warm request takes 0.15 to 0.3 s and a cold start about 4 s. `demo.db` is about 5.5 MB.
- **A snapshot.** The data is what `--reindex` last built. The scheduled refresh and webhooks don't run.
- **No live updates.** Vercel functions don't keep WebSockets open. The dashboard opens one only while a run is in progress, which never happens here.
- **Limits.**
  - Rate limits live in each function instance, so they hold per instance, not across the deployment.
  - ChatGPT calls `/mcp` from OpenAI's servers, so all ChatGPT users share those servers' addresses, and so their rate limits.
  - Algolia's free plan has a monthly search quota with no overage charges. If the demo uses it up, search stops until the month resets.
