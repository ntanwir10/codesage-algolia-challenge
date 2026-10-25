"""MCP tool handlers.

Every handler returns measured data from the database or the Algolia index.
Interpretation is left to the calling model.
"""

import asyncio
import difflib
import fnmatch
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

import regex
import structlog
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.code_entity import CodeEntity
from app.models.code_file import CodeFile
from app.models.repository import Repository
from app.services import algolia_service
from app.services.github_service import quote_path
from app.services.repository_service import RepositoryService
from codesage_mcp import schemas

logger = structlog.get_logger()

MAX_FILE_LINES = 400
SNIPPET_CHARS = 600
MATCH_TEXT_CHARS = 300
DESCRIPTION_CHARS = 300
REGEX_FILE_BYTES = 1_000_000
REGEX_FILE_TIMEOUT = 1.0
GITHUB_PREFIX = "https://github.com/"

REPOSITORIES_URI = "codesage://repositories"
_FILES_URI = re.compile(r"codesage://repositories/([0-9]+)/files")


class ToolError(Exception):
    """A failure the caller can act on, such as an unknown repository"""


# --- repositories -----------------------------------------------------------


def _url_path(url: str | None) -> str | None:
    """owner/name from a repository URL"""
    if not url:
        return None
    path = url.strip()
    if path.lower().startswith(GITHUB_PREFIX):
        path = path[len(GITHUB_PREFIX):]
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path or None


