"""Git repositories on any https host (GitLab, Bitbucket, self-hosted), read with the git CLI.

github.com goes through GitHubService and its REST API; every other host lands here. Git runs
without a shell, a credential helper or a prompt, and only over https. A host listed in
GIT_HOST_CREDENTIALS gets its token as a header; on any other host a repository that needs
credentials is refused instead of asking for them.
"""

import asyncio
import base64
import ipaddress
import os
import socket
import tempfile
from pathlib import Path

import structlog

from app.core.config import get_settings
from app.services.github_service import (
    DENIED_DIRS,
    FileSelector,
    GitHubAPIError,
    GitHubFile,
    RepositoryCheckError,
    parse_repository_url,
)

logger = structlog.get_logger()

CHECK_TIMEOUT = 10  # seconds; the caller is an HTTP request or a tool call
CLONE_TIMEOUT = 120

# No credential helper (the user's keychain), https only, whatever the user's git config says.
# Redirects stay on without a token: gitlab.com answers /group/repo with a 301 to /group/repo.git.
# shortcut: git follows that first redirect unchecked, so a hostile public host could point it at an
# internal address; route git through an egress proxy that refuses private addresses if that matters.
# A host with a token gets no redirects at all (see _git_env)
_SAFE_GIT_ARGS = [
    "-c", "credential.helper=",
    "-c", "protocol.allow=never",
    "-c", "protocol.https.allow=always",
]  # fmt: skip

# What git prints when a repository is missing, or answers 401 and wants a password
_NOT_FOUND_MARKERS = (
    "not found",
    "authentication failed",
    "could not read username",
    "could not read password",
    "terminal prompts disabled",
    "invalid username or password",
    "returned error: 401",
    "returned error: 403",
    "returned error: 404",
)


def _credential(host: str) -> str | None:
    """'user:token' for `host` from GIT_HOST_CREDENTIALS, or None"""
    return get_settings().git_host_credentials_map.get(host)


def _remote_url(url: str, host: str, path: str) -> str:
    """The URL git is given. With a token redirects are off, so it must be the one that doesn't
    redirect: gitlab.com sends /group/repo to /group/repo.git"""
    return f"https://{host}/{path}.git" if _credential(host) else url


