import asyncio
import fnmatch
import ipaddress
import math
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
from app.services.code_parser import LANGUAGE_SPECS

logger = structlog.get_logger()

# Performance constants
MAX_CONCURRENT_REQUESTS = 5  # GitHub API rate limiting
MAX_RETRIES = 3  # Attempts in total, so 2 retries
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
    "tf": "terraform",
    "tfvars": "terraform",
    "hcl": "hcl",
}

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# Directory names and file name shapes that hold tests rather than the code under test
_TEST_DIRS = frozenset({"test", "tests", "__tests__", "spec", "specs", "__mocks__", "e2e", "testing"})
_TEST_FILE_RE = re.compile(r"^test_.*\.py$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$|Tests?\.(java|cs|kt)$|_spec\.rb$")

# Languages the parser turns into entities; selection fills the file budget with these first
_SOURCE_LANGUAGES = frozenset({"python", "terraform", "hcl", *LANGUAGE_SPECS})


def is_test_path(path: str) -> bool:
    """True for files under a test directory or named like a test"""
    parts = path.split("/")
    return any(part.lower() in _TEST_DIRS for part in parts[:-1]) or bool(_TEST_FILE_RE.search(parts[-1]))


def is_denied_path(path: str) -> bool:
    """True if the path sits under a denied directory or is a denied file"""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return True
    if any(part in DENIED_DIRS for part in parts[:-1]):
        return True
    name = parts[-1].lower()
    return any(fnmatch.fnmatchcase(name, pat) for pat in DENIED_FILE_PATTERNS)


