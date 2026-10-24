from app.models.repository import Repository

BASE = "/api/v1/ai"


def call(client, tool, **arguments):
    return client.post(f"{BASE}/mcp/tools/call", json={"tool_name": tool, "arguments": arguments})


def test_tools_list_has_input_schemas(client):
    body = client.get(f"{BASE}/mcp/tools").json()
    names = [t["name"] for t in body["tools"]]
    assert body["count"] == len(names) == 6
    assert set(names) == {"list_repositories", "search_code", "get_file", "list_definitions",
                          "analyze_repository", "find_patterns"}
    search = next(t for t in body["tools"] if t["name"] == "search_code")
    assert search["description"] and search["inputSchema"]["properties"]["limit"]["maximum"] == 50


def test_call_success_shape(client, db_session):
    db_session.add(Repository(name="r", url="https://github.com/o/r", status="completed"))
    db_session.commit()
    resp = call(client, "list_repositories")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "list_repositories" and body["is_error"] is False and body["error"] is None
    assert body["result"]["repositories"][0]["name"] == "r"


def test_call_tool_error_is_200_with_is_error(client):
    resp = call(client, "get_file", repository="nope", path="x")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_error"] is True and body["result"] is None and "not found" in body["error"]


def test_call_unknown_tool_404(client):
    assert call(client, "explore_functions").status_code == 404


def test_call_bad_arguments_422(client):
    resp = call(client, "search_code", query="x", limit=500)
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["limit"]
    assert call(client, "search_code").status_code == 422


def test_get_on_call_route_is_gone(client):
    assert client.get(f"{BASE}/mcp/tools/call").status_code == 405


def test_capabilities(client):
    body = client.get(f"{BASE}/mcp/capabilities").json()
    assert body["name"] and body["version"]
    assert body["capabilities"] == {"tools": True, "resources": True, "prompts": False}
    assert "find_patterns" in body["tools"]


def test_resources(client, db_session):
    listing = client.get(f"{BASE}/mcp/resources").json()
    assert listing["resources"][0]["uri"] == "codesage://repositories"
    ok = client.get(f"{BASE}/mcp/resources/read", params={"uri": "codesage://repositories"})
    assert ok.status_code == 200 and ok.json()["content"] == {"repositories": []}
    bad = client.get(f"{BASE}/mcp/resources/read", params={"uri": "codesage://repositories/x/files"})
    assert bad.status_code == 404


def test_suggestions_distinct(client, algolia_index):
    seen = []

    def fake_search(q, params):
        seen.append(params)
        return {"hits": [{"entity_name": n} for n in ["create", "create", "createStore", "other"]]}

    algolia_index.search = fake_search
    resp = client.get(f"{BASE}/search/suggestions", params={"query": "cre", "limit": 2})
    assert resp.json() == {"suggestions": ["create", "createStore"]}
    assert seen[-1]["hitsPerPage"] == 4


def test_suggestions_short_query(client, algolia_index):
    assert client.get(f"{BASE}/search/suggestions", params={"query": "c"}).json() == {"suggestions": []}
    assert algolia_index.searches == []


def test_suggestions_algolia_unavailable(client, algolia_index):
    def boom(q, params):
        raise RuntimeError("down")

    algolia_index.search = boom
    resp = client.get(f"{BASE}/search/suggestions", params={"query": "create"})
    assert resp.status_code == 200 and resp.json() == {"suggestions": []}
