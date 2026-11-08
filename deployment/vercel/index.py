"""Vercel entry point for the read-only demo: the CodeSage app plus two things Vercel needs.

- The dashboard's own routes answer with its page. Vercel serves public/ for paths that are files,
  such as / and /assets/..., but sends a rewritten path to this function, not to public/.
- Each request's client address comes from x-real-ip. Vercel's edge sets that header itself, so a
  visitor can't choose it; without this, rate limits could count every visitor as one client.
"""

from pathlib import Path

from fastapi.responses import HTMLResponse

from app.main import app

# The built index.html, copied here by scripts/build_demo.py
DASHBOARD = (Path(__file__).parent / "dashboard.html").read_text()


async def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD)


for path in ("/dashboard", "/search", "/repository/{rest:path}"):
    app.add_api_route(path, dashboard, include_in_schema=False)


class RealClientAddress:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            ip = dict(scope["headers"]).get(b"x-real-ip")
            if ip:
                scope = {**scope, "client": (ip.decode("latin-1"), 0)}
        await self.app(scope, receive, send)


app.add_middleware(RealClientAddress)
