"""Semantic search, bring your own key: vectors from an OpenAI-compatible endpoint (faked here)"""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.core.config import get_settings
from app.models.code_entity import CodeEntity
from app.models.repository import Repository
from app.services import embeddings
from app.services.github_service import GitHubFile
from app.services.mcp_tools import ToolError, call_tool
from app.services.repository_service import RepositoryService

VOCABULARY = ["retry", "store", "parse", "render"]
RETRY = "def retry_request(url):\n    # retry with backoff\n    return url\n"
STORE = "import os\n\ndef create_store(state):\n    return state\n"


def vector(text: str) -> list[float]:
    """Meaning, as far as this fake goes: how often each vocabulary word appears"""
    return [float(text.lower().count(word)) for word in VOCABULARY] + [0.01]


@pytest.fixture
async def provider(monkeypatch):
    """A fake embeddings API on localhost, configured as the server's provider"""
    state = {"requests": [], "status": 200}

    async def handler(request):
        body = await request.json()
        state["requests"].append((request.headers.get("Authorization"), body))
        if state["status"] != 200:
            return web.json_response({"error": {"message": "Incorrect API key sk-...abcd"}}, status=state["status"])
        data = [{"index": i, "embedding": vector(text)} for i, text in enumerate(body["input"])]
        return web.json_response({"data": list(reversed(data))})  # order comes from index, not position

    app = web.Application()
    app.router.add_post("/v1/embeddings", handler)
    server = TestServer(app)
    await server.start_server()
    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_api_url", str(server.make_url("/v1/embeddings")))
    monkeypatch.setattr(settings, "embedding_api_key", "test-key")
    monkeypatch.setattr(settings, "embedding_model", "fake-1")
    try:
        yield state
    finally:
        await server.close()


def github_file(path, content):
    return GitHubFile(path=path, content=content, size=len(content), language="python", filename=path)


@pytest.fixture
def repository(db_session):
    repo = Repository(name="octo/demo", url="https://github.com/octo/demo", status="pending",
                      total_files=0, processed_files=0, total_lines=0)
    db_session.add(repo)
    db_session.commit()
    return repo


async def run(db_session, repository, incremental=False):
    await RepositoryService(db_session).process_repository(repository, force_reprocess=True, incremental=incremental)
    db_session.refresh(repository)


def vectors(db_session):
    return {e.entity_name: e.embedding_model for e in db_session.query(CodeEntity)}


# --- the client ---------------------------------------------------------------


async def test_embed_batches_keeps_order_and_normalises(provider, monkeypatch):
    monkeypatch.setattr(embeddings, "BATCH_SIZE", 2)

    result = await embeddings.embed(["retry", "store", "parse parse", "render", "retry store"])

    assert len(provider["requests"]) == 3
    assert provider["requests"][0] == ("Bearer test-key", {"model": "fake-1", "input": ["retry", "store"]})
    unpacked = [embeddings.unpack(blob) for blob in result]
    assert [max(range(4), key=lambda i: v[i]) for v in unpacked[:4]] == [0, 1, 2, 3]
    assert all(abs(embeddings.similarity(v, v) - 1) < 1e-5 for v in unpacked)


async def test_embed_errors_say_the_status_but_never_echo_the_provider(provider):
    provider["status"] = 401

    with pytest.raises(embeddings.EmbeddingError) as caught:
        await embeddings.embed(["retry"])

    assert str(caught.value) == "The embedding API answered 401; check EMBEDDING_API_KEY"


# --- indexing -----------------------------------------------------------------


async def test_indexing_embeds_definitions_but_not_imports(db_session, repository, github, algolia_index, provider):
    github.files = [github_file("a.py", RETRY), github_file("b.py", STORE)]

    await run(db_session, repository)

    assert repository.status == "completed" and repository.error_message is None
    assert vectors(db_session) == {"retry_request": "fake-1", "create_store": "fake-1", "import os": None}
    [(_, body)] = provider["requests"]
    assert body["input"][0].startswith("function retry_request in a.py\ndef retry_request(url):")


async def test_incremental_runs_reuse_vectors_and_a_new_model_re_embeds(
    db_session, repository, github, algolia_index, provider, monkeypatch
):
    github.files = [github_file("a.py", RETRY), github_file("b.py", STORE)]
    await run(db_session, repository)

    await run(db_session, repository, incremental=True)
    assert len(provider["requests"]) == 1  # nothing changed, nothing sent

    monkeypatch.setattr(get_settings(), "embedding_model", "fake-2")
    await run(db_session, repository, incremental=True)
    assert len(provider["requests"]) == 2
    assert set(vectors(db_session).values()) == {"fake-2", None}


async def test_a_failing_provider_still_completes_the_run(db_session, repository, github, algolia_index, provider):
    provider["status"] = 500
    github.files = [github_file("a.py", RETRY), github_file("b.py", STORE)]

    await run(db_session, repository)

    assert repository.status == "completed"
    assert repository.error_message == (
        "Partially indexed: 2 definitions have no semantic search vectors (the embedding API failed)"
    )
    assert len(algolia_index.records) == 3  # keyword search is unaffected


async def test_without_a_key_indexing_sends_nothing(db_session, repository, github, algolia_index, provider, monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_api_key", None)
    github.files = [github_file("a.py", RETRY)]

    await run(db_session, repository)

    assert provider["requests"] == [] and set(vectors(db_session).values()) == {None}


# --- search -------------------------------------------------------------------


async def test_semantic_search_ranks_by_meaning(db_session, repository, github, algolia_index, provider):
    github.files = [github_file("a.py", RETRY), github_file("b.py", STORE)]
    await run(db_session, repository)

    result = await call_tool(db_session, "search_code", {"query": "retry failed requests", "mode": "semantic"})

    assert result["mode"] == "semantic" and result["total_hits"] == 2
    first = result["results"][0]
    assert (first["entity_name"], first["file_path"], first["line_start"], first["repository"]) == (
        "retry_request", "a.py", 1, "octo/demo",
    )
    assert first["score"] > result["results"][1]["score"]
    assert first["url"].startswith("https://github.com/octo/demo/blob/")


async def test_semantic_search_needs_a_key(db_session, repository, provider, monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_api_key", None)

    with pytest.raises(ToolError, match="EMBEDDING_API_KEY"):
        await call_tool(db_session, "search_code", {"query": "retry", "mode": "semantic"})


async def test_semantic_pages_go_past_algolias_1000_hit_limit(
    db_session, repository, github, algolia_index, provider, monkeypatch
):
    from app.services import mcp_tools

    github.files = [github_file("a.py", RETRY), github_file("b.py", STORE)]
    await run(db_session, repository)
    monkeypatch.setattr(mcp_tools, "MAX_SEARCH_HITS", 1)

    result = await call_tool(db_session, "search_code", {"query": "store", "mode": "semantic", "limit": 1, "page": 1})

    assert (result["pages"], len(result["results"])) == (2, 1)


def test_the_suite_never_sees_a_real_embeddings_key():
    assert not embeddings.is_configured()
