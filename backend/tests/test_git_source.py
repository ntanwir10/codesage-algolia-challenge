"""git_source with the git subprocess mocked: no network, no real git"""

import asyncio
import os
from pathlib import Path

import pytest

from app.services import git_source
from app.services.github_service import GitHubAPIError, RepositoryCheckError

URL = "https://gitlab.com/group/sub/repo"


class FakeProcess:
    def __init__(self, code=0, out="", err="", hang=False):
        self.returncode = code
        self._out, self._err, self._hang = out.encode(), err.encode(), hang
        self.killed = False

    async def communicate(self):
        if self._hang:
            await asyncio.sleep(60)
        return self._out, self._err

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


@pytest.fixture
def spawn(monkeypatch):
    """Mock asyncio.create_subprocess_exec; `spawn.process` is what it returns"""
    calls = []

    async def fake(*argv, **kwargs):
        calls.append((argv, kwargs))
        if isinstance(spawn.process, Exception):
            raise spawn.process
        return spawn.process

    spawn.calls = calls
    spawn.process = FakeProcess()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake)
    return spawn


async def check(url=URL, branch=None) -> RepositoryCheckError | None:
    try:
        await git_source.check_remote(url, branch)
    except RepositoryCheckError as e:
        return e
    return None


SHA = "a" * 40


async def test_a_reachable_repository_passes(spawn):
    spawn.process = FakeProcess(out=f"ref: refs/heads/main\tHEAD\n{SHA}\trefs/heads/main\n")
    assert await check() is None
    assert await check(branch="main") is None


async def test_git_runs_without_a_shell_prompt_credentials_or_other_protocols(spawn):
    await check(branch="dev")

    [(argv, kwargs)] = spawn.calls
    assert argv[0] == "git"
    joined = " ".join(argv)
    for flag in ("credential.helper=", "protocol.allow=never", "protocol.https.allow=always"):
        assert f"-c {flag}" in joined
    assert argv[argv.index("ls-remote") :] == (
        "ls-remote", "--heads", "--symref", "--", URL, "refs/heads/dev"
    )  # fmt: skip
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["stdin"] == asyncio.subprocess.DEVNULL
    assert "shell" not in kwargs


@pytest.mark.parametrize(
    "stderr",
    [
        "fatal: Authentication failed for 'https://gitlab.com/group/sub/repo/'",
        "fatal: could not read Username for 'https://gitlab.com': terminal prompts disabled",
        "remote: The project you were looking for could not be found.\nfatal: repository 'x' not found",
    ],
)
async def test_missing_or_private_is_422(spawn, stderr):
    spawn.process = FakeProcess(code=128, err=stderr)
    error = await check()
    assert (error.status_code, error.detail) == (
        422,
        "gitlab.com/group/sub/repo was not found or is private; only public repositories are "
        "supported on gitlab.com.",
    )


async def test_a_missing_branch_is_422(spawn):
    spawn.process = FakeProcess(out="")
    error = await check(branch="nope")
    assert (error.status_code, error.detail) == (
        422,
        "Branch 'nope' does not exist in gitlab.com/group/sub/repo.",
    )


async def test_the_branch_in_the_url_is_checked(spawn):
    spawn.process = FakeProcess(out="")
    error = await check(f"{URL}/-/tree/dev")
    assert error.detail == "Branch 'dev' does not exist in gitlab.com/group/sub/repo."


async def test_an_empty_repository_is_422(spawn):
    spawn.process = FakeProcess(out="")
    error = await check()
    assert (error.status_code, error.detail) == (
        422,
        "gitlab.com/group/sub/repo is empty; there is nothing to index.",
    )


async def test_a_timeout_is_504_and_kills_git(spawn, monkeypatch):
    monkeypatch.setattr(git_source, "CHECK_TIMEOUT", 0.01)
    spawn.process = FakeProcess(hang=True)
    error = await check()
    assert (error.status_code, error.detail) == (504, "gitlab.com did not respond in time; try again.")
    assert spawn.process.killed


async def test_anything_else_is_502_without_the_stderr(spawn):
    spawn.process = FakeProcess(code=128, err="fatal: unable to access: Could not resolve host: secret.internal")
    error = await check()
    assert (error.status_code, error.detail) == (502, "Could not reach gitlab.com; try again.")
    spawn.process = OSError("git: not installed")
    assert (await check()).status_code == 502


# --- fetch_files -------------------------------------------------------------


def fake_clone(monkeypatch, populate, code=0, stderr=""):
    """Replace the git runner: a clone writes `populate(target)` into the target directory"""
    seen = {}

    async def run(args, timeout):
        seen["args"], seen["timeout"] = args, timeout
        target = Path(args[-1])
        seen["target"] = target
        if code == 0:
            target.mkdir(parents=True)
            populate(target)
        return code, "", stderr

    monkeypatch.setattr(git_source, "_git", run)
    return seen


