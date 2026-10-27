import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.code_entity import CodeEntity
from app.models.code_file import CodeFile
from app.models.repository import Repository
from app.services import mcp_tools
from app.services.mcp_tools import ToolError, call_tool, resolve_repository

BACKEND = Path(__file__).resolve().parent.parent


def make_repo(db, name="zustand", url="https://github.com/pmndrs/zustand", status="completed", **kw):
    repo = Repository(name=name, url=url, status=status, **kw)
    db.add(repo)
    db.commit()
    return repo


def add_file(db, repo, path, content, language="typescript"):
    lines = content.count("\n") + 1
    f = CodeFile(
        repository_id=repo.id, file_path=path,
        content=content, language=language, line_count=lines,
    )
    db.add(f)
    db.commit()
    return f


def add_entity(db, f, name, etype="function", start=1, end=3, doc=None):
    e = CodeEntity(
        file_id=f.id, repository_id=f.repository_id, entity_type=etype, entity_name=name,
        start_line=start, end_line=end, signature=f"{name}()", docstring=doc,
    )
    db.add(e)
    db.commit()
    return e


@pytest.fixture
def repo(db_session):
    return make_repo(db_session, branch="main", total_files=2, processed_at=datetime(2026, 1, 2, tzinfo=UTC))


def test_schemas_import_without_app():
    code = (
        "import sys; import codesage_mcp.schemas; "
        "assert not any(m == 'app' or m.startswith('app.') for m in sys.modules)"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_resolve_by_id_name_and_url(db_session, repo):
    assert resolve_repository(db_session, str(repo.id)) is repo
    assert resolve_repository(db_session, "ZUSTAND") is repo
    assert resolve_repository(db_session, "pmndrs/zustand") is repo
    assert resolve_repository(db_session, "PMNDRS/Zustand") is repo


def test_resolve_unknown_lists_available(db_session, repo):
    with pytest.raises(ToolError, match="zustand"):
        resolve_repository(db_session, "nope/missing")
    with pytest.raises(ToolError, match="not found"):
        resolve_repository(db_session, "999")


def test_resolve_ambiguous(db_session, repo):
    make_repo(db_session, name="zustand", url="https://github.com/fork/zustand")
    with pytest.raises(ToolError, match="ambiguous"):
        resolve_repository(db_session, "zustand")
    assert resolve_repository(db_session, "fork/zustand").url.endswith("fork/zustand")


async def test_list_repositories(db_session, repo):
    f = add_file(db_session, repo, "a.ts", "x")
    add_entity(db_session, f, "a")
    add_entity(db_session, f, "b")
    result = await call_tool(db_session, "list_repositories", {})
    [row] = result["repositories"]
    assert row["id"] == repo.id and row["total_entities"] == 2 and row["total_files"] == 2
    assert row["processed_at"].startswith("2026-01-02") and row["processed_at"].endswith("+00:00")
    assert row["error_message"] is None and row["branch"] == "main"


async def test_unknown_tool_and_bad_args(db_session):
    with pytest.raises(KeyError):
        await call_tool(db_session, "explore_functions", {})
    with pytest.raises(ValidationError):
        await call_tool(db_session, "search_code", {"query": "x", "limit": 0})
    with pytest.raises(ValidationError):
        await call_tool(db_session, "search_code", {"query": "x", "repository_id": 3})


HIT = {
    "entity_name": "create", "entity_type": "function", "file_path": "src/vanilla.ts",
    "line_start": 5, "line_end": 20, "language": "typescript", "signature": "create()",
    "content": "x" * 900, "description": "makes a store", "repository_id": None,
}


async def test_search_permalink_and_snippet(db_session, repo, algolia_index):
    seen = []

    def fake_search(q, params):
        seen.append(params)
        return {"hits": [{**HIT, "repository_id": repo.id}], "nbHits": 1, "page": 0, "nbPages": 1}

    algolia_index.search = fake_search
    result = await call_tool(db_session, "search_code", {"query": "create", "repository": "pmndrs/zustand"})
    assert result["total_hits"] == 1 and result["pages"] == 1 and result["repository"] == "zustand"
    [hit] = result["results"]
    assert hit["url"] == "https://github.com/pmndrs/zustand/blob/main/src/vanilla.ts#L5-L20"
    assert len(hit["snippet"]) == 600
    assert seen[-1]["filters"] == f'repository_id={repo.id} AND NOT entity_type:"import"'
    assert seen[-1]["hitsPerPage"] == 10


async def test_permalinks_use_the_indexed_commit(db_session, repo, algolia_index):
    repo.commit_sha = "c0ffee"
    db_session.commit()
    algolia_index.search = lambda q, params: {"hits": [{**HIT, "repository_id": repo.id}], "nbHits": 1}

    result = await call_tool(db_session, "search_code", {"query": "create", "repository": "pmndrs/zustand"})

    assert result["results"][0]["url"] == "https://github.com/pmndrs/zustand/blob/c0ffee/src/vanilla.ts#L5-L20"


@pytest.mark.parametrize("query", ['"', "%%%", "🔍", "<>"])
async def test_a_query_with_nothing_searchable_finds_nothing(db_session, algolia_index, query):
    # Algolia drops punctuation and would match every record
    result = await call_tool(db_session, "search_code", {"query": query})
    assert (result["total_hits"], result["results"]) == (0, [])
    assert algolia_index.searches == []


async def test_pages_past_algolias_first_1000_hits_are_explained(db_session, algolia_index):
    with pytest.raises(ToolError, match="first 1000 hits"):
        await call_tool(db_session, "search_code", {"query": "x", "limit": 10, "page": 100})
    assert algolia_index.searches == []


async def test_search_query_is_capped_in_bytes(db_session, algolia_index):
    # Algolia refuses a query over 512 bytes; a 4-byte emoji reaches that at 129 characters
    with pytest.raises(ValidationError, match="512 bytes"):
        await call_tool(db_session, "search_code", {"query": "🔍" * 129})
    assert algolia_index.searches == []


async def test_search_all_repos_looks_up_hit_repository(db_session, repo, algolia_index):
    other = make_repo(db_session, name="o", url="https://github.com/a/o")  # no branch -> HEAD
    algolia_index.search = lambda q, params: {"hits": [{**HIT, "repository_id": other.id}], "nbHits": 1}
    result = await call_tool(db_session, "search_code", {"query": "create"})
    assert result["repository"] is None
    assert result["results"][0]["url"] == "https://github.com/a/o/blob/HEAD/src/vanilla.ts#L5-L20"


async def test_search_permalink_percent_encodes_branch_and_path(db_session, algolia_index):
    other = make_repo(db_session, name="o", url="https://github.com/a/o", branch="feat/50%")
    hit = {**HIT, "file_path": "docs/setup#linux v2.md", "repository_id": other.id}
    algolia_index.search = lambda q, params: {"hits": [hit], "nbHits": 1}
    result = await call_tool(db_session, "search_code", {"query": "create"})
    assert result["results"][0]["url"] == (
        "https://github.com/a/o/blob/feat/50%25/docs/setup%23linux%20v2.md#L5-L20"
    )


async def test_search_requires_completed(db_session, algolia_index):
    make_repo(db_session, name="busy", url=None, status="processing", total_files=10, processed_files=4)
    with pytest.raises(ToolError, match=r"'busy' is still indexing \(4/10 files\)"):
        await call_tool(db_session, "search_code", {"query": "x", "repository": "busy"})
    assert algolia_index.searches == []


async def test_search_not_configured(db_session, repo, monkeypatch):
    class Unconfigured:
        def is_available(self):
            return False

    monkeypatch.setattr(mcp_tools.algolia_service, "AlgoliaService", Unconfigured)
    with pytest.raises(ToolError, match="Search is not configured on the server.*ALGOLIA_APP_ID"):
        await call_tool(db_session, "search_code", {"query": "x"})


TOOL_ARGS = {
    "search_code": {"query": "x"},
    "get_file": {"path": "a.ts"},
    "list_definitions": {},
    "analyze_repository": {},
    "find_patterns": {"pattern": "x"},
}


@pytest.mark.parametrize("tool", TOOL_ARGS)
@pytest.mark.parametrize(
    ("kw", "message"),
    [
        ({"status": "failed", "error_message": "Rate limited"}, "failed to index: Rate limited. Reprocess"),
        ({"status": "failed"}, "failed to index. Reprocess it from the dashboard."),
        ({"status": "processing", "total_files": 8, "processed_files": 3}, "still indexing (3/8 files); try"),
        ({"status": "pending"}, "still indexing; try again when it completes."),
    ],
)
async def test_tools_refuse_repositories_that_are_not_ready(db_session, algolia_index, tool, kw, message):
    make_repo(db_session, name="r", url=None, **kw)
    with pytest.raises(ToolError, match=r"Repository 'r' ") as excinfo:
        await call_tool(db_session, tool, {"repository": "r", **TOOL_ARGS[tool]})
    assert message in str(excinfo.value)


async def test_search_algolia_failure(db_session, repo, algolia_index):
    def boom(q, params):
        raise RuntimeError("down")

    algolia_index.search = boom
    # The client's text can name the Algolia host or app id, so it stays in the log
    with pytest.raises(ToolError, match="Search is unavailable") as excinfo:
        await call_tool(db_session, "search_code", {"query": "x"})
    assert "down" not in str(excinfo.value)


@pytest.fixture
def lined_file(db_session, repo):
    return add_file(db_session, repo, "src/big.ts", "\n".join(f"line {i}" for i in range(1, 501)))


async def test_get_file_range_and_truncation(db_session, repo, lined_file):
    r = await call_tool(db_session, "get_file", {"repository": "zustand", "path": "src/big.ts",
                                                 "start_line": 10, "end_line": 12})
    assert (r["start_line"], r["end_line"], r["total_lines"], r["truncated"]) == (10, 12, 500, False)
    assert r["content"].splitlines() == ["  10| line 10", "  11| line 11", "  12| line 12"]

    r = await call_tool(db_session, "get_file", {"repository": "zustand", "path": "src/big.ts"})
    assert (r["start_line"], r["end_line"], r["truncated"]) == (1, 400, True)
    assert len(r["content"].splitlines()) == 400

    r = await call_tool(db_session, "get_file", {"repository": "zustand", "path": "src/big.ts", "start_line": 401})
    assert (r["end_line"], r["truncated"]) == (500, False)


async def test_get_file_not_found_suggests(db_session, repo, lined_file):
    with pytest.raises(ToolError, match="src/big.ts"):
        await call_tool(db_session, "get_file", {"repository": "zustand", "path": "src/bigg.ts"})
    with pytest.raises(ToolError, match="past the end"):
        await call_tool(db_session, "get_file", {"repository": "zustand", "path": "src/big.ts", "start_line": 900})


async def test_list_definitions_filters_and_order(db_session, repo):
    b = add_file(db_session, repo, "src/b.ts", "x")
    a = add_file(db_session, repo, "lib/a.ts", "x")
    add_entity(db_session, b, "createStore", start=9)
    add_entity(db_session, b, "Helper", "class", start=2)
    add_entity(db_session, a, "createThing", start=4, doc="doc")
    run = lambda **kw: call_tool(db_session, "list_definitions", {"repository": "zustand", **kw})  # noqa: E731

    r = await run()
    assert r["total"] == 3
    assert [(d["file_path"], d["line_start"]) for d in r["definitions"]] == [
        ("lib/a.ts", 4), ("src/b.ts", 2), ("src/b.ts", 9)]
    assert r["definitions"][0]["description"] == "doc"
    assert (await run(name="CREATE"))["total"] == 2
    assert (await run(path_prefix="src/"))["total"] == 2
    assert (await run(entity_type="class"))["definitions"][0]["entity_name"] == "Helper"
    limited = await run(limit=1)
    assert limited["total"] == 3 and len(limited["definitions"]) == 1


async def test_analyze_repository(db_session, repo):
    a = add_file(db_session, repo, "src/a.ts", "1\n2\n3")
    add_file(db_session, repo, "src/b.ts", "1")
    add_file(db_session, repo, "README.md", "x", language="markdown")
    add_entity(db_session, a, "f")
    r = await call_tool(db_session, "analyze_repository", {"repository": str(repo.id)})
    assert r["total_entities"] == 1 and r["files_by_language"]["typescript"] == 2
    assert r["top_directories"][0] == {"directory": "src", "files": 2}
    assert {"directory": "(root)", "files": 1} in r["top_directories"]
    assert r["largest_files"][0] == {"file_path": "src/a.ts", "line_count": 3}
    assert r["definitions_by_language"] == {"typescript": 1}


@pytest.fixture
def pattern_files(db_session, repo):
    add_file(db_session, repo, "src/a.py", "import os\nFoo = 1\n  foo = 2\n", language="python")
    add_file(db_session, repo, "docs/b.md", "foo bar\n", language="markdown")


async def test_find_patterns_literal_is_case_sensitive(db_session, repo, pattern_files):
    r = await call_tool(db_session, "find_patterns", {"repository": "zustand", "pattern": "foo"})
    assert [(m["file_path"], m["line"], m["text"]) for m in r["matches"]] == [
        ("docs/b.md", 1, "foo bar"), ("src/a.py", 3, "foo = 2")]
    assert r["total_matches"] == 2 and r["truncated"] is False and r["regex"] is False


async def test_find_patterns_glob_and_max(db_session, repo, pattern_files):
    r = await call_tool(db_session, "find_patterns", {"repository": "zustand", "pattern": "o", "path_glob": "src/*.py"})
    assert {m["file_path"] for m in r["matches"]} == {"src/a.py"}
    r = await call_tool(db_session, "find_patterns", {"repository": "zustand", "pattern": "o", "max_results": 2})
    assert r["total_matches"] == 2 and r["truncated"] is True


async def test_find_patterns_regex(db_session, repo, pattern_files):
    r = await call_tool(db_session, "find_patterns", {"repository": "zustand", "pattern": r"^[Ff]oo\s*=", "regex": True})
    assert [m["line"] for m in r["matches"]] == [2]


async def test_find_patterns_invalid_regex(db_session, repo):
    with pytest.raises(ToolError, match="Invalid regular expression"):
        await call_tool(db_session, "find_patterns", {"repository": "zustand", "pattern": "(", "regex": True})


async def test_find_patterns_skips_large_and_slow_files(db_session, repo, monkeypatch):
    add_file(db_session, repo, "big.txt", "a" * 1_000_001)
    r = await call_tool(db_session, "find_patterns", {"repository": "zustand", "pattern": "a+", "regex": True})
    assert r["skipped_files"] == ["big.txt"] and r["matches"] == []
    # literal search is not size-limited
    r = await call_tool(db_session, "find_patterns", {"repository": "zustand", "pattern": "aaa"})
    assert r["total_matches"] == 1

    monkeypatch.setattr(mcp_tools, "REGEX_FILE_TIMEOUT", 0.05)
    add_file(db_session, repo, "slow.txt", "a" * 40 + "!")
    r = await call_tool(db_session, "find_patterns",
                        {"repository": "zustand", "pattern": r"(a|aa)+$", "regex": True, "path_glob": "slow.txt"})
    assert r["skipped_files"] == ["slow.txt"]


async def test_find_patterns_has_a_budget_for_the_whole_call(db_session, repo, monkeypatch):
    # Each file stays under its own budget, but together they'd run files x budget
    monkeypatch.setattr(mcp_tools, "REGEX_FILE_TIMEOUT", 0.2)
    monkeypatch.setattr(mcp_tools, "REGEX_CALL_TIMEOUT", 0.3)
    for i in range(20):
        add_file(db_session, repo, f"slow{i:02}.txt", "a" * 40 + "!")
    started = time.monotonic()
    r = await call_tool(db_session, "find_patterns",
                        {"repository": "zustand", "pattern": r"(a|aa)+$", "regex": True, "path_glob": "slow*"})
    assert time.monotonic() - started < 1.5  # not 20 x 0.2s
    assert r["truncated"] is True
    assert r["skipped_count"] == 20


async def test_find_patterns_lists_at_most_50_skipped_files(db_session, repo):
    for i in range(60):
        add_file(db_session, repo, f"big{i:02}.txt", "a" * 1_000_001)
    r = await call_tool(db_session, "find_patterns", {"repository": "zustand", "pattern": "b", "regex": True})
    assert len(r["skipped_files"]) == 50 and r["skipped_count"] == 60


def test_out_of_range_ids_are_not_found(db_session, repo):
    for ref in ("9" * 5000, "9" * 19, "18446744073709551616"):
        with pytest.raises(ToolError, match="not found"):
            resolve_repository(db_session, ref)


async def test_out_of_range_resource_ids_are_not_found(db_session, repo):
    for uri in (f"codesage://repositories/{'9' * 19}/files", f"codesage://repositories/{'9' * 40}/files"):
        with pytest.raises(ToolError):
            await mcp_tools.read_resource(db_session, uri)


async def test_file_resource_is_capped(db_session, repo, monkeypatch):
    monkeypatch.setattr(mcp_tools, "MAX_RESOURCE_FILES", 3)
    for i in range(5):
        add_file(db_session, repo, f"f{i}.ts", "x")
    content = (await mcp_tools.read_resource(db_session, f"codesage://repositories/{repo.id}/files"))["content"]
    assert [f["file_path"] for f in content["files"]] == ["f0.ts", "f1.ts", "f2.ts"]
    assert content["total_files"] == 5 and content["truncated"] is True


async def test_get_file_caps_characters_as_well_as_lines(db_session, repo):
    add_file(db_session, repo, "min.js", "\n".join("x" * 5000 for _ in range(100)))
    r = await call_tool(db_session, "get_file", {"repository": "zustand", "path": "min.js"})
    assert len(r["content"]) == mcp_tools.FILE_CHARS and r["truncated"] is True


async def test_long_signatures_are_truncated(db_session, repo, algolia_index):
    f = add_file(db_session, repo, "src/a.ts", "x")
    entity = add_entity(db_session, f, "huge")
    entity.signature = "s" * 5000
    db_session.commit()
    r = await call_tool(db_session, "list_definitions", {"repository": "zustand"})
    assert all(len(d["signature"]) <= mcp_tools.SIGNATURE_CHARS for d in r["definitions"])


async def test_resources(db_session, repo):
    assert [r["uri"] for r in mcp_tools.list_resources()] == ["codesage://repositories"]
    add_file(db_session, repo, "a.ts", "1\n2")
    top = await mcp_tools.read_resource(db_session, "codesage://repositories")
    assert top["content"] == await call_tool(db_session, "list_repositories", {})
    files = await mcp_tools.read_resource(db_session, f"codesage://repositories/{repo.id}/files")
    assert files["content"]["files"] == [{"file_path": "a.ts", "language": "typescript", "line_count": 2}]


@pytest.mark.parametrize("uri", [
    "codesage://repositories/abc/files", "codesage://repositories/1/files/x",
    "codesage://repositories/1", "other://x", "codesage://repositories/999/files",
])
async def test_resource_errors(db_session, repo, uri):
    with pytest.raises(ToolError):
        await mcp_tools.read_resource(db_session, uri)


# --- permalinks on other hosts -----------------------------------------------


@pytest.mark.parametrize(
    ("url", "branch", "expected"),
    [
        (
            "https://gitlab.com/group/sub/repo",
            "main",
            "https://gitlab.com/group/sub/repo/-/blob/main/src/vanilla.ts#L5-20",
        ),
        (
            "https://gitlab.example.org/team/repo",
            None,
            "https://gitlab.example.org/team/repo/-/blob/HEAD/src/vanilla.ts#L5-20",
        ),
        (
            "https://bitbucket.org/team/repo",
            "dev",
            "https://bitbucket.org/team/repo/src/dev/src/vanilla.ts#lines-5:20",
        ),
        ("https://git.example.com/team/repo", "main", None),
    ],
)
async def test_permalinks_for_other_hosts(db_session, algolia_index, url, branch, expected):
    other = make_repo(db_session, name="o", url=url, branch=branch)
    algolia_index.search = lambda q, params: {"hits": [{**HIT, "repository_id": other.id}], "nbHits": 1}
    result = await call_tool(db_session, "search_code", {"query": "create"})
    assert result["results"][0]["url"] == expected


# --- add_repository -----------------------------------------------------------


@pytest.fixture
def started(monkeypatch):
    from app.services import git_source, repository_service

    checks = []

    async def record(url, branch=None):
        checks.append((url, branch))

    monkeypatch.setattr(git_source, "check_remote", record)
    monkeypatch.setattr(repository_service, "start_processing", lambda *a, **k: None)
    return checks


async def test_add_repository_creates_and_starts_indexing(db_session, started):
    result = await call_tool(
        db_session,
        "add_repository",
        {"url": "https://gitlab.com/group/repo/-/tree/dev", "description": "demo"},
    )

    row = db_session.query(Repository).one()
    assert result == {
        "repository_id": row.id,
        "name": "gitlab.com/group/repo",
        "status": "pending",
        "message": "Indexing started; check list_repositories for progress.",
    }
    assert (row.url, row.branch, row.description) == ("https://gitlab.com/group/repo", "dev", "demo")
    assert started == [("https://gitlab.com/group/repo", "dev")]


async def test_add_repository_names_the_existing_row_for_a_duplicate(db_session, started):
    existing = make_repo(db_session, name="gitlab.com/g/r", url="https://gitlab.com/g/r")

    with pytest.raises(ToolError, match=rf"already added as repository {existing.id}"):
        await call_tool(db_session, "add_repository", {"url": "https://gitlab.com/G/R"})
    assert started == []


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://gitlab.com/g/r", "only https"),
        ("https://127.0.0.1/g/r", "private or loopback"),
        ("https://gitlab.com/g", "missing owner"),
    ],
)
async def test_add_repository_refuses_bad_urls_as_tool_errors(db_session, started, url, message):
    with pytest.raises(ToolError, match=message):
        await call_tool(db_session, "add_repository", {"url": url})
    assert db_session.query(Repository).count() == 0


async def test_add_repository_reports_a_refused_check(db_session, monkeypatch):
    from app.services import git_source
    from app.services.github_service import RepositoryCheckError

    async def refuse(url, branch=None):
        raise RepositoryCheckError(422, "gitlab.com/g/r was not found or is private.")

    monkeypatch.setattr(git_source, "check_remote", refuse)
    with pytest.raises(ToolError, match="was not found or is private"):
        await call_tool(db_session, "add_repository", {"url": "https://gitlab.com/g/r"})
    assert db_session.query(Repository).count() == 0
