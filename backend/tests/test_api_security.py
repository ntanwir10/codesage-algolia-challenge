"""API key auth, rate limiting, URL validation and error handling"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings, validate_runtime_settings
from app.core.security import limiter
from app.models.repository import Repository

URL = "https://github.com/octocat/hello"
REPOS = "/api/v1/repositories/"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """No key by default, a clean limiter, and no real background jobs"""
    monkeypatch.setattr(get_settings(), "codesage_api_key", None)
    monkeypatch.setattr(
        "app.services.repository_service.start_processing", lambda *a, **k: None
    )
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "codesage_api_key", "s3cret")
    return "s3cret"


class TestApiKey:
    def test_write_without_key_is_401(self, client, api_key):
        response = client.post(REPOS, json={"url": URL})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API key"

    def test_write_with_wrong_key_is_401(self, client, api_key):
        response = client.post(REPOS, json={"url": URL}, headers={"X-API-Key": "nope"})
        assert response.status_code == 401

    def test_write_with_key_succeeds(self, client, api_key):
        response = client.post(REPOS, json={"url": URL}, headers={"X-API-Key": api_key})
        assert response.status_code == 201

    def test_put_and_delete_need_the_key(self, client, db_session, api_key):
        repo = Repository(name="r", url=URL, status="pending")
        db_session.add(repo)
        db_session.commit()
        assert client.put(f"{REPOS}{repo.id}", json={"name": "x"}).status_code == 401
        assert client.delete(f"{REPOS}{repo.id}").status_code == 401
        assert client.post(f"{REPOS}{repo.id}/process").status_code == 401

    def test_gets_need_no_key(self, client, api_key):
        assert client.get(REPOS).status_code == 200
        assert client.get("/health").status_code == 200

    def test_performance_router_needs_the_key(self, client, api_key):
        assert client.get("/api/v1/performance/metrics").status_code == 401
        response = client.get("/api/v1/performance/metrics", headers={"X-API-Key": api_key})
        assert response.status_code != 401

    def test_no_key_configured_allows_writes(self, client):
        assert client.post(REPOS, json={"url": URL}).status_code == 201


EVIL = "https://evil.example"


class TestBrowserRequests:
    def test_cross_site_writes_are_refused_even_with_the_key(self, client, db_session, api_key):
        # Prod nginx adds the key to every request that carries the browser's cached login
        repo = Repository(name="r", url=URL, status="completed")
        db_session.add(repo)
        db_session.commit()
        forged = {"X-API-Key": api_key, "Origin": EVIL}
        process = client.post(f"{REPOS}{repo.id}/process?force_reprocess=true", headers=forged)
        assert process.status_code == 403
        assert process.json()["detail"] == "Cross-origin request refused"
        assert client.post("/api/v1/performance/reset", headers=forged).status_code == 403

    @pytest.mark.parametrize("origin", ["http://localhost:5173", "http://localhost"])
    def test_listed_and_same_origin_writes_pass(self, client, origin):
        assert client.post(REPOS, json={"url": URL}, headers={"Origin": origin}).status_code == 201

    def test_same_host_on_another_scheme_is_another_origin(self, client):
        # http://localhost is the request's own origin; https://localhost is not
        response = client.post(REPOS, json={"url": URL}, headers={"Origin": "https://localhost"})
        assert response.status_code == 403
        https_client = TestClient(client.app, base_url="https://localhost")
        response = https_client.post(REPOS, json={"url": URL}, headers={"Origin": "https://localhost"})
        assert response.status_code == 201

    def test_cross_site_reads_are_served(self, client):
        assert client.get(REPOS, headers={"Origin": EVIL}).status_code == 200

    def test_cross_site_websocket_is_refused(self):
        from fastapi import WebSocketDisconnect

        from app.main import app

        ws_client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as excinfo, ws_client.websocket_connect(
            "ws://localhost/ws", headers={"Origin": EVIL}
        ) as ws:
            ws.receive_json()
        assert excinfo.value.code == 1008
        with ws_client.websocket_connect(
            "ws://localhost/ws", headers={"Origin": "http://localhost:5173"}
        ) as ws:
            assert ws.receive_json()["type"] == "connected"
        # ws:// maps to http://, so a page served from the API's own host connects
        with ws_client.websocket_connect("ws://localhost/ws", headers={"Origin": "http://localhost"}) as ws:
            assert ws.receive_json()["type"] == "connected"

    def test_without_a_key_only_loopback_hosts_are_served(self, client):
        # DNS rebinding: a hostile page re-pointed at 127.0.0.1 still sends its own Host
        assert client.get(REPOS, headers={"Host": "evil.example:8001"}).status_code == 403
        assert client.get(REPOS, headers={"Host": "127.0.0.1:8001"}).status_code == 200
        assert client.get(REPOS, headers={"Host": "[::1]:8001"}).status_code == 200

    def test_with_a_key_any_host_is_served(self, client, api_key):
        assert client.get(REPOS, headers={"Host": "codesage.example.com"}).status_code == 200


class TestRateLimit:
    def test_limit_returns_429(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "rate_limit_default", "2/minute")
        statuses = [
            client.post(REPOS, json={"url": f"https://github.com/o/r{i}"}).status_code
            for i in range(3)
        ]
        assert statuses == [201, 201, 429]


class TestUrlValidation:
    @pytest.mark.parametrize(
        "url", ["not a url", "", "https://gitlab.com/o/r", "https://github.com/onlyowner"]
    )
    def test_bad_urls_are_422(self, client, url):
        assert client.post(REPOS, json={"url": url}).status_code == 422

    def test_missing_url_is_422(self, client):
        assert client.post(REPOS, json={"name": "x"}).status_code == 422

    def test_url_is_normalised_and_name_defaulted(self, client):
        response = client.post(REPOS, json={"url": "https://github.com/octocat/hello.git/"})
        assert response.status_code == 201
        body = response.json()
        assert body["url"] == URL
        assert body["name"] == "octocat/hello"

    def test_branch_is_taken_from_the_url(self, client):
        response = client.post(REPOS, json={"url": f"{URL}/tree/dev"})
        assert response.json()["branch"] == "dev"
        assert response.json()["url"] == URL

    def test_explicit_branch_wins(self, client):
        response = client.post(REPOS, json={"url": f"{URL}/tree/dev", "branch": "main"})
        assert response.json()["branch"] == "main"

    def test_duplicate_url_is_409(self, client):
        assert client.post(REPOS, json={"url": URL}).status_code == 201
        assert client.post(REPOS, json={"url": URL + ".git"}).status_code == 409

    def test_limit_must_be_positive(self, client):
        assert client.get(REPOS, params={"limit": 0}).status_code == 422

    def test_put_cannot_change_status(self, client):
        created = client.post(REPOS, json={"url": URL}).json()
        response = client.put(
            f"{REPOS}{created['id']}", json={"status": "completed", "name": "renamed"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "pending"
        assert response.json()["name"] == "renamed"


class TestErrors:
    def test_unhandled_error_hides_internals(self, db_session):
        from app.core.database import get_db
        from app.main import app

        def boom():
            raise RuntimeError("secret internal detail")
            yield  # pragma: no cover

        app.dependency_overrides[get_db] = boom
        try:
            response = TestClient(app, base_url="http://localhost", raise_server_exceptions=False).get(REPOS)
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 500
        body = response.json()
        assert body["detail"] == "Internal server error"
        assert "secret internal detail" not in response.text
        assert body["request_id"] == response.headers["X-Request-ID"]

    def test_request_id_is_reused_or_generated(self, client):
        echoed = client.get("/health", headers={"X-Request-ID": "abc-123"})
        assert echoed.headers["X-Request-ID"] == "abc-123"
        assert client.get("/health").headers["X-Request-ID"]


class TestHealthAndMcp:
    def test_health_without_algolia(self, client, monkeypatch):
        import app.main as main

        class NoAlgolia:
            client = None

        monkeypatch.setattr(main, "AlgoliaService", NoAlgolia)
        monkeypatch.setattr(main, "_algolia_check", None)
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["components"]["algolia"]["status"] == "not_configured"
        assert body["components"]["database"]["status"] == "healthy"
        assert body["timestamp"] != "2024-01-01T00:00:00Z"
        assert "mcp_server" not in body["components"]


class TestRuntimeSettings:
    def test_wildcard_cors_is_refused(self):
        with pytest.raises(RuntimeError, match="CORS"):
            validate_runtime_settings(Settings(cors_origins="http://a.com,*"))

    def test_public_host_without_key_is_refused(self):
        with pytest.raises(RuntimeError, match="CODESAGE_API_KEY"):
            validate_runtime_settings(
                Settings(mcp_server_host="0.0.0.0", codesage_api_key=None)
            )

    def test_public_host_with_key_is_allowed(self):
        validate_runtime_settings(Settings(mcp_server_host="0.0.0.0", codesage_api_key="k"))

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
    def test_loopback_without_key_is_allowed(self, host):
        validate_runtime_settings(Settings(mcp_server_host=host, codesage_api_key=None))