def resolve_repository(db: Session, ref: str) -> Repository:
    """Find a repository by ID, name or owner/name, never guessing"""
    ref = ref.strip()
    repositories = db.query(Repository).order_by(Repository.id).all()

    if ref.isascii() and ref.isdigit():
        for repository in repositories:
            if repository.id == int(ref):
                return repository
    else:
        wanted = ref.lower()
        matches = [
            repository
            for repository in repositories
            if (repository.name or "").lower() == wanted
            or (_url_path(repository.url) or "").lower() == wanted
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            options = ", ".join(f"{r.name} (id {r.id})" for r in matches)
            raise ToolError(f"Repository '{ref}' is ambiguous: {options}. Use the numeric ID.")

    available = ", ".join(r.name for r in repositories) or "none indexed yet"
    raise ToolError(f"Repository '{ref}' not found. Available repositories: {available}")


def _entity_counts(db: Session) -> dict[int, int]:
    rows = db.query(CodeEntity.repository_id, func.count()).group_by(CodeEntity.repository_id).all()
    return dict(rows)


def _repository_summary(repository: Repository, entity_count: int) -> dict[str, Any]:
    return {
        "id": repository.id,
        "name": repository.name,
        "url": repository.url,
        "branch": repository.branch,
        "status": repository.status,
        "total_files": repository.total_files,
        "total_entities": entity_count,
        "error_message": repository.error_message,
        "processed_at": repository.processed_at.isoformat() if repository.processed_at else None,
    }


async def list_repositories(db: Session, args: BaseModel) -> dict:
    counts = _entity_counts(db)
    repositories = db.query(Repository).order_by(Repository.id).all()
    return {
        "repositories": [_repository_summary(r, counts.get(r.id, 0)) for r in repositories]
    }


# --- search -----------------------------------------------------------------


def _permalink(repository: Repository | None, hit: dict) -> str | None:
    path = _url_path(repository.url) if repository else None
    file_path = hit.get("file_path")
    if not path or not file_path:
        return None
    start = hit.get("line_start")
    end = hit.get("line_end") or start
    url = f"{GITHUB_PREFIX}{path}/blob/{quote_path(repository.branch or 'HEAD')}/{quote_path(file_path)}"
    if start:
        url += f"#L{start}-L{end}"
    return url


async def search_code(db: Session, args: schemas.SearchCodeArgs) -> dict:
    repository = None
    if args.repository is not None:
        repository = resolve_repository(db, args.repository)
        if repository.status != "completed":
            raise ToolError(
                f"Repository '{repository.name}' is not searchable yet (status: {repository.status})"
            )

    try:
        response = await algolia_service.AlgoliaService().search_code(
            args.query,
            repository_id=repository.id if repository else None,
            language=args.language,
            entity_type=args.entity_type,
            hits_per_page=args.limit,
            page=args.page,
        )
    except Exception as exc:
        logger.warning("MCP search failed", error=str(exc))
        raise ToolError(f"Search is unavailable: {exc}") from exc

    hits = response.get("hits", [])
    known = {repository.id: repository} if repository else {}
    missing = {h.get("repository_id") for h in hits} - set(known) - {None}
    if missing:
        for found in db.query(Repository).filter(Repository.id.in_(missing)).all():
            known[found.id] = found

    results = [
        {
            "entity_name": hit.get("entity_name"),
            "entity_type": hit.get("entity_type"),
            "file_path": hit.get("file_path"),
            "line_start": hit.get("line_start"),
            "line_end": hit.get("line_end"),
            "language": hit.get("language"),
            "signature": hit.get("signature"),
            "snippet": (hit.get("content") or "")[:SNIPPET_CHARS],
            "description": hit.get("description"),
            "url": _permalink(known.get(hit.get("repository_id")), hit),
        }
        for hit in hits
    ]
    return {
        "query": args.query,
        "repository": repository.name if repository else None,
        "total_hits": response.get("nbHits", len(results)),
        "page": response.get("page", args.page),
        "pages": response.get("nbPages", 1 if results else 0),
        "results": results,
    }


# --- files and definitions --------------------------------------------------


async def get_file(db: Session, args: schemas.GetFileArgs) -> dict:
    repository = resolve_repository(db, args.repository)
    code_file = (
        db.query(CodeFile)
        .filter(CodeFile.repository_id == repository.id, CodeFile.file_path == args.path)
        .first()
    )
    if code_file is None:
        paths = [
            p for (p,) in db.query(CodeFile.file_path).filter(CodeFile.repository_id == repository.id)
        ]
        close = difflib.get_close_matches(args.path, paths, n=10, cutoff=0.4)
        hint = f" Close paths: {', '.join(close)}" if close else ""
        raise ToolError(f"File '{args.path}' not found in {repository.name}.{hint}")

    lines = code_file.content.splitlines()
    total = len(lines)
    start = args.start_line or 1
    requested_end = args.end_line if args.end_line is not None else total
    if total and start > total:
        raise ToolError(f"start_line {start} is past the end of the file ({total} lines)")
    if requested_end < start:
        raise ToolError("end_line must not be before start_line")

    end = min(requested_end, total, start + MAX_FILE_LINES - 1)
    width = max(4, len(str(end)))
    content = "\n".join(
        f"{number:>{width}}| {line}" for number, line in enumerate(lines[start - 1 : end], start)
    )
    return {
        "repository": repository.name,
        "path": code_file.file_path,
        "language": code_file.language,
        "total_lines": total,
        "start_line": start,
        "end_line": end,
        "truncated": end < min(requested_end, total),
        "content": content,
    }


async def list_definitions(db: Session, args: schemas.ListDefinitionsArgs) -> dict:
    repository = resolve_repository(db, args.repository)
    query = (
        db.query(CodeEntity, CodeFile.file_path)
        .join(CodeFile, CodeEntity.file_id == CodeFile.id)
        .filter(CodeEntity.repository_id == repository.id)
    )
    if args.path_prefix:
        query = query.filter(CodeFile.file_path.startswith(args.path_prefix, autoescape=True))
    if args.entity_type:
        query = query.filter(CodeEntity.entity_type == args.entity_type)
    if args.name:
        query = query.filter(
            func.lower(CodeEntity.entity_name).contains(args.name.lower(), autoescape=True)
        )

    total = query.count()
    rows = (
        query.order_by(CodeFile.file_path, CodeEntity.start_line, CodeEntity.id)
        .limit(args.limit)
        .all()
    )
    return {
        "repository": repository.name,
        "total": total,
        "definitions": [
            {
                "entity_type": entity.entity_type,
                "entity_name": entity.entity_name,
                "file_path": file_path,
                "line_start": entity.start_line,
                "line_end": entity.end_line,
                "signature": entity.signature,
                "description": (entity.docstring or "")[:DESCRIPTION_CHARS] or None,
            }
            for entity, file_path in rows
        ],
    }


# --- analysis and patterns --------------------------------------------------


async def analyze_repository(db: Session, args: schemas.AnalyzeRepositoryArgs) -> dict:
    repository = resolve_repository(db, args.repository)
    stats = await RepositoryService(db).get_repository_statistics(repository)

    files = (
        db.query(CodeFile.file_path, CodeFile.line_count)
        .filter(CodeFile.repository_id == repository.id)
        .all()
    )
    directories = Counter(path.split("/", 1)[0] if "/" in path else "(root)" for path, _ in files)
    largest = sorted(files, key=lambda row: row[1] or 0, reverse=True)[:10]
    by_language = (
        db.query(CodeFile.language, func.count())
        .select_from(CodeEntity)
        .join(CodeFile, CodeEntity.file_id == CodeFile.id)
        .filter(CodeEntity.repository_id == repository.id)
        .group_by(CodeFile.language)
        .all()
    )
    return {
        "repository": repository.name,
        **stats,
        "top_directories": [
            {"directory": name, "files": count} for name, count in directories.most_common(10)
        ],
        "largest_files": [{"file_path": path, "line_count": lines} for path, lines in largest],
        "definitions_by_language": {language or "unknown": count for language, count in by_language},
    }


def _scan(
    files: list[tuple[str, str]], pattern: str, use_regex: bool, max_results: int
) -> tuple[list[dict], bool, list[str]]:
    """Match lines in plain data, so it can run off the event loop"""
    compiled = regex.compile(pattern) if use_regex else None
    matches: list[dict] = []
    skipped: list[str] = []

    for file_path, content in files:
        if compiled is not None:
            if len(content) > REGEX_FILE_BYTES:
                skipped.append(file_path)
                continue
            deadline = time.monotonic() + REGEX_FILE_TIMEOUT
        for number, line in enumerate(content.splitlines(), 1):
            if compiled is None:
                hit = line.find(pattern) != -1
            else:
                remaining = deadline - time.monotonic()
                try:
                    if remaining <= 0:
                        raise TimeoutError
                    hit = compiled.search(line, timeout=remaining) is not None
                except TimeoutError:
                    skipped.append(file_path)
                    break
            if not hit:
                continue
            if len(matches) == max_results:
                return matches, True, skipped
            matches.append(
                {"file_path": file_path, "line": number, "text": line.strip()[:MATCH_TEXT_CHARS]}
            )
    return matches, False, skipped


async def find_patterns(db: Session, args: schemas.FindPatternsArgs) -> dict:
    repository = resolve_repository(db, args.repository)
    if args.regex:
        try:
            regex.compile(args.pattern)
        except regex.error as exc:
            raise ToolError(f"Invalid regular expression: {exc}") from exc

    def load_and_scan():
        # Loads every file's content, so it runs off the event loop along with the scan
        files = (
            db.query(CodeFile.file_path, CodeFile.content)
            .filter(CodeFile.repository_id == repository.id)
            .order_by(CodeFile.file_path)
            .all()
        )
        if args.path_glob:
            files = [row for row in files if fnmatch.fnmatchcase(row[0], args.path_glob)]
        return _scan([tuple(row) for row in files], args.pattern, args.regex, args.max_results)

    matches, truncated, skipped = await asyncio.to_thread(load_and_scan)
    result = {
        "repository": repository.name,
        "pattern": args.pattern,
        "regex": args.regex,
        "total_matches": len(matches),
        "truncated": truncated,
        "matches": matches,
    }
    if skipped:
        result["skipped_files"] = skipped
    return result


# --- dispatch ---------------------------------------------------------------

Handler = Callable[[Session, Any], Awaitable[dict]]

HANDLERS: dict[str, Handler] = {
    "list_repositories": list_repositories,
    "search_code": search_code,
    "get_file": get_file,
    "list_definitions": list_definitions,
    "analyze_repository": analyze_repository,
    "find_patterns": find_patterns,
}


async def call_tool(db: Session, name: str, arguments: dict) -> dict:
    """Run a tool. KeyError for an unknown tool, ValidationError for bad arguments."""
    spec = schemas.TOOLS[name]
    return await HANDLERS[name](db, spec.args_model.model_validate(arguments or {}))


# --- resources --------------------------------------------------------------


def list_resources() -> list[dict]:
    return [
        {
            "uri": REPOSITORIES_URI,
            "name": "Repositories",
            "description": "Indexed repositories and their status",
            "mimeType": "application/json",
        }
    ]


async def read_resource(db: Session, uri: str) -> dict:
    if uri == REPOSITORIES_URI:
        content = await list_repositories(db, schemas.ListRepositoriesArgs())
    else:
        match = _FILES_URI.fullmatch(uri)
        if match is None:
            raise ToolError(f"Unknown resource '{uri}'")
        repository = db.get(Repository, int(match.group(1)))
        if repository is None:
            raise ToolError(f"Repository {match.group(1)} not found")
        rows = (
            db.query(CodeFile.file_path, CodeFile.language, CodeFile.line_count)
            .filter(CodeFile.repository_id == repository.id)
            .order_by(CodeFile.file_path)
            .all()
        )
        content = {
            "repository": repository.name,
            "files": [
                {"file_path": path, "language": language, "line_count": lines}
                for path, language, lines in rows
            ],
        }
    return {"uri": uri, "mimeType": "application/json", "content": content}
