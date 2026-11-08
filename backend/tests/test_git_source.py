"""git_source with the git subprocess mocked: no network, no real git"""

import asyncio
import base64
import os
import re
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings, parse_git_host_credentials
from app.services import git_source
from app.services.github_service import GitHubAPIError, RepositoryCheckError

URL = "https://gitlab.com/group/sub/repo"
TOKEN = "glpat-s3cret=:x"  # a token may hold '=' and ':'
ENCODED = base64.b64encode(f"oauth2:{TOKEN}".encode()).decode()


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


PUBLIC_ADDRESS = "140.82.112.3"


@pytest.fixture(autouse=True)
def resolve(monkeypatch):
    """Answer DNS from `resolve.answers` (host -> addresses), never the network"""
    resolve.answers = {}

    async def fake(host):
        return set(resolve.answers.get(host, {PUBLIC_ADDRESS}))

    monkeypatch.setattr(git_source, "_resolve", fake)
    return resolve


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


@pytest.fixture
def credentials(monkeypatch):
    """gitlab.com has a token in GIT_HOST_CREDENTIALS"""
    monkeypatch.setattr(get_settings(), "git_host_credentials", f"gitlab.com=oauth2:{TOKEN}")


async def check(url=URL, branch=None) -> RepositoryCheckError | None:
    try:
        await git_source.check_remote(url, branch)
    except RepositoryCheckError as e:
        return e
    return None


SHA = "a" * 40


@pytest.mark.parametrize(
    "answers",
    [{"10.0.0.1"}, {"127.0.0.1"}, {"169.254.169.254"}, {"fd00::1"}, {PUBLIC_ADDRESS, "192.168.1.5"}, set()],
)
async def test_hosts_that_resolve_to_private_addresses_are_refused(spawn, resolve, answers):
    # A name like 10.0.0.1.nip.io passes the URL's IP-literal check but must not reach git
    resolve.answers["gitlab.com"] = answers

    error = await check()
    assert error is not None and error.status_code == 422
    with pytest.raises(GitHubAPIError, match="private or loopback") as clone_error:
        await git_source.GitSource().get_repository_files(URL)
    assert clone_error.value.status == 422
    assert spawn.calls == []


async def test_the_pinned_address_prefers_ipv4(spawn, resolve):
    resolve.answers["gitlab.com"] = {"2606:4700::1111", PUBLIC_ADDRESS}
    await check()
    [(argv, _)] = spawn.calls
    assert f"http.curloptResolve=gitlab.com:443:{PUBLIC_ADDRESS}" in argv

    resolve.answers["gitlab.com"] = {"2606:4700::1111"}
    await check()
    assert "http.curloptResolve=gitlab.com:443:[2606:4700::1111]" in spawn.calls[-1][0]


async def test_a_reachable_repository_passes(spawn):
    spawn.process = FakeProcess(out=f"ref: refs/heads/main\tHEAD\n{SHA}\trefs/heads/main\n")
    assert await check() is None
    assert await check(branch="main") is None


async def test_git_runs_without_a_shell_prompt_credentials_or_other_protocols(spawn):
    await check(branch="dev")

    [(argv, kwargs)] = spawn.calls
    assert argv[0] == "git"
    joined = " ".join(argv)
    for flag in (
        "credential.helper=", "protocol.allow=never", "protocol.https.allow=always",
        f"http.curloptResolve=gitlab.com:443:{PUBLIC_ADDRESS}",
    ):  # fmt: skip
        assert f"-c {flag}" in joined
    assert argv[argv.index("ls-remote") :] == (
        "ls-remote", "--heads", "--symref", "--", URL, "refs/heads/dev"
    )  # fmt: skip
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["stdin"] == asyncio.subprocess.DEVNULL
    assert "shell" not in kwargs


# What git prints when the host refuses: a 401 shows up as the username prompt git can't show
REFUSED = [
    "fatal: Authentication failed for 'https://gitlab.com/group/sub/repo/'",
    "fatal: could not read Username for 'https://gitlab.com': terminal prompts disabled",
    "fatal: unable to access 'https://gitlab.com/group/sub/repo.git/': The requested URL returned error: 403",
    "remote: The project you were looking for could not be found.\nfatal: repository 'x' not found",
]


@pytest.mark.parametrize("stderr", REFUSED)
async def test_missing_or_private_is_422(spawn, stderr):
    spawn.process = FakeProcess(code=128, err=stderr)
    error = await check()
    assert (error.status_code, error.detail) == (
        422,
        "gitlab.com/group/sub/repo was not found or is private; only public repositories are "
        "supported on gitlab.com.",
    )


