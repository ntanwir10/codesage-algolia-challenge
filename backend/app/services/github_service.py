import asyncio
import fnmatch
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote as urlquote
from urllib.parse import unquote, urlsplit

import aiohttp
import structlog

logger = structlog.get_logger()

# Performance constants
MAX_CONCURRENT_REQUESTS = 5  # GitHub API rate limiting
REQUEST_DELAY = 0.1  # Delay between requests to avoid rate limits
MAX_RETRIES = 3  # Retry timeouts and 5xx responses
RETRY_BACKOFF_BASE = 1.0  # Seconds; attempt n waits base * 2**n
MAX_RATE_LIMIT_WAIT = 60  # Longest we will sleep for a rate-limit reset

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
    if not _NAME_RE.match(owner) or not repo or not _NAME_RE.match(repo) or repo in (".", ".."):
        raise ValueError(f"Invalid GitHub URL (bad owner or repository name): {url}")
    if branch is not None and (not branch or ".." in branch.split("/") or "\x00" in branch):
        raise ValueError(f"Invalid GitHub URL (bad branch): {url}")
    return owner, repo, branch


def _quote_path(path: str) -> str:
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

    def is_code_file(self) -> bool:
        """Check if this is a code file we should process"""
        code_extensions = {
            "py",
            "js",
            "ts",
            "jsx",
            "tsx",
            "java",
            "go",
            "rs",
            "cpp",
            "c",
            "cs",
            "php",
            "rb",
            "html",
            "css",
            "scss",
            "sql",
            "json",
            "yaml",
            "yml",
            "xml",
            "md",
        }
        if not self.filename:
            return False

        ext = self.filename.lower().split(".")[-1] if "." in self.filename else ""
        return ext in code_extensions


class GitHubService:
    """
    GitHub API client for repository analysis with performance optimizations.
    Based on architecture.md: External Integration → GitHub API
    """

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"
        self.raw_base_url = "https://raw.githubusercontent.com"
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        # Set processing limits
        self.max_files = 1000  # Maximum number of files to process
        self.max_file_size = 1024 * 1024  # 1MB file size limit

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
            logger.error("Failed to get repository files", repo_url=repo_url, error=str(e))
            raise

    def _select_candidates(self, entries: list[tuple[str, int]]) -> list[tuple[str, int]]:
        """Apply deny-list, extension and size filters, then sort and cap"""
        selected = []
        for path, size in entries:
            if is_denied_path(path):
                continue
            filename = path.split("/")[-1]
            probe = GitHubFile(path, "", size, self._detect_language(filename), filename)
            if not probe.is_code_file() or size >= self.max_file_size:
                continue
            selected.append((path, size))
        selected.sort()
        if len(selected) > self.max_files:
            logger.warning(
                "Repository has too many files, limiting to max",
                total_files=len(selected),
                max_files=self.max_files,
            )
            selected = selected[: self.max_files]
        return selected

    async def _list_entries(
        self, session: aiohttp.ClientSession, owner: str, repo: str, branch: str
    ) -> list[tuple[str, int]]:
        """List (path, size) for every file, via one git trees call when possible"""
        tree = await self._make_request_with_retries(
            session,
            f"{self.base_url}/repos/{owner}/{repo}/git/trees/{urlquote(branch, safe='')}",
            owner,
            repo,
            params={"recursive": "1"},
        )
        if tree.get("truncated"):
            logger.warning("Git tree truncated, walking contents API", owner=owner, repo=repo)
            entries: list[tuple[str, int]] = []
            await self._walk_contents(session, owner, repo, branch, "", entries)
            return entries
        return [
            (item["path"], item.get("size", 0))
            for item in tree.get("tree", [])
            if item.get("type") == "blob" and item.get("mode") != "120000"
        ]

    async def _walk_contents(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        branch: str,
        path: str,
        entries: list[tuple[str, int]],
    ) -> None:
        """Fallback listing: one contents request per directory, denied dirs pruned"""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{_quote_path(path) if path else ''}"
        contents = await self._make_request_with_retries(
            session, url, owner, repo, path, params={"ref": branch}
        )
        if not isinstance(contents, list):
            return
        for item in contents:
            if item["type"] == "file":
                entries.append((item["path"], item.get("size", 0)))
            elif item["type"] == "dir" and not is_denied_path(item["path"] + "/x"):
                await self._walk_contents(session, owner, repo, branch, item["path"], entries)

    async def _download_all(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        branch: str,
        candidates: list[tuple[str, int]],
    ) -> list[GitHubFile]:
        """Download candidates concurrently; failed, empty and binary files are skipped"""

        async def fetch(path: str, size: int) -> GitHubFile | None:
            url = (
                f"{self.raw_base_url}/{urlquote(owner, safe='')}/{urlquote(repo, safe='')}"
                f"/{_quote_path(branch)}/{_quote_path(path)}"
            )
            async with self._semaphore:
                raw = await self._download_file_content(session, url)
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

        results = await asyncio.gather(*(fetch(p, s) for p, s in candidates))
        return [f for f in results if f is not None]

    def _detect_language(self, filename: str) -> str:
        """Detect programming language from file extension"""
        if not filename:
            return "text"

        ext = filename.lower().split(".")[-1] if "." in filename else ""
        language_map = {
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
        return language_map.get(ext, "text")

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
        self, session: aiohttp.ClientSession, download_url: str
    ) -> bytes:
        """Download individual file content as bytes; b"" (skipped) on failure"""
        try:
            async with session.get(download_url) as response:
                if response.status == 200:
                    return await response.read()
                logger.warning("Failed to download file", url=download_url, status=response.status)
                return b""
        except Exception as e:
            logger.warning("Failed to download file", url=download_url, error=str(e))
            return b""
