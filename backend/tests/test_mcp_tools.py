import subprocess
import sys
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
    assert row["processed_at"].startswith("2026-01-02")
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
    assert seen[-1]["filters"] == f"repository_id={repo.id}"
    assert seen[-1]["hitsPerPage"] == 10


async def test_search_all_repos_looks_up_hit_repository(db_session, repo, algolia_index):
    other = make_repo(db_session, name="o", url="https://github.com/a/o")  # no branch -> HEAD
    algolia_index.search = lambda q, params: {"hits": [{**HIT, "repository_id": other.id}], "nbHits": 1}
    result = await call_tool(db_session, "search_code", {"query": "create"})
    assert result["repository"] is None
    assert result["results"][0]["url"] == "https://github.com/a/o/blob/HEAD/src/vanilla.ts#L5-L20"


async def test_search_requires_completed(db_session, algolia_index):
    make_repo(db_session, name="busy", url=None, status="processing")
    with pytest.raises(ToolError, match="processing"):
        await call_tool(db_session, "search_code", {"query": "x", "repository": "busy"})
    assert algolia_index.searches == []


async def test_search_algolia_failure(db_session, repo, algolia_index):
    def boom(q, params):
        raise RuntimeError("down")

    algolia_index.search = boom
    with pytest.raises(ToolError, match="Search is unavailable: down"):
        await call_tool(db_session, "search_code", {"query": "x"})


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