# --- GIT_HOST_CREDENTIALS -------------------------------------------------------


async def test_a_token_goes_to_its_host_in_the_environment_never_argv(spawn, credentials):
    spawn.process = FakeProcess(out=f"ref: refs/heads/main\tHEAD\n{SHA}\tHEAD\n")

    assert await check() is None
    assert await git_source.remote_head(URL) == ("main", SHA)
    await git_source.GitSource().get_repository_files(URL)  # the clone, then rev-parse inside it

    ls_remote, head, clone, rev_parse = spawn.calls
    for argv, kwargs in (ls_remote, head, clone):
        env = kwargs["env"]
        config = [(env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"]) for i in range(int(env["GIT_CONFIG_COUNT"]))]
        assert config == [
            ("http.https://gitlab.com/.extraHeader", f"Authorization: Basic {ENCODED}"),
            ("http.followRedirects", "false"),  # the header can't follow a redirect
        ]
        # ps shows argv; and with redirects off git needs the address gitlab.com doesn't redirect
        assert not any(TOKEN in a or ENCODED in a or "extraHeader" in a for a in argv)
        assert argv[argv.index("--") + 1] == f"{URL}.git"
    assert "GIT_CONFIG_COUNT" not in rev_parse[1]["env"]  # a command on the local clone gets none


async def test_other_hosts_get_no_token(spawn, credentials):
    for url in ("https://bitbucket.org/team/repo", "https://gitlab.com.example.org/group/repo"):
        await check(url)
        argv, kwargs = spawn.calls[-1]
        assert "GIT_CONFIG_COUNT" not in kwargs["env"]
        assert not any(ENCODED in value for value in kwargs["env"].values())
        assert argv[argv.index("--") + 1] == url  # unchanged, redirects allowed as before


@pytest.mark.parametrize("stderr", REFUSED)
async def test_with_a_token_a_refusal_blames_the_token_not_privacy(spawn, credentials, stderr):
    spawn.process = FakeProcess(code=128, err=stderr)
    error = await check()
    assert (error.status_code, error.detail) == (
        422,
        "gitlab.com rejected the token in GIT_HOST_CREDENTIALS or it lacks access to group/sub/repo.",
    )


async def test_with_a_token_a_redirect_says_so(spawn, credentials):
    spawn.process = FakeProcess(code=128, err=f"fatal: unable to access '{URL}.git/': The requested URL returned error: 301")
    error = await check()
    assert (error.status_code, error.detail) == (
        422,
        "gitlab.com redirected group/sub/repo; with a token CodeSage doesn't follow redirects, so use its current address.",
    )


async def test_with_a_token_a_refused_clone_blames_the_token(monkeypatch, credentials):
    seen = fake_clone(monkeypatch, populate, code=128, stderr=REFUSED[1])
    with pytest.raises(GitHubAPIError) as caught:
        await git_source.GitSource().get_repository_files(URL)
    assert (caught.value.status, str(caught.value)) == (
        404,
        "gitlab.com rejected the token in GIT_HOST_CREDENTIALS or it lacks access to group/sub/repo",
    )
    assert seen["host"] == "gitlab.com"


def test_credentials_parse_into_a_host_map():
    raw = " GitLab.com=oauth2:glpat-x , bitbucket.org=x-token-auth:ATCTT3x=AB:C,, "
    expected = {"gitlab.com": "oauth2:glpat-x", "bitbucket.org": "x-token-auth:ATCTT3x=AB:C"}
    assert parse_git_host_credentials(raw) == expected
    assert Settings(_env_file=None, git_host_credentials=raw).git_host_credentials_map == expected
    assert Settings(_env_file=None, git_host_credentials="").git_host_credentials_map == {}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("glpat-SECRET", "entry 1 must look like host=user:token"),
        ("gitlab.com=glpat-SECRET", "entry 1 must look like host=user:token"),
        ("gitlab.com=oauth2:", "entry 1 must look like host=user:token"),
        ("gitlab.com=:glpat-SECRET", "entry 1 must look like host=user:token"),
        ("a.example=u:t,https://gitlab.com=oauth2:glpat-SECRET", "entry 2 must look like host=user:token"),
        ("gitlab.com:443=oauth2:glpat-SECRET", "entry 1 must look like host=user:token"),
        ("gitlab.com/group=oauth2:glpat-SECRET", "entry 1 must look like host=user:token"),
        ("github.com=x:glpat-SECRET", "can't hold github.com; set GITHUB_TOKEN for it"),
        ("www.github.com=x:glpat-SECRET", "can't hold github.com; set GITHUB_TOKEN for it"),
        ("gitlab.com=a:glpat-SECRET,GITLAB.com=b:c", "lists gitlab.com twice"),
    ],
)
def test_bad_credentials_stop_startup_without_echoing_the_token(raw, message):
    with pytest.raises(ValueError, match=re.escape(message)) as caught:
        Settings(_env_file=None, git_host_credentials=raw)
    assert "SECRET" not in str(caught.value)


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