def _git_env(host: str | None = None) -> dict[str, str]:
    """A clean environment: no user config, no prompts, nothing but what git needs to run.

    For a host with a token: an Authorization header sent only to https://<host>/, and no
    redirects, so the header can't follow one. It goes in GIT_CONFIG_* rather than `-c`, so
    neither `ps` nor a clone's .git/config shows it.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "LC_ALL": "C",
    }
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR", "GIT_SSL_CAINFO", "HTTPS_PROXY", "https_proxy", "NO_PROXY"):
        if key in os.environ:
            env[key] = os.environ[key]
    credential = _credential(host) if host else None
    if credential:
        header = "Authorization: Basic " + base64.b64encode(credential.encode()).decode()
        config = [(f"http.https://{host}/.extraHeader", header), ("http.followRedirects", "false")]
        env["GIT_CONFIG_COUNT"] = str(len(config))
        for i, (key, value) in enumerate(config):
            env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = key, value
    return env


async def _git(args: list[str], timeout: float, host: str | None = None) -> tuple[int, str, str]:
    """Run git with the safety flags; (returncode, stdout, stderr). Kills it on timeout.

    `host` is the remote's host, so its token (if any) is sent. Raises TimeoutError, or OSError
    when git can't be started.
    """
    process = await asyncio.create_subprocess_exec(
        "git",
        *_SAFE_GIT_ARGS,
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_git_env(host),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    return process.returncode, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


async def _resolve(host: str) -> set[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return {info[4][0] for info in infos}


def _is_public(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%", 1)[0]).is_global
    except ValueError:
        return False


async def _pin_public_address(host: str) -> list[str]:
    """`-c` arguments that make git reach `host` at a public address checked here.

    parse_repository_url refuses private IP literals, but a name such as 10.0.0.1.nip.io resolves
    to one. Pinning the checked address also stops git resolving the name again, so a DNS answer
    that changes in between (rebinding) can't send it elsewhere. Raises ValueError otherwise.
    """
    try:
        addresses = await _resolve(host)
    except OSError as e:
        raise ValueError(f"{host} could not be resolved") from e
    if not addresses or not all(_is_public(a) for a in addresses):
        raise ValueError(f"{host} resolves to a private or loopback address")
    address = min(addresses, key=lambda a: ":" in a)  # IPv4 when there is one
    return ["-c", f"http.curloptResolve={host}:443:{f'[{address}]' if ':' in address else address}"]


def _refusal(host: str, path: str, stderr: str) -> str | None:
    """Why the host refused the repository, in words for the user (never the token), or None
    when git failed some other way. A bad token reads 'could not read Username': git got a 401"""
    text = stderr.lower()
    token = _credential(host) is not None
    if token and "returned error: 30" in text:
        return f"{host} redirected {path}; with a token CodeSage doesn't follow redirects, so use its current address"
    if not any(marker in text for marker in _NOT_FOUND_MARKERS):
        return None
    if token:
        return f"{host} rejected the token in GIT_HOST_CREDENTIALS or it lacks access to {path}"
    return f"{host}/{path} was not found or is private; only public repositories are supported on {host}"


async def remote_head(url: str, branch: str | None = None) -> tuple[str | None, str]:
    """(branch, commit) the remote has now for `branch`, or for its default branch when None.

    Raises RepositoryCheckError, like check_remote.
    """
    host, path, _ = parse_repository_url(url)
    want = f"refs/heads/{branch}" if branch else "HEAD"
    stdout = await _ls_remote(url, ["--symref"], [want])
    for line in stdout.splitlines():
        first, _, ref = line.partition("\t")
        if first.startswith("ref: ") and ref == "HEAD":
            branch = first.removeprefix("ref: ").removeprefix("refs/heads/")
        elif ref == want:  # ls-remote patterns match by suffix; only the exact ref counts
            return branch, first
    if branch:
        raise RepositoryCheckError(422, f"Branch '{branch}' does not exist in {host}/{path}.")
    raise RepositoryCheckError(422, f"{host}/{path} is empty; there is nothing to index.")


async def check_remote(url: str, branch: str | None = None) -> None:
    """Fail fast, before a row exists, if the repository or branch can't be read.

    Raises RepositoryCheckError carrying the HTTP status and message to return.
    """
    host, path, url_branch = parse_repository_url(url)
    branch = branch or url_branch
    name = f"{host}/{path}"
    stdout = await _ls_remote(url, ["--heads", "--symref"], [f"refs/heads/{branch}"] if branch else [])
    refs = [line.split("\t")[-1] for line in stdout.splitlines() if not line.startswith("ref:")]
    if branch:
        if f"refs/heads/{branch}" not in refs:
            raise RepositoryCheckError(422, f"Branch '{branch}' does not exist in {name}.")
    elif not refs:
        raise RepositoryCheckError(422, f"{name} is empty; there is nothing to index.")


async def _ls_remote(url: str, options: list[str], patterns: list[str]) -> str:
    """stdout of `git ls-remote <options> -- <url> <patterns>` at a checked public address.

    Raises RepositoryCheckError carrying the HTTP status and message to return.
    """
    host, path, _ = parse_repository_url(url)
    name = f"{host}/{path}"
    try:
        pin = await _pin_public_address(host)
    except ValueError as e:
        raise RepositoryCheckError(422, f"Can't index {name}: {e}.") from e
    args = [*pin, "ls-remote", *options, "--", _remote_url(url, host, path), *patterns]
    try:
        code, stdout, stderr = await _git(args, CHECK_TIMEOUT, host)
    except TimeoutError as e:
        logger.warning("git ls-remote timed out", host=host, path=path)
        raise RepositoryCheckError(504, f"{host} did not respond in time; try again.") from e
    except OSError as e:
        logger.warning("git could not be started", error=str(e))
        raise RepositoryCheckError(502, f"Could not reach {host}; try again.") from e

    if code != 0:
        logger.warning("git ls-remote failed", host=host, path=path, code=code, stderr=stderr[:500])
        if refusal := _refusal(host, path, stderr):
            raise RepositoryCheckError(422, f"{refusal}.")
        raise RepositoryCheckError(502, f"Could not reach {host}; try again.")
    return stdout


class GitSource(FileSelector):
    """Reads a repository's files by cloning it; the same selection rules as GitHubService"""

    async def get_repository_files(self, repo_url: str, branch: str | None = None) -> list[GitHubFile]:
        """Shallow-clone into a temp dir (always removed) and return the indexable files.

        Raises GitHubAPIError for clone failures and ValueError for a bad URL.
        """
        host, path, url_branch = parse_repository_url(repo_url)
        branch = branch or url_branch
        name = f"{host}/{path}"
        try:
            pin = await _pin_public_address(host)
        except ValueError as e:
            raise GitHubAPIError(422, f"Can't clone {name}: {e}") from e
        with tempfile.TemporaryDirectory(prefix="codesage-clone-") as tmp:
            target = str(Path(tmp) / "repo")
            args = [*pin, "clone", "--depth", "1", "--single-branch", "--no-tags"]
            if branch:
                args += ["--branch", branch]
            args += ["--", _remote_url(repo_url, host, path), target]
            logger.info("Cloning repository", host=host, path=path, branch=branch)
            try:
                code, _, stderr = await _git(args, CLONE_TIMEOUT, host)
            except TimeoutError as e:
                raise GitHubAPIError(504, f"{host} did not respond in time while cloning {name}") from e
            except OSError as e:
                logger.warning("git could not be started", error=str(e))
                raise GitHubAPIError(503, f"Could not run git to clone {name}") from e
            if code != 0:
                logger.warning("git clone failed", host=host, path=path, code=code, stderr=stderr[:500])
                if branch and "remote branch" in stderr.lower():
                    raise GitHubAPIError(404, f"Branch '{branch}' not found in {name}")
                if refusal := _refusal(host, path, stderr):
                    raise GitHubAPIError(404, refusal)
                raise GitHubAPIError(502, f"Could not clone {name} from {host}")
            code, out, _ = await _git(["-C", target, "rev-parse", "HEAD"], CHECK_TIMEOUT)
            self.commit_sha = out.strip() if code == 0 and out.strip() else None
            files = await asyncio.to_thread(self._read_tree, Path(target))
        logger.info("Repository files retrieved", host=host, path=path, downloaded=len(files))
        return files

    def _read_tree(self, root: Path) -> list[GitHubFile]:
        """Walk a cloned tree: .git, denied directories and symlinks never get listed (a clone keeps symlinks as real links)"""
        sizes: dict[str, int] = {}
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in DENIED_DIRS]
            for filename in filenames:
                full = Path(directory) / filename
                if full.is_symlink():
                    continue
                sizes[full.relative_to(root).as_posix()] = full.stat().st_size
        files = []
        for rel, size in self._select_candidates(list(sizes.items())):
            content = self._decode_content((root / rel).read_bytes())
            if content is None:
                continue
            filename = rel.split("/")[-1]
            files.append(
                GitHubFile(path=rel, content=content, size=size, language=self._detect_language(filename), filename=filename)
            )
        return files