def write(root: Path, rel: str, content: str | bytes = "x = 1\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode())


def populate(root: Path):
    write(root, "src/app.py", "def f():\n    pass\n")
    write(root, "infra/main.tf", 'resource "a" "b" {}\n')
    write(root, "README.md", "# hi\n")
    write(root, "notes.txt", "not indexed")
    write(root, "node_modules/lib/index.js", "ignored")
    write(root, "dist/out.js", "ignored")
    write(root, "app.min.js", "ignored")
    write(root, ".git/config", "ignored")
    write(root, ".git/hooks/x.py", "ignored")
    write(root, "blob.py", b"\x00\x01binary")
    write(root, "empty.py", "")
    os.symlink("src/app.py", root / "link.py")
    os.symlink("/etc", root / "etcdir")


async def test_fetch_files_walks_the_clone_and_applies_the_selection_rules(monkeypatch):
    seen = fake_clone(monkeypatch, populate)

    files = await git_source.fetch_files(URL, "main")

    assert {f.path: f.language for f in files} == {
        "README.md": "markdown",
        "infra/main.tf": "terraform",
        "src/app.py": "python",
    }
    app = next(f for f in files if f.path == "src/app.py")
    assert (app.filename, app.content, app.size) == ("app.py", "def f():\n    pass\n", 18)
    args = seen["args"]
    assert args[:5] == ["clone", "--depth", "1", "--single-branch", "--no-tags"]
    assert args[args.index("--branch") + 1] == "main"
    assert "core.symlinks=false" not in args and args[-2] == URL and "--" in args
    assert seen["timeout"] == 120
    assert not seen["target"].parent.exists()  # the temp dir is removed


async def test_fetch_files_without_a_branch_clones_the_default(monkeypatch):
    seen = fake_clone(monkeypatch, populate)
    await git_source.fetch_files(URL)
    assert "--branch" not in seen["args"]


async def test_the_source_reports_what_it_skipped_over_the_limit(monkeypatch):
    fake_clone(monkeypatch, populate)
    source = git_source.GitSource()
    source.max_files = 2
    files = await source.get_repository_files(URL, None)
    # the cap counts selected paths: README.md and the binary blob.py; blob.py then drops out
    assert [f.path for f in files] == ["README.md"]
    assert source.skipped_files == 3


@pytest.mark.parametrize(
    ("stderr", "status", "message"),
    [
        (
            "fatal: Remote branch dev not found in upstream origin",
            404,
            "Branch 'dev' not found in gitlab.com/group/sub/repo",
        ),
        (
            "fatal: could not read Username: terminal prompts disabled",
            404,
            "gitlab.com/group/sub/repo was not found or is private; only public repositories are "
            "supported on gitlab.com",
        ),
        ("fatal: unable to access: Could not resolve host", 502, "Could not clone gitlab.com/group/sub/repo from gitlab.com"),
    ],
)
async def test_clone_failures_are_user_facing_and_clean_up(monkeypatch, stderr, status, message):
    seen = fake_clone(monkeypatch, populate, code=128, stderr=stderr)

    with pytest.raises(GitHubAPIError) as caught:
        await git_source.fetch_files(URL, "dev")

    assert (caught.value.status, str(caught.value)) == (status, message)
    assert caught.value.user_facing
    assert not seen["target"].parent.exists()


async def test_a_clone_timeout_is_504_and_cleans_up(monkeypatch):
    seen = {}

    async def run(args, timeout):
        seen["target"] = Path(args[-1])
        raise TimeoutError

    monkeypatch.setattr(git_source, "_git", run)

    with pytest.raises(GitHubAPIError) as caught:
        await git_source.fetch_files(URL)

    assert caught.value.status == 504
    assert "did not respond in time" in str(caught.value)
    assert not seen["target"].parent.exists()


async def test_the_temp_dir_is_removed_when_reading_fails(monkeypatch):
    seen = fake_clone(monkeypatch, populate)

    def boom(self, root):
        raise RuntimeError("disk")

    monkeypatch.setattr(git_source.GitSource, "_read_tree", boom)
    with pytest.raises(RuntimeError):
        await git_source.fetch_files(URL)
    assert not seen["target"].parent.exists()


async def test_symlinks_in_a_real_clone_are_not_indexed(tmp_path, monkeypatch):
    """Real git clone (the production args) of a local repo; only the URL and the protocol allow-list differ"""
    import shutil
    import subprocess

    if not shutil.which("git"):
        pytest.skip("git is not installed")
    outside = tmp_path / "outside"
    write(outside, "secret.py", "SECRET = 1\n")
    src = tmp_path / "src"
    write(src, "a.py", "x = 1\n")
    os.symlink("a.py", src / "link.py")
    os.symlink(outside, src / "linkdir")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(src)]
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
        subprocess.run([*git, *cmd], check=True, capture_output=True)

    real_git = git_source._git

    async def local_git(args, timeout):
        return await real_git([src.as_uri() if a == URL else a for a in args], timeout)

    monkeypatch.setattr(git_source, "_git", local_git)
    monkeypatch.setattr(git_source, "_SAFE_GIT_ARGS", [*git_source._SAFE_GIT_ARGS, "-c", "protocol.file.allow=always"])

    files = await git_source.fetch_files(URL)

    assert [f.path for f in files] == ["a.py"]