# --- GitSource ---------------------------------------------------------------


def fake_clone(monkeypatch, populate, code=0, stderr=""):
    """Replace the git runner: a clone writes `populate(target)` into the target directory"""
    seen = {}

    async def run(args, timeout, host=None):
        if "rev-parse" in args:
            return 0, "c0ffee\n", ""
        seen["args"], seen["timeout"], seen["host"] = args, timeout, host
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


async def test_a_clone_is_walked_and_applies_the_selection_rules(monkeypatch):
    seen = fake_clone(monkeypatch, populate)

    files = await git_source.GitSource().get_repository_files(URL, "main")

    assert {f.path: f.language for f in files} == {
        "README.md": "markdown",
        "infra/main.tf": "terraform",
        "src/app.py": "python",
    }
    app = next(f for f in files if f.path == "src/app.py")
    assert (app.filename, app.content, app.size) == ("app.py", "def f():\n    pass\n", 18)
    args = seen["args"]
    assert args[:2] == ["-c", f"http.curloptResolve=gitlab.com:443:{PUBLIC_ADDRESS}"]
    assert args[2:7] == ["clone", "--depth", "1", "--single-branch", "--no-tags"]
    assert args[args.index("--branch") + 1] == "main"
    assert "core.symlinks=false" not in args and args[-2] == URL and "--" in args
    assert seen["timeout"] == 120
    assert not seen["target"].parent.exists()  # the temp dir is removed


async def test_without_a_branch_it_clones_the_default(monkeypatch):
    seen = fake_clone(monkeypatch, populate)
    await git_source.GitSource().get_repository_files(URL)
    assert "--branch" not in seen["args"]


async def test_the_source_reports_what_it_skipped_over_the_limit(monkeypatch):
    fake_clone(monkeypatch, populate)
    source = git_source.GitSource()
    source.max_files = 3
    files = await source.get_repository_files(URL, None)
    # Source fills the cap first (blob.py, empty.py, infra/main.tf); the binary and the empty file
    # then drop out, and src/app.py and README.md were over the cap
    assert [f.path for f in files] == ["infra/main.tf"]
    assert source.skipped_files == 2
    assert source.commit_sha == "c0ffee"  # read from the clone's HEAD


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
        await git_source.GitSource().get_repository_files(URL, "dev")

    assert (caught.value.status, str(caught.value)) == (status, message)
    assert caught.value.user_facing
    assert not seen["target"].parent.exists()


async def test_a_clone_timeout_is_504_and_cleans_up(monkeypatch):
    seen = {}

    async def run(args, timeout, host=None):
        seen["target"] = Path(args[-1])
        raise TimeoutError

    monkeypatch.setattr(git_source, "_git", run)

    with pytest.raises(GitHubAPIError) as caught:
        await git_source.GitSource().get_repository_files(URL)

    assert caught.value.status == 504
    assert "did not respond in time" in str(caught.value)
    assert not seen["target"].parent.exists()


async def test_the_temp_dir_is_removed_when_reading_fails(monkeypatch):
    seen = fake_clone(monkeypatch, populate)

    def boom(self, root):
        raise RuntimeError("disk")

    monkeypatch.setattr(git_source.GitSource, "_read_tree", boom)
    with pytest.raises(RuntimeError):
        await git_source.GitSource().get_repository_files(URL)
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

    async def local_git(args, timeout, host=None):
        return await real_git([src.as_uri() if a == URL else a for a in args], timeout, host)

    monkeypatch.setattr(git_source, "_git", local_git)
    monkeypatch.setattr(git_source, "_SAFE_GIT_ARGS", [*git_source._SAFE_GIT_ARGS, "-c", "protocol.file.allow=always"])

    files = await git_source.GitSource().get_repository_files(URL)

    assert [f.path for f in files] == ["a.py"]
