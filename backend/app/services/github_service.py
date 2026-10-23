import os
import re
import tempfile
import shutil
from typing import List, Dict, Any, Optional
import asyncio
import aiohttp
import structlog
from urllib.parse import urlparse
import base64
from dataclasses import dataclass
from functools import lru_cache
import time

logger = structlog.get_logger()

# Performance constants
MAX_CONCURRENT_REQUESTS = 5  # GitHub API rate limiting
REQUEST_DELAY = 0.1  # Delay between requests to avoid rate limits
CACHE_TTL = 300  # 5 minutes cache for repository metadata
MAX_RETRIES = 3  # Retry failed requests


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
        self.session = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._cache = {}  # Simple in-memory cache

        # Set processing limits
        self.max_files = 1000  # Maximum number of files to process
        self.max_file_size = 1024 * 1024  # 1MB file size limit

        if not self.token:
            logger.warning("GitHub token not found. Rate limits will be lower.")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with proper headers"""
        if not self.session:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "CodeSage-MCP-Server/1.0",
            }
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            # Optimize connection pooling for GitHub API
            connector = aiohttp.TCPConnector(
                limit=100,  # Total connection pool size
                limit_per_host=MAX_CONCURRENT_REQUESTS,  # Per-host limit
                keepalive_timeout=30,
                enable_cleanup_closed=True,
            )

            timeout = aiohttp.ClientTimeout(total=30, connect=10)

            self.session = aiohttp.ClientSession(
                headers=headers, connector=connector, timeout=timeout
            )
        return self.session

    async def _make_request_with_retries(self, url: str, **kwargs) -> Dict[str, Any]:
        """Make GitHub API request with retries and rate limiting"""
        async with self._semaphore:  # Limit concurrent requests
            for attempt in range(MAX_RETRIES):
                try:
                    session = await self._get_session()

                    async with session.get(url, **kwargs) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 403:
                            # Rate limit hit
                            reset_time = response.headers.get("X-RateLimit-Reset")
                            if reset_time:
                                wait_time = int(reset_time) - int(time.time()) + 1
                                logger.warning(f"Rate limit hit, waiting {wait_time}s")
                                await asyncio.sleep(
                                    min(wait_time, 60)
                                )  # Max 1 minute wait
                                continue
                        elif response.status == 404:
                            logger.error(f"Repository not found: {url}")
                            return {}
                        else:
                            logger.warning(
                                f"GitHub API error {response.status} for {url}"
                            )

                except asyncio.TimeoutError:
                    logger.warning(f"Timeout for {url}, attempt {attempt + 1}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2**attempt)  # Exponential backoff
                        continue

                except Exception as e:
                    logger.error(f"Request failed for {url}: {str(e)}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(1)
                        continue

            return {}  # Return empty dict if all retries failed

    @lru_cache(maxsize=100)
    def _parse_github_url(self, url: str) -> tuple:
        """Parse GitHub URL to extract owner and repository name (cached)"""
        try:
            # More robust parsing for different GitHub URL formats
            match = re.match(
                r"^(?:https|git)://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?$",
                url,
            )
            if match:
                owner, repo = match.groups()
                return owner, repo.replace(".git", "")
            return None, None
        except Exception:
            return None, None

    async def get_repository_files(self, repo_url: str) -> List[GitHubFile]:
        """
        Download files from GitHub repository for processing.
        Based on our architecture: GitHub API → File Extraction → Algolia Indexing
        """
        try:
            logger.info("Starting get_repository_files", repo_url=repo_url)

            # Parse GitHub URL to get owner/repo
            owner, repo = self._parse_github_url(repo_url)
            logger.info("Parsed GitHub URL", owner=owner, repo=repo)

            if not owner or not repo:
                raise ValueError(f"Invalid GitHub URL: {repo_url}")

            logger.info("Fetching repository files", owner=owner, repo=repo)

            # Get repository file tree
            files = await self._get_file_tree(owner, repo)
            logger.info("Raw files from GitHub", total_raw_files=len(files))

            # Filter to code files only
            code_files = [
                f for f in files if f.is_code_file() and f.size < self.max_file_size
            ]
            logger.info(
                "After filtering",
                code_files_count=len(code_files),
                raw_files_count=len(files),
            )

            # Limit number of files for processing
            if len(code_files) > self.max_files:
                logger.warning(
                    "Repository has too many files, limiting to max",
                    total_files=len(code_files),
                    max_files=self.max_files,
                )
                code_files = code_files[: self.max_files]

            logger.info(
                "Repository files retrieved",
                total_files=len(files),
                code_files=len(code_files),
            )

            return code_files

        except Exception as e:
            logger.error(
                "Failed to get repository files", repo_url=repo_url, error=str(e)
            )
            raise

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

    async def _get_file_tree(self, owner: str, repo: str) -> List[GitHubFile]:
        """Get repository file tree using GitHub API"""
        files = []

        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Get repository contents recursively
            await self._fetch_directory_contents(session, owner, repo, "", files)

        return files

    @staticmethod
    def _describe_api_error(
        status: int, headers, owner: str, repo: str, path: str
    ) -> str:
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
    def _decode_content(raw: bytes) -> Optional[str]:
        """Decode downloaded bytes to text, or None for empty and binary files"""
        if not raw or b"\x00" in raw:
            return None
        return raw.decode("utf-8-sig", errors="replace")

    async def _fetch_directory_contents(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        path: str,
        files: List[GitHubFile],
    ):
        """Recursively fetch directory contents.

        Raises GitHubAPIError on any non-200 listing so that an unreadable
        repository fails the run instead of looking like an empty one.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        logger.info("Fetching directory", url=url, path=path)

        headers = {}
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        async with session.get(url, headers=headers) as response:
            logger.info("GitHub API response", status=response.status, url=url)

            if response.status != 200:
                response_text = await response.text()
                logger.warning(
                    "Failed to fetch directory",
                    path=path,
                    status=response.status,
                    response_text=response_text[:500],  # Log first 500 chars of error
                )
                raise GitHubAPIError(
                    response.status,
                    self._describe_api_error(
                        response.status, response.headers, owner, repo, path
                    ),
                )

            contents = await response.json()
            logger.info("Directory contents", path=path, items_count=len(contents))

        for item in contents:
            if item["type"] == "file":
                filename = item["path"].split("/")[-1]
                github_file = GitHubFile(
                    path=item["path"],
                    content="",
                    size=item["size"],
                    language=self._detect_language(filename),
                    filename=filename,
                )
                # Filter before downloading so skipped files cost no requests
                if (
                    not github_file.is_code_file()
                    or github_file.size >= self.max_file_size
                ):
                    logger.debug(
                        "Filtered out file",
                        file_path=item["path"],
                        size=github_file.size,
                        language=github_file.language,
                    )
                    continue

                content = self._decode_content(
                    await self._download_file_content(session, item["download_url"])
                )
                if content is None:
                    logger.debug("Skipped empty or binary file", file_path=item["path"])
                    continue

                github_file.content = content
                files.append(github_file)
                logger.debug(
                    "Added code file",
                    file_path=item["path"],
                    language=github_file.language,
                )

            elif item["type"] == "dir" and len(files) < self.max_files:
                logger.debug("Processing directory", dir_path=item["path"])
                # Recursively fetch subdirectory (with limit)
                await self._fetch_directory_contents(
                    session, owner, repo, item["path"], files
                )

    async def _download_file_content(
        self, session: aiohttp.ClientSession, download_url: str
    ) -> bytes:
        """Download individual file content as bytes"""
        try:
            headers = {}
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            async with session.get(download_url, headers=headers) as response:
                if response.status == 200:
                    content = await response.read()
                    return content
                logger.warning(
                    "Failed to download file", url=download_url, status=response.status
                )
                return b""
        except Exception as e:
            logger.error("Failed to download file", url=download_url, error=str(e))
            return b""
