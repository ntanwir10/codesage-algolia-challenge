import asyncio
import fnmatch
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote as urlquote
from urllib.parse import unquote, urlsplit

import aiohttp
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()

# Performance constants
MAX_CONCURRENT_REQUESTS = 5  # GitHub API rate limiting
MAX_RETRIES = 3  # Retry timeouts and 5xx responses
RETRY_BACKOFF_BASE = 1.0  # Seconds; attempt n waits base * 2**n
MAX_RATE_LIMIT_WAIT = 60  # Longest we will sleep for a rate-limit reset
# Directories the contents-API fallback lists (one request each) before it stops. It only runs
# for trees too big for one git trees call, and 5000 requests is a token's whole hourly quota
MAX_WALK_REQUESTS = 300

# Directory names (matched as path segments) that hold generated or third-party code
DENIED_DIRS = frozenset(
    {
        "node_modules",
        "dist",
        "build",
        "vendor",
        "third_party",
        ".git",
        "__pycache__",
        ".next",
        "coverage",
    }
)
# File name patterns (case-insensitive) that are generated, minified or lockfiles
DENIED_FILE_PATTERNS = (
    "*.min.js",
    "*.min.css",
    "*.bundle.js",
    "*.map",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "cargo.lock",
)

# File extensions we index, mapped to their language
EXT_TO_LANGUAGE: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "jsx": "javascript",
    "tsx": "typescript",
    "java": "java",
    "go": "go",
    "rs": "rust",
    "cpp": "cpp",
    "c": "c",
    "cs": "csharp",
    "php": "php",
    "rb": "ruby",
    "html": "html",
    "css": "css",
    "scss": "scss",
    "sql": "sql",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "xml": "xml",
    "md": "markdown",
}

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def is_denied_path(path: str) -> bool:
    """True if the path sits under a denied directory or is a denied file"""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return True
    if any(part in DENIED_DIRS for part in parts[:-1]):
        return True
    name = parts[-1].lower()
    return any(fnmatch.fnmatchcase(name, pat) for pat in DENIED_FILE_PATTERNS)


def is_valid_branch(branch: str) -> bool:
    """False for names that could step outside the repository in an API path"""
    return bool(branch) and ".." not in branch.split("/") and "\x00" not in branch