# What `git check-ref-format` forbids in a branch name: control characters, space and ~^:?*[\,
# "..", "@{", "//", a part starting with "." or ending in ".lock", and a leading or trailing "/" or "."
_BAD_REF = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]|\.\.|@\{|//|(^|/)\.|\.lock(/|$)|^/|/$|\.$|^@$")


def is_valid_branch(branch: str) -> bool:
    """git's branch-name rules, so a bad name gets 'invalid' instead of 'does not exist'. They also
    keep a name from stepping outside the repository in an API path"""
    return (
        bool(branch)
        and not branch.startswith("-")  # would read as an option to git
        and not _BAD_REF.search(branch)
    )


def parse_repository_url(url: str) -> tuple[str, str, str | None]:
    """Parse an https git URL on any host into (host, path, branch_or_None).

    The path keeps nested groups (GitLab's group/sub/repo) without a trailing .git or slash.
    The branch comes from /tree/<b> (GitHub), /-/tree/<b> (GitLab) or /src/<b> (Bitbucket).
    Raises ValueError for anything else, including non-https schemes, credentials, ports and
    hosts that are localhost or a non-public IP literal.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Invalid repository URL: empty")
    raw = url.strip()
    try:
        parts = urlsplit(raw)
        hostname = parts.hostname
        port = parts.port
    except ValueError as e:
        raise ValueError(f"Invalid repository URL: {url}") from e
    if parts.scheme != "https":
        raise ValueError(f"Invalid repository URL (only https is supported): {url}")
    if not hostname:
        raise ValueError(f"Invalid repository URL (missing host): {url}")
    if parts.username is not None or parts.password is not None:
        raise ValueError(f"Invalid repository URL (credentials are not allowed): {url}")
    if port:
        raise ValueError(f"Invalid repository URL (ports are not supported): {url}")
    if parts.query or parts.fragment:
        raise ValueError(f"Invalid repository URL (query or fragment not allowed): {url}")
    host = hostname.removeprefix("www.") if hostname == "www.github.com" else hostname
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError(f"Invalid repository URL (localhost is not allowed): {url}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise ValueError(f"Invalid repository URL (private or loopback address): {url}")

    segments = [unquote(s) for s in parts.path.split("/") if s]
    branch: str | None = None
    marker = None  # index where the branch part starts
    if host == "github.com":
        if len(segments) > 2:
            if segments[2] != "tree" or len(segments) < 4:
                raise ValueError(f"Invalid repository URL (unsupported path): {url}")
            marker = 2
    elif "-" in segments:
        i = segments.index("-")
        if segments[i + 1 : i + 2] != ["tree"] or len(segments) < i + 3:
            raise ValueError(f"Invalid repository URL (unsupported path): {url}")
        marker = i
    elif host == "bitbucket.org" and len(segments) > 2:
        if segments[2] != "src" or len(segments) < 4:
            raise ValueError(f"Invalid repository URL (unsupported path): {url}")
        marker = 2
    if marker is not None:
        skip = 1 if segments[marker] == "-" else 0
        branch = "/".join(segments[marker + 1 + skip :])
        segments = segments[:marker]

    if segments and segments[-1].endswith(".git"):
        segments[-1] = segments[-1][: -len(".git")]
    if len(segments) < 2:
        raise ValueError(f"Invalid repository URL (missing owner or repository): {url}")
    # "." and ".." as owner would turn api.github.com/users/<owner> into api.github.com/user
    if any(not _NAME_RE.match(seg) or seg in (".", "..") for seg in segments):
        raise ValueError(f"Invalid repository URL (bad owner or repository name): {url}")
    if branch is not None and not is_valid_branch(branch):
        raise ValueError(f"Invalid repository URL (bad branch): {url}")
    return host, "/".join(segments), branch


def to_https_url(url: str) -> str:
    """Rewrite http:// and git@<host>:<path> forms to https://; anything else is returned stripped"""
    raw = url.strip()
    ssh = re.match(r"^git@([^:/\s]+):(.+)$", raw)
    if ssh:
        return f"https://{ssh.group(1)}/{ssh.group(2)}"
    if raw.lower().startswith("http://"):
        return "https://" + raw[len("http://") :]
    return raw


def parse_github_url(url: str) -> tuple[str, str, str | None]:
    """Parse a GitHub URL into (owner, repo, branch_or_None).

    Accepts https/http (optionally www.), a trailing slash, a trailing .git,
    /tree/<branch> and git@github.com:owner/repo.git. Anything else raises
    ValueError.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Invalid GitHub URL: empty")
    try:
        host, path, branch = parse_repository_url(to_https_url(url))
    except ValueError as e:
        raise ValueError(str(e).replace("Invalid repository URL", "Invalid GitHub URL", 1)) from e
    if host != "github.com":
        raise ValueError(f"Invalid GitHub URL (host must be github.com): {url}")
    owner, repo = path.split("/")
    return owner, repo, branch


def quote_path(path: str) -> str:
    """Percent-encode each segment of a slash-separated path"""
    return "/".join(urlquote(seg, safe="") for seg in path.split("/"))


class GitHubAPIError(Exception):
    """GitHub returned an error status while listing repository contents"""

    user_facing = True  # the message is written for the person who added the repository

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class RepositoryCheckError(Exception):
    """The pre-flight check refused a repository; the endpoint returns it as an HTTP error"""

    def __init__(self, status_code: int, detail: str, headers: dict[str, str] | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


def rate_limit_wait(headers) -> float | None:
    """Seconds until a rate-limited 403/429 clears, or None when headers say nothing"""
    try:
        if "Retry-After" in headers:
            return max(1.0, float(headers["Retry-After"]))
        if headers.get("X-RateLimit-Remaining") == "0":
            return max(1.0, int(headers["X-RateLimit-Reset"]) - time.time())
    except (KeyError, ValueError):
        pass
    return None


def is_rate_limited(status: int, headers) -> bool:
    return status in (403, 429) and (
        headers.get("X-RateLimit-Remaining") == "0" or "Retry-After" in headers
    )


def _about_minutes(seconds: float) -> str:
    minutes = max(1, math.ceil(seconds / 60))
    return f"about {minutes} minute{'' if minutes == 1 else 's'}"


@dataclass
class GitHubFile:
    """Represents a file from GitHub repository"""

    path: str
    content: str
    size: int
    language: str
    filename: str


class FileSelector:
    """Which repository files get indexed: the limits and filters shared by every git source"""

    def __init__(self):
        self.max_files = 1000  # Maximum number of files to process
        self.max_file_size = 1024 * 1024  # 1MB file size limit
        self.max_total_bytes = 100 * 1024 * 1024  # a run holds every file in memory at once
        self.skipped_files = 0  # Code files the last listing dropped over max_files / max_total_bytes
        self.listing_truncated = False  # The last listing stopped at MAX_WALK_REQUESTS directories
        self.commit_sha: str | None = None  # The commit the last listing read

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
        # Source before tests, docs and data, so a capped listing keeps src/ over docs/ or examples/
        selected.sort(key=lambda entry: (self._priority(entry[0]), entry[0]))
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

    def _priority(self, path: str) -> int:
        """0 source, 1 test source, 2 markdown (doc sections), 3 files that yield no entities"""
        language = self._detect_language(path.split("/")[-1])
        if language in _SOURCE_LANGUAGES:
            return 1 if is_test_path(path) else 0
        return 2 if language == "markdown" else 3

    def _detect_language(self, filename: str) -> str:
        """Detect programming language from file extension"""
        if not filename:
            return "text"

        ext = filename.lower().split(".")[-1] if "." in filename else ""
        return EXT_TO_LANGUAGE.get(ext, "text")

    @staticmethod
    def _decode_content(raw: bytes) -> str | None:
        """Decode downloaded bytes to text, or None for empty and binary files"""
        if not raw or b"\x00" in raw:
            return None
        return raw.decode("utf-8-sig", errors="replace")


class GitHubService(FileSelector):
    """
    GitHub API client for repository analysis with performance optimizations.
    Based on architecture.md: External Integration → GitHub API
    """

    def __init__(self):
        self.token = get_settings().github_token
        self.base_url = "https://api.github.com"
        self.raw_base_url = "https://raw.githubusercontent.com"
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        super().__init__()
        self._walk_requests = 0

        if not self.token:
            logger.warning("GitHub token not found. Rate limits will be lower.")

    def _new_session(self, total_timeout: float = 30) -> aiohttp.ClientSession:
        """One session per get_repository_files call"""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "CodeSage-MCP-Server/1.0",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        timeout = aiohttp.ClientTimeout(total=total_timeout, connect=10)
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
            except TimeoutError as e:
                target = f"{owner}/{repo}/{path}" if path else f"{owner}/{repo}"
                logger.warning("GitHub request timed out", url=url, error=str(e))
                failure = GitHubAPIError(504, f"GitHub did not respond in time while reading {target}")
            except aiohttp.ClientError as e:
                target = f"{owner}/{repo}/{path}" if path else f"{owner}/{repo}"
                logger.warning("GitHub request failed", url=url, error=str(e))
                failure = GitHubAPIError(503, f"Could not reach GitHub while reading {target}")

            attempt += 1
            if attempt >= MAX_RETRIES:
                raise failure
            delay = RETRY_BACKOFF_BASE * 2 ** (attempt - 1)
            logger.warning("Retrying GitHub request", url=url, attempt=attempt, delay=delay)
            await asyncio.sleep(delay)

    async def check_repository(self, url: str, branch: str | None = None) -> None:
        """Fail fast, before a row exists, if the repository or branch can't be read.

        One attempt each for the repository and its branch, 10 s per request (so about 20 s at
        worst): no retries or rate-limit sleeps, since the caller is an HTTP request.
        Raises RepositoryCheckError carrying the HTTP status and message to return.
        """
        owner, repo, url_branch = parse_github_url(url)
        branch = branch or url_branch
        name = f"{owner}/{repo}"
        session = self._new_session(total_timeout=10)
        try:
            status, info = await self._check_get(session, f"{self.base_url}/repos/{owner}/{repo}")
            if status == 404:
                raise RepositoryCheckError(
                    422,
                    f"GitHub repository {name} was not found. Check the URL; "
                    "if it's private, the server's GITHUB_TOKEN needs access.",
                )
            if status == 403:
                raise RepositoryCheckError(422, f"GitHub denied access to {name}.")
            if status != 200 or not isinstance(info, dict):
                raise RepositoryCheckError(502, "Could not reach GitHub; try again.")

            branch = branch or info.get("default_branch")
            if not branch:
                return  # get_repository_files reports a missing default branch itself
            status, _ = await self._check_get(
                session, f"{self.base_url}/repos/{owner}/{repo}/branches/{quote_path(branch)}"
            )
            if status == 404:
                # Assumed: GitHub answers 404 for any branch of an empty repository
                if info.get("size") == 0:
                    raise RepositoryCheckError(422, f"{name} is empty; there is nothing to index.")
                raise RepositoryCheckError(422, f"Branch '{branch}' does not exist in {name}.")
            if status == 403:
                raise RepositoryCheckError(422, f"GitHub denied access to {name}.")
            if status != 200:
                raise RepositoryCheckError(502, "Could not reach GitHub; try again.")
        finally:
            await session.close()

    async def _check_get(self, session: aiohttp.ClientSession, url: str) -> tuple[int, Any]:
        """One GET for check_repository: (status, JSON) for 200, 403 and 404, else raises"""
        try:
            async with session.get(url) as response:
                status, headers = response.status, response.headers
                body = await response.json(content_type=None) if status == 200 else None
        except TimeoutError as e:
            logger.warning("GitHub check timed out", url=url, error=str(e))
            raise RepositoryCheckError(504, "GitHub did not respond in time; try again.") from e
        except aiohttp.ClientError as e:
            logger.warning("GitHub check failed", url=url, error=str(e))
            raise RepositoryCheckError(502, "Could not reach GitHub; try again.") from e

        if is_rate_limited(status, headers):
            wait = rate_limit_wait(headers) or 60.0
            raise RepositoryCheckError(
                503,
                f"GitHub's API rate limit was reached; try again in {_about_minutes(wait)}.",
                {"Retry-After": str(math.ceil(wait))},
            )
        if status == 401:
            raise RepositoryCheckError(
                502,
                "GitHub rejected the server's GITHUB_TOKEN; check the token configured "
                "on the CodeSage server.",
            )
        if status >= 500:
            logger.warning("GitHub check got a server error", url=url, status=status)
            raise RepositoryCheckError(502, "Could not reach GitHub; try again.")
        return status, body

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
                # One commit for the listing and every download: a push mid-run can't mix two
                self.commit_sha = await self._resolve_commit(session, owner, repo, branch)
                entries = await self._list_entries(session, owner, repo, self.commit_sha)
                candidates = self._select_candidates(entries)
                files = await self._download_all(session, owner, repo, self.commit_sha, candidates)
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

    async def _resolve_commit(
        self, session: aiohttp.ClientSession, owner: str, repo: str, branch: str
    ) -> str:
        """The commit `branch` points at"""
        try:
            info = await self._make_request_with_retries(
                session, f"{self.base_url}/repos/{owner}/{repo}/branches/{quote_path(branch)}", owner, repo
            )
        except GitHubAPIError as e:
            if e.status != 404:
                raise
            # Say which is missing: a missing repository raises its own 404 from this lookup
            await self._make_request_with_retries(
                session, f"{self.base_url}/repos/{owner}/{repo}", owner, repo
            )
            raise GitHubAPIError(404, f"Branch '{branch}' not found in {owner}/{repo}") from e
        sha = (info.get("commit") or {}).get("sha") if isinstance(info, dict) else None
        if not isinstance(sha, str) or not sha:
            raise GitHubAPIError(502, f"GitHub did not report a commit for {owner}/{repo} branch '{branch}'")
        return sha

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

    @staticmethod
    def _describe_api_error(status: int, headers, owner: str, repo: str, path: str) -> str:
        """Explain a failed contents request in terms a user can act on"""
        target = f"{owner}/{repo}/{path}" if path else f"{owner}/{repo}"
        if status == 401:
            return f"GitHub rejected the token (401) for {target}; check GITHUB_TOKEN"
        if is_rate_limited(status, headers):
            wait = rate_limit_wait(headers)
            retry = f"; try again in {_about_minutes(wait)}" if wait else ""
            return f"GitHub API rate limit exceeded ({status}) while reading {target}{retry}"
        if status == 403:
            return f"GitHub denied access (403) to {target}"
        if status == 404:
            return f"GitHub repository or path not found (404): {target}; it may be private or misspelled"
        return f"GitHub API error {status} while reading {target}"

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
