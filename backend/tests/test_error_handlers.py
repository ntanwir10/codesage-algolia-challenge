"""One error shape: CORS on 500s, 429 body and Retry-After, health, placeholder settings"""

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.core.config import Settings
from app.core.security import limiter

LOCAL = ("127.0.0.1", 50000)
ALLOWED = "http://localhost:5173"


@pytest.fixture
def boom_client():
    @main.app.get("/_test/boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    try:
        yield TestClient(main.app, base_url="http://localhost", raise_server_exceptions=False, client=LOCAL)
    finally:
        main.app.router.routes[:] = [r for r in main.app.router.routes if getattr(r, "path", None) != "/_test/boom"]


def test_500_carries_cors_headers_for_an_allowed_origin(boom_client):
    response = boom_client.get("/_test/boom", headers={"Origin": ALLOWED})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "Origin" in response.headers["vary"]
    assert response.json()["detail"] == "Internal server error"


def test_500_has_no_cors_headers_for_other_origins(boom_client):
    response = boom_client.get("/_test/boom", headers={"Origin": "http://evil.example"})
    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in boom_client.get("/_test/boom").headers


def test_rate_limit_429_is_detail_with_retry_after(client, monkeypatch):
    limiter.reset()
    monkeypatch.setattr(main.settings, "rate_limit_default", "1/minute")
    url = "/api/v1/repositories/"
    try:
        client.post(url, json={"url": "https://github.com/o/a"})
        response = client.post(url, json={"url": "https://github.com/o/b"})
    finally:
        limiter.reset()
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many requests; try again in 60 seconds."}
    assert response.headers["retry-after"] == "60"


def test_health_is_degraded_when_algolia_is_not_configured(client, monkeypatch):
    class NoAlgolia:
        client = None

    monkeypatch.setattr(main, "AlgoliaService", NoAlgolia)
    monkeypatch.setattr(main, "_algolia_check", None)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["components"]["algolia"]["status"] == "not_configured"


def test_placeholder_settings_count_as_empty():
    settings = Settings(
        _env_file=None,
        algolia_app_id="your-algolia-app-id-here",
        algolia_admin_api_key="your-algolia-admin-api-key-here",
        github_token="your-github-personal-access-token-here",
    )
    assert settings.algolia_app_id is None
    assert settings.algolia_admin_api_key is None
    assert settings.github_token is None
    assert Settings(_env_file=None, github_token="ghp_real").github_token == "ghp_real"