def parse_github_url(url: str) -> tuple[str, str, str | None]:
    """Parse a GitHub URL into (owner, repo, branch_or_None).

    Accepts https/http (optionally www.), a trailing slash, a trailing .git,
    /tree/<branch> and git@github.com:owner/repo.git. Anything else raises
    ValueError.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Invalid GitHub URL: empty")
    raw = url.strip()
    branch: str | None = None

    ssh = re.match(r"^git@github\.com:([^/?#]+)/([^/?#]+?)/?$", raw)
    if ssh:
        owner, repo = ssh.groups()
    else:
        try:
            parts = urlsplit(raw)
            hostname = parts.hostname
            port = parts.port
        except ValueError as e:
            raise ValueError(f"Invalid GitHub URL: {url}") from e
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"Invalid GitHub URL (unsupported scheme): {url}")
        if hostname not in ("github.com", "www.github.com"):
            raise ValueError(f"Invalid GitHub URL (host must be github.com): {url}")
        if parts.username or parts.password or port:
            raise ValueError(f"Invalid GitHub URL (unexpected credentials or port): {url}")
        if parts.query or parts.fragment:
            raise ValueError(f"Invalid GitHub URL (query or fragment not allowed): {url}")
        segments = [s for s in parts.path.split("/") if s]
        if len(segments) < 2:
            raise ValueError(f"Invalid GitHub URL (missing owner or repository): {url}")
        owner, repo = segments[0], segments[1]
        rest = segments[2:]
        if rest:
            if rest[0] != "tree" or len(rest) < 2:
                raise ValueError(f"Invalid GitHub URL (unsupported path): {url}")
            branch = "/".join(unquote(s) for s in rest[1:])

    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    # "." and ".." as owner would turn api.github.com/users/<owner> into api.github.com/user
    if not _NAME_RE.match(owner) or owner in (".", "..") or not repo or not _NAME_RE.match(repo) or repo in (".", ".."):
        raise ValueError(f"Invalid GitHub URL (bad owner or repository name): {url}")
    if branch is not None and not is_valid_branch(branch):
        raise ValueError(f"Invalid GitHub URL (bad branch): {url}")
    return owner, repo, branch


def quote_path(path: str) -> str:
    """Percent-encode each segment of a slash-separated path"""
    return "/".join(urlquote(seg, safe="") for seg in path.split("/"))


class GitHubAPIError(Exception):
    """GitHub returned an error status while listing repository contents"""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class GitHubFile:
    """Represents a file from GitHub repository"""

    path: str
    content: str
    size: int
    language: str
    filename: str


class GitHubService:
    """
    GitHub API client for repository analysis with performance optimizations.
    Based on architecture.md: External Integration → GitHub API
    """

    def __init__(self):
        self.token = get_settings().github_token
        self.base_url = "https://api.github.com"
        self.raw_base_url = "https://raw.githubusercontent.com"
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        # Set processing limits
        self.max_files = 1000  # Maximum number of files to process
        self.max_file_size = 1024 * 1024  # 1MB file size limit
        self.max_total_bytes = 100 * 1024 * 1024  # a run holds every file in memory at once
        self.skipped_files = 0  # Code files the last listing dropped over max_files / max_total_bytes
        self.listing_truncated = False  # The last listing stopped at MAX_WALK_REQUESTS directories
        self._walk_requests = 0

        if not self.token:
            logger.warning("GitHub token not found. Rate limits will be lower.")

    def _new_session(self) -> aiohttp.ClientSession:
        """One session per get_repository_files call"""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "CodeSage-MCP-Server/1.0",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        return aiohttp.ClientSession(headers=headers, timeout=timeout)

    async def _make_request_with_retries(
        self,
        session: aiohttp.ClientSession,
        url: str,
        owner: str,
        repo: str,
        path: str = "",
        params: dict[str, str] | None = None,
    ) -> Any:
        """GET a GitHub API URL and return its JSON body.

        Timeouts, connection errors and 5xx are retried with backoff up to
        MAX_RETRIES. A rate-limited 403/429 waits for X-RateLimit-Reset (at
        most MAX_RATE_LIMIT_WAIT seconds) and retries once. Everything else
        raises GitHubAPIError; this never returns an empty result on failure.
        """
        rate_limit_retried = False
        attempt = 0
        while True:
            failure: GitHubAPIError
            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    status = response.status
                    headers = response.headers
                    body = (await response.text())[:500]
                logger.warning("GitHub API non-200", url=url, status=status, response_text=body)
                failure = GitHubAPIError(
                    status, self._describe_api_error(status, headers, owner, repo, path)
                )
                if (
                    status in (403, 429)
                    and headers.get("X-RateLimit-Remaining") == "0"
                    and not rate_limit_retried
                ):
                    try:
                        wait = int(headers.get("X-RateLimit-Reset", "")) - time.time()
                    except ValueError:
                        raise failure from None
                    rate_limit_retried = True
                    wait = max(0.0, min(wait + 1, MAX_RATE_LIMIT_WAIT))
                    logger.warning("Rate limit hit, waiting", seconds=wait)
                    await asyncio.sleep(wait)
                    continue
                if status < 500:
                    raise failure
            except TimeoutError:
                target = f"{owner}/{repo}/{path}" if path else f"{owner}/{repo}"
                failure = GitHubAPIError(
                    504, f"GitHub API request timed out (504) while reading {target}"
                )
            except aiohttp.ClientError as e:
                target = f"{owner}/{repo}/{path}" if path else f"{owner}/{repo}"
                failure = GitHubAPIError(
                    503, f"GitHub API connection failed (503) while reading {target}: {e}"
                )

            attempt += 1
            if attempt >= MAX_RETRIES:
                raise failure
            delay = RETRY_BACKOFF_BASE * 2 ** (attempt - 1)
            logger.warning("Retrying GitHub request", url=url, attempt=attempt, delay=delay)
            await asyncio.sleep(delay)

    async def get_repository_files(
        self, repo_url: str, branch: str | None = None
    ) -> list[GitHubFile]:
        """
        Download files from GitHub repository for processing.
        Based on our architecture: GitHub API → File Extraction → Algolia Indexing

        Raises GitHubAPIError for API failures and ValueError for a bad URL.
        """
        try:
            logger.info("Starting get_repository_files", repo_url=repo_url)
            owner, repo, url_branch = parse_github_url(repo_url)
            branch = branch or url_branch

            session = self._new_session()
            try:
                if not branch:
                    info = await self._make_request_with_retries(
                        session, f"{self.base_url}/repos/{owner}/{repo}", owner, repo
                    )
                    branch = info.get("default_branch")
                    if not branch:
                        raise GitHubAPIError(
                            502,
                            f"GitHub did not report a default branch for {owner}/{repo}",
                        )
                logger.info("Fetching repository files", owner=owner, repo=repo, branch=branch)

                self._walk_requests, self.listing_truncated = 0, False
                entries = await self._list_entries(session, owner, repo, branch)
                candidates = self._select_candidates(entries)
                files = await self._download_all(session, owner, repo, branch, candidates)
            finally:
                await session.close()

            logger.info(
                "Repository files retrieved",
                listed=len(entries),
                selected=len(candidates),
                downloaded=len(files),
            )
            return files

        except Exception as e:
            # The caller records the failure on the repository; just trace it here
            logger.debug("Failed to get repository files", repo_url=repo_url, error=str(e))
            raise

    def _select_candidates(self, entries: list[tuple[str, int]]) -> list[tuple[str, int]]:
        """Apply deny-list, extension and size filters, then sort and cap"""
        selected = []
        for path, size in entries:
            if is_denied_path(path):
                continue
            filename = path.split("/")[-1]
            # Unknown extensions map to "text", which we don't index
            if self._detect_language(filename) == "text" or size >= self.max_file_size:
                continue
            selected.append((path, size))
        selected.sort()
        kept, total_bytes = 0, 0
        for _, size in selected:
            if kept == self.max_files or total_bytes + size > self.max_total_bytes:
                break
            kept += 1
            total_bytes += size
        self.skipped_files = len(selected) - kept
        if self.skipped_files:
            logger.warning(
                "Repository is over the file or size limit, indexing the first files only",
                total_files=len(selected),
                kept_files=kept,
                max_files=self.max_files,
                max_total_bytes=self.max_total_bytes,
            )
        return selected[:kept]

    async def _list_entries(
        self, session: aiohttp.ClientSession, owner: str, repo: str, branch: str
    ) -> list[tuple[str, int]]:
        """List (path, size) for every file, via one git trees call when possible"""
        try:
            tree = await self._make_request_with_retries(
                session,
                f"{self.base_url}/repos/{owner}/{repo}/git/trees/{urlquote(branch, safe='')}",
                owner,
                repo,
                params={"recursive": "1"},
            )
        except GitHubAPIError as e:
            if e.status != 404:
                raise
            # The repository may exist while the branch doesn't; say which. A
            # missing repository raises its own 404 from this lookup.
            await self._make_request_with_retries(
                session, f"{self.base_url}/repos/{owner}/{repo}", owner, repo
            )
            raise GitHubAPIError(404, f"Branch '{branch}' not found in {owner}/{repo}") from e
        listed = [
            (item["path"], item.get("size", 0))
            for item in tree.get("tree", [])
            if item.get("type") == "blob" and item.get("mode") != "120000"
        ]
        if not tree.get("truncated"):
            return listed
        logger.warning("Git tree truncated, walking contents API", owner=owner, repo=repo)
        walked: list[tuple[str, int]] = []
        await self._walk_contents(session, owner, repo, branch, walked)
        # The truncated tree still lists its first entries; keep them, so a walk cut short
        # by its request cap never indexes fewer files than the tree alone would have
        return list({**dict(listed), **dict(walked)}.items())

    async def _walk_contents(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        branch: str,
        entries: list[tuple[str, int]],
    ) -> None:
        """Fallback listing: one contents request per directory, denied dirs pruned.

        Breadth-first, so when MAX_WALK_REQUESTS runs out it is the deepest directories
        that go unlisted, not whole top-level ones after a deep one early in the order.
        """
        pending = deque([""])
        while pending:
            if self._walk_requests >= MAX_WALK_REQUESTS:
                logger.warning("Contents walk hit its request cap", owner=owner, repo=repo)
                self.listing_truncated = True
                return
            self._walk_requests += 1
            path = pending.popleft()
            url = f"{self.base_url}/repos/{owner}/{repo}/contents/{quote_path(path) if path else ''}"
            contents = await self._make_request_with_retries(
                session, url, owner, repo, path, params={"ref": branch}
            )
            if not isinstance(contents, list):
                continue
            for item in contents:
                if item["type"] == "file":
                    entries.append((item["path"], item.get("size", 0)))
                elif item["type"] == "dir" and not is_denied_path(item["path"] + "/x"):
                    pending.append(item["path"])

    async def _download_all(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        branch: str,
        candidates: list[tuple[str, int]],
    ) -> list[GitHubFile]:
        """Download candidates concurrently; empty and binary files are skipped, failures raise"""

        async def fetch(path: str, size: int) -> GitHubFile | None:
            url = (
                f"{self.raw_base_url}/{urlquote(owner, safe='')}/{urlquote(repo, safe='')}"
                f"/{quote_path(branch)}/{quote_path(path)}"
            )
            async with self._semaphore:
                raw = await self._download_file_content(session, url, path)
            content = self._decode_content(raw)
            if content is None:
                logger.debug("Skipped empty or binary file", file_path=path)
                return None
            filename = path.split("/")[-1]
            return GitHubFile(
                path=path,
                content=content,
                size=size,
                language=self._detect_language(filename),
                filename=filename,
            )

        tasks = [asyncio.create_task(fetch(p, s)) for p, s in candidates]
        try:
            results = await asyncio.gather(*tasks)
        except BaseException:
            # One failed download fails the run; stop the rest before the session closes
            for task in tasks:
                task.cancel()
            raise
        return [f for f in results if f is not None]

    def _detect_language(self, filename: str) -> str:
        """Detect programming language from file extension"""
        if not filename:
            return "text"

        ext = filename.lower().split(".")[-1] if "." in filename else ""
        return EXT_TO_LANGUAGE.get(ext, "text")

    @staticmethod
    def _describe_api_error(status: int, headers, owner: str, repo: str, path: str) -> str:
        """Explain a failed contents request in terms a user can act on"""
        target = f"{owner}/{repo}/{path}" if path else f"{owner}/{repo}"
        if status == 401:
            return f"GitHub rejected the token (401) for {target}; check GITHUB_TOKEN"
        if status in (403, 429) and headers.get("X-RateLimit-Remaining") == "0":
            return f"GitHub API rate limit exceeded ({status}) while reading {target}"
        if status == 403:
            return f"GitHub denied access (403) to {target}"
        if status == 404:
            return f"GitHub repository or path not found (404): {target}; it may be private or misspelled"
        return f"GitHub API error {status} while reading {target}"

    @staticmethod
    def _decode_content(raw: bytes) -> str | None:
        """Decode downloaded bytes to text, or None for empty and binary files"""
        if not raw or b"\x00" in raw:
            return None
        return raw.decode("utf-8-sig", errors="replace")

    async def _download_file_content(
        self, session: aiohttp.ClientSession, download_url: str, path: str
    ) -> bytes:
        """Download one file's bytes, retrying timeouts, 429 and 5xx up to MAX_RETRIES.

        Raises GitHubAPIError when the file can't be fetched: skipping it would let
        a reprocess replace a complete index with a partial one.
        """
        attempt = 0
        while True:
            failure: GitHubAPIError
            try:
                async with session.get(download_url) as response:
                    if response.status == 200:
                        return await response.read()
                    status = response.status
                logger.warning("Failed to download file", url=download_url, status=status)
                failure = GitHubAPIError(status, f"GitHub download failed ({status}) for {path}")
                if status < 500 and status != 429:
                    raise failure
            except TimeoutError:
                failure = GitHubAPIError(504, f"GitHub download timed out (504) for {path}")
            except aiohttp.ClientError as e:
                failure = GitHubAPIError(503, f"GitHub download failed (503) for {path}: {e}")

            attempt += 1
            if attempt >= MAX_RETRIES:
                raise failure
            await asyncio.sleep(RETRY_BACKOFF_BASE * 2 ** (attempt - 1))
