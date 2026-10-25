"""API key auth, rate limiting, URL validation and error handling"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings, validate_runtime_settings
from app.core.security import limiter
from app.models.repository import Repository

LOCAL = ("127.0.0.1", 50000)  # TestClient's default peer, "testclient", is not a loopback address

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
    monkeypatch.setattr(get_settings(), "allowed_hosts", "codesage.example.com")
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
        https_client = TestClient(client.app, base_url="https://localhost", client=LOCAL)
        response = https_client.post(REPOS, json={"url": URL}, headers={"Origin": "https://localhost"})
        assert response.status_code == 201

    def test_cross_site_reads_are_served(self, client):
        assert client.get(REPOS, headers={"Origin": EVIL}).status_code == 200

    def test_cross_site_websocket_is_refused(self):
        from fastapi import WebSocketDisconnect

        from app.main import app

        ws_client = TestClient(app, client=LOCAL)
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

    def test_with_a_key_only_allowed_hosts_are_served(self, client, api_key, monkeypatch):
        # DNS rebinding still matters with a key: the dev bundle embeds it, so a rebound page can read it
        assert client.get(REPOS, headers={"Host": "codesage.example.com"}).status_code == 200
        assert client.get(REPOS, headers={"Host": "127.0.0.1:8001"}).status_code == 200
        rebound = {"Host": "evil.example", "Origin": "http://evil.example", "X-API-Key": api_key}
        response = client.post(REPOS, json={"url": URL}, headers=rebound)
        assert response.status_code == 403
        assert response.json()["detail"] == "Host not allowed"
        # CORS_ORIGINS hosts count, without their scheme or port
        monkeypatch.setattr(get_settings(), "cors_origins", "https://app.example.org:8443")
        assert client.get(REPOS, headers={"Host": "app.example.org:8443"}).status_code == 200

    @pytest.mark.parametrize("entry", ["codesage.example.com:8443", "[2001:db8::1]", " Codesage.Example.com "])
    def test_allowed_hosts_entries_match_without_their_port(self, client, api_key, monkeypatch, entry):
        monkeypatch.setattr(get_settings(), "allowed_hosts", entry)
        host = "[2001:db8::1]:8001" if "[" in entry else "codesage.example.com:8443"
        assert client.get(REPOS, headers={"Host": host}).status_code == 200

    def test_a_wildcard_entry_allows_subdomains_only(self, client, api_key, monkeypatch):
        monkeypatch.setattr(get_settings(), "allowed_hosts", "*.example.org")
        assert client.get(REPOS, headers={"Host": "app.example.org"}).status_code == 200
        assert client.get(REPOS, headers={"Host": "a.b.example.org:8443"}).status_code == 200
        assert client.get(REPOS, headers={"Host": "evilexample.org"}).status_code == 403
        assert client.get(REPOS, headers={"Host": "example.org.evil.com"}).status_code == 403

    def test_with_a_key_a_request_without_host_is_served(self, client, api_key):
        # HTTP/1.0 clients may omit Host; browsers never do, so it can't be a rebound page
        from app.core.security import request_refusal

        scope = {"type": "http", "method": "GET", "path": REPOS, "headers": [], "client": LOCAL}
        assert request_refusal(scope) is None

    def test_without_a_key_a_request_without_host_is_refused(self):
        from app.core.security import request_refusal

        scope = {"type": "http", "method": "GET", "path": REPOS, "headers": [], "client": LOCAL}
        assert request_refusal(scope) == "Host not allowed"

    def test_the_host_list_is_parsed_once_and_follows_setting_changes(self, api_key, monkeypatch):
        settings = get_settings()
        first = settings.allowed_hosts_list
        assert settings.allowed_hosts_list is first  # cached, not rebuilt per request
        monkeypatch.setattr(settings, "allowed_hosts", "other.example.com")
        assert "other.example.com" in settings.allowed_hosts_list

    def test_allowed_hosts_star_serves_any_host(self, client, api_key, monkeypatch):
        monkeypatch.setattr(get_settings(), "allowed_hosts", "*")
        assert client.get(REPOS, headers={"Host": "anything.example"}).status_code == 200

    def test_health_is_served_on_any_host(self, client, api_key):
        assert client.get("/health", headers={"Host": "10.0.0.5"}).status_code == 200

    @pytest.mark.parametrize(
        ("host", "served"),
        [
            ("LOCALHOST:8001", True),
            ("[::1]:8001", True),
            ("127.0.0.1", True),
            ("evil.com@localhost", False),  # userinfo syntax a URL parser would accept
            ("localhost#.evil.com", False),
            ("[::1", False),
            ("", False),
        ],
    )
    def test_host_is_parsed_strictly_without_a_key(self, client, host, served):
        assert (client.get(REPOS, headers={"Host": host}).status_code == 200) is served

    def test_without_a_key_only_loopback_peers_are_served(self, client):
        # A server bound to 0.0.0.0 by hand: a LAN client can send Host: localhost, not a loopback address
        lan = TestClient(client.app, base_url="http://localhost", client=("192.168.1.20", 50000))
        response = lan.get(REPOS)
        assert response.status_code == 403
        assert response.json()["detail"] == "Only local clients are served without an API key"
        assert TestClient(client.app, base_url="http://localhost", client=("::1", 50000)).get(REPOS).status_code == 200

    def test_without_a_key_a_lan_websocket_is_refused(self):
        from fastapi import WebSocketDisconnect

        from app.main import app

        lan = TestClient(app, client=("192.168.1.20", 50000))
        with pytest.raises(WebSocketDisconnect) as excinfo, lan.websocket_connect("ws://localhost/ws") as ws:
            ws.receive_json()
        assert excinfo.value.code == 1008

    def test_with_a_key_lan_peers_are_served(self, client, api_key):
        lan = TestClient(client.app, base_url="http://codesage.example.com", client=("192.168.1.20", 50000))
        assert lan.get(REPOS).status_code == 200

    def test_null_origin_is_refused(self, client):
        assert client.post(REPOS, json={"url": URL}, headers={"Origin": "null"}).status_code == 403

    def test_refusals_carry_a_request_id(self, client):
        response = client.post(REPOS, json={"url": URL}, headers={"Origin": EVIL})
        assert response.status_code == 403
        assert response.headers["X-Request-ID"]

    def test_same_origin_on_a_non_default_port(self, client, api_key):
        # Prod nginx forwards Host with its port, so an Origin with a port matches it
        https_client = TestClient(client.app, base_url="https://codesage.example.com:8443", client=LOCAL)
        headers = {"Origin": "https://codesage.example.com:8443", "X-API-Key": api_key}
        assert https_client.post(REPOS, json={"url": URL}, headers=headers).status_code == 201


class TestBehindTheProdProxy:
    """uvicorn --forwarded-allow-ips '*' behind nginx, which sets both forwarded headers"""

    @pytest.fixture
    def proxied(self, client, api_key):
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        app = ProxyHeadersMiddleware(client.app, trusted_hosts="*")
        return TestClient(app, base_url="http://codesage.example.com", client=LOCAL)

    def forwarded(self, ip, origin):
        # What nginx sends on: forwarded headers it sets itself, the browser's Origin, the key
        return {"X-Forwarded-For": ip, "X-Forwarded-Proto": "https", "Origin": origin, "X-API-Key": "s3cret"}

    def test_the_forwarded_scheme_decides_the_origin(self, proxied):
        same = self.forwarded("203.0.113.1", "https://codesage.example.com")
        assert proxied.post(REPOS, json={"url": URL}, headers=same).status_code == 201
        plain = self.forwarded("203.0.113.1", "http://codesage.example.com")
        assert proxied.post(REPOS, json={"url": URL}, headers=plain).status_code == 403

    def test_websocket_scheme_follows_the_proxy(self, proxied):
        headers = self.forwarded("203.0.113.1", "https://codesage.example.com")
        with proxied.websocket_connect("ws://codesage.example.com/ws", headers=headers) as ws:
            assert ws.receive_json()["type"] == "connected"

    def test_rate_limits_are_per_client(self, proxied, monkeypatch):
        monkeypatch.setattr(get_settings(), "rate_limit_default", "1/minute")
        origin = "https://codesage.example.com"

        def create(ip, name):
            body = {"url": f"https://github.com/octocat/{name}"}
            return proxied.post(REPOS, json=body, headers=self.forwarded(ip, origin)).status_code

        assert create("203.0.113.1", "a") == 201
        assert create("203.0.113.1", "b") == 429
        assert create("203.0.113.2", "c") == 201  # another client keeps its own budget


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
        "url",
        [
            "not a url",
            "",
            "https://gitlab.com/o/r",
            "https://github.com/onlyowner",
            "https://github.com/../user",  # would call api.github.com/user with the token
            "https://github.com/./r",
        ],
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

    def test_a_null_branch_falls_back_to_the_url_branch(self, client):
        response = client.post(REPOS, json={"url": f"{URL}/tree/dev", "branch": None})
        assert response.json()["branch"] == "dev"

    def test_an_explicit_empty_branch_beats_the_url_branch(self, client):
        response = client.post(REPOS, json={"url": f"{URL}/tree/dev", "branch": ""})
        assert response.json()["branch"] is None

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

    def test_a_duplicate_that_slips_past_the_check_is_409(self, client, monkeypatch):
        # Two creates racing: both pass the lookup, the second insert hits the unique index
        assert client.post(REPOS, json={"url": URL}).status_code == 201
        from sqlalchemy.orm import Query

        monkeypatch.setattr(Query, "first", lambda self: None)
        response = client.post(REPOS, json={"url": URL})
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_the_branch_cannot_change_while_a_job_holds_the_repository(self, client, monkeypatch):
        created = client.post(REPOS, json={"url": URL}).json()
        monkeypatch.setattr("app.api.v1.endpoints.repositories.is_processing", lambda _id: True)
        url = f"{REPOS}{created['id']}"
        assert client.put(url, json={"branch": "dev"}).status_code == 409
        # The run sets these itself when it ends, so an edit now would be overwritten
        response = client.put(url, json={"language": "go", "framework": "gin"})
        assert response.status_code == 409
        assert "language, framework" in response.json()["detail"]
        # Other fields, or the same branch (empty is the same as null), are fine
        assert client.put(url, json={"name": "renamed", "branch": None}).status_code == 200
        assert client.put(url, json={"branch": ""}).status_code == 200

    def test_a_bad_body_is_not_logged_as_a_database_error(self, monkeypatch):
        # FastAPI raises a body's 422 through get_db (the client fixture overrides it, so drive it here)
        from fastapi.exceptions import RequestValidationError

        from app.core import database

        logged = []

        class Logger:
            def error(self, *args, **kwargs):
                logged.append(args)

        monkeypatch.setattr(database, "logger", Logger())
        session = database.get_db()
        next(session)
        with pytest.raises(RequestValidationError):
            session.throw(RequestValidationError([{"loc": ("body", "url"), "input": "secret body"}]))
        assert logged == []

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

    @pytest.mark.parametrize(
        "body", [{"name": None}, {"name": "  "}, {"branch": "../../x"}, {"branch": "a/../b"}]
    )
    def test_put_rejects_a_null_name_or_bad_branch(self, client, body):
        created = client.post(REPOS, json={"url": URL}).json()
        assert client.put(f"{REPOS}{created['id']}", json=body).status_code == 422

    def test_put_accepts_a_branch_or_the_default(self, client):
        created = client.post(REPOS, json={"url": URL}).json()
        # Empty is stored as null, which the UI shows as "default" (it showed "" as a blank)
        for branch, stored in (("feature/x", "feature/x"), ("", None), (None, None)):
            response = client.put(f"{REPOS}{created['id']}", json={"branch": branch})
            assert response.status_code == 200
            assert response.json()["branch"] == stored

    def test_an_empty_branch_on_create_is_stored_as_null(self, client):
        assert client.post(REPOS, json={"url": URL, "branch": ""}).json()["branch"] is None

    def test_explicit_branch_is_validated_on_create(self, client):
        assert client.post(REPOS, json={"url": URL, "branch": "../main"}).status_code == 422


class TestErrors:
    def test_unhandled_error_hides_internals(self, db_session):
        from app.core.database import get_db
        from app.main import app

        def boom():
            raise RuntimeError("secret internal detail")
            yield  # pragma: no cover

        app.dependency_overrides[get_db] = boom
        try:
            response = TestClient(app, base_url="http://localhost", raise_server_exceptions=False, client=LOCAL).get(REPOS)
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

    @pytest.mark.parametrize(("key", "warned"), [("k", True), (None, False)])
    def test_allowed_hosts_star_warns_only_when_it_applies(self, monkeypatch, key, warned):
        # Without a key ALLOWED_HOSTS is ignored, and the loopback-only Host check still holds
        messages = []
        monkeypatch.setattr("app.core.config.logger.warning", lambda message, **_: messages.append(message))
        validate_runtime_settings(Settings(allowed_hosts="*", codesage_api_key=key))
        assert any("ALLOWED_HOSTS" in m for m in messages) is warned

    def test_public_host_with_key_is_allowed(self):
        validate_runtime_settings(Settings(mcp_server_host="0.0.0.0", codesage_api_key="k"))

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
    def test_loopback_without_key_is_allowed(self, host):
        validate_runtime_settings(Settings(mcp_server_host=host, codesage_api_key=None))
