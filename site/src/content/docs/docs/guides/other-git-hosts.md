---
title: Other git hosts
description: Add public GitLab, Bitbucket and self-hosted repositories through the add_repository tool.
---

The dashboard and the REST API take github.com only. Claude can also add a public repository from GitLab, Bitbucket or a self-hosted git server by calling the `add_repository` tool. This page covers the URLs it accepts, how the backend reads the repository, the links in search results and every refusal message.

Ask Claude something like:

> Add https://gitlab.com/group/project to CodeSage.

Claude calls `add_repository`, which returns `repository_id`, `name`, `status` and `Indexing started; check list_repositories for progress.` Indexing runs in the background. Ask Claude to check `list_repositories`, and search once the status is `completed`. Then try *"Search it for where requests are retried."*

## Accepted URL forms

The URL must be an `https` URL on a public host. The tool also accepts `http://` (rewritten to `https://`) and `git@host:path` (rewritten to `https://host/path`).

| Host | URL | Result |
| --- | --- | --- |
| GitLab | `https://gitlab.com/group/project` | Name `gitlab.com/group/project`, default branch |
| GitLab, nested groups | `https://gitlab.com/group/subgroup/project` | Name `gitlab.com/group/subgroup/project` |
| GitLab, branch | `https://gitlab.com/group/project/-/tree/dev` | Branch `dev` |
| GitLab, branch with slash | `https://gitlab.com/group/project/-/tree/feature/login` | Branch `feature/login` |
| Bitbucket | `https://bitbucket.org/team/repo` | Name `bitbucket.org/team/repo` |
| Bitbucket, branch | `https://bitbucket.org/team/repo/src/main` | Branch `main` |
| Self-hosted | `https://git.example.com/team/repo` | Name `git.example.com/team/repo` |
| Self-hosted, nested path | `https://git.example.com/a/b/c` | Name `git.example.com/a/b/c` |
| GitHub | `https://github.com/owner/repo/tree/dev` | Name `owner/repo`, branch `dev` |
| Any host, `.git` suffix | `https://gitlab.com/group/project.git` | `.git` and a trailing slash are removed |
| Any host, SSH form | `git@gitlab.com:group/project.git` | Rewritten to `https://gitlab.com/group/project` |

Rules behind the table:

- **Branch markers.** On GitHub the branch follows `/tree/`. On other hosts it follows `/-/tree/`. On `bitbucket.org` it follows `/src/`. Everything after the marker is joined into the branch name, so a URL that ends in a file path becomes a very odd branch. Pass a plain repository URL plus the `branch` argument when in doubt.
- **Other hosts.** Without one of those markers, extra path segments are read as nested groups. A forge with a different URL style (Gitea's `/src/branch/main`, for example) isn't understood; the segments become part of the repository path and the clone later fails.
- **Argument wins.** If you pass `branch` it overrides the branch in the URL. An empty `branch` means the default branch, even with a `/tree/` URL.
- **Segment characters.** Each path segment may contain only letters, digits, `_`, `.` and `-`, and may not be `.` or `..`.
- **`www.`** is removed only from `www.github.com`.
- **Length.** The URL is at most 500 characters and the derived name at most 255.
- **One row per URL.** The stored URL has no branch, so you can't index two branches of the same repository. A second add, even with another branch or another letter case, is refused as a duplicate.

## Names

A GitHub repository is named `owner/repo`. Every other repository is named `<host>/<path>`, such as `gitlab.com/group/project`, so names from different hosts can't collide. Pass that name, its numeric ID, or the same name in any letter case as the `repository` argument of the other tools.

## Public repositories only

Git can't ask for credentials here, so a repository that needs a login is treated as missing. Private repositories are refused on every host except github.com, where the server's `GITHUB_TOKEN` can read them. The message is:

```text
gitlab.com/group/project was not found or is private; only public repositories are supported on gitlab.com.
```

A repository that answers `401`, `403` or `404` to git, or prints "authentication failed" or "terminal prompts disabled", is reported this way.

## Rejected URLs

A URL the backend rejects comes back as an error that starts with `url:` and says why. Nothing is created.

| Rejected | Message after `url: ` |
| --- | --- |
| `ssh://...`, `ftp://...`, `git://...` | `Invalid repository URL (only https is supported): <url>` |
| No host | `Invalid repository URL (missing host): <url>` |
| `https://user:pass@host/...` or `https://user@host/...` | `Invalid repository URL (credentials are not allowed): <url>` |
| Any port, even `:443` | `Invalid repository URL (ports are not supported): <url>` |
| `?query` or `#fragment` | `Invalid repository URL (query or fragment not allowed): <url>` |
| `localhost` or `*.localhost` | `Invalid repository URL (localhost is not allowed): <url>` |
| `127.0.0.1`, `10.0.0.5`, `192.168.1.5`, `[::1]` (any non-public IP literal) | `Invalid repository URL (private or loopback address): <url>` |
| A `/-/` not followed by `tree`; a GitHub URL with extra segments other than `/tree/<branch>`; a Bitbucket URL with extra segments other than `/src/<branch>` | `Invalid repository URL (unsupported path): <url>` |
| Fewer than two path segments | `Invalid repository URL (missing owner or repository): <url>` |
| A segment with other characters, or `.` and `..` | `Invalid repository URL (bad owner or repository name): <url>` |
| A branch starting with `-` or containing a `..` segment | `Invalid repository URL (bad branch): <url>` |
| A branch argument with the same faults | `branch: Invalid branch name` |
| An empty or whitespace-only URL | `Invalid repository URL: empty` |
| Over 500 characters | `url: String should have at most 500 characters` |

The IP rule means a repository on a private network (an internal GitLab at `10.x.x.x`) can't be added by IP. A private DNS name is not checked by the URL rules, but the clone must still work without credentials.

## How the backend reads the repository

github.com goes through the GitHub REST API. Any other host is read with the `git` command, so the backend machine needs `git` (the prod Docker image includes it).

1. **Check.** Before anything is created, the backend runs `git ls-remote --heads --symref -- <url>` (with `refs/heads/<branch>` appended when a branch is set). It times out after **10 seconds**.
2. **Create.** If the check passes, a repository row is created with status `pending` and a background job starts.
3. **Clone.** The job runs `git clone --depth 1 --single-branch --no-tags` (with `--branch <b>` when set) into a temporary `codesage-clone-*` folder. It times out after **120 seconds**. The folder is always removed afterwards.
4. **Select.** The same rules as for GitHub apply: skip `node_modules`, `dist`, `build`, `vendor`, `third_party`, `.git`, `__pycache__`, `.next` and `coverage`; skip minified files, source maps and lockfiles; keep known extensions only; skip files of 1 MB or more; keep the first 1000 files or 100 MB by path. Anything left out makes the index partial.
5. **Parse, store, index.** The same pipeline as for GitHub. See [Indexing pipeline](/docs/concepts/indexing-pipeline/).

### The git sandbox

Git runs without a shell (`create_subprocess_exec`), with no stdin, and is killed on timeout. Every call carries:

- `-c credential.helper=`, so your keychain is never consulted;
- `-c protocol.allow=never -c protocol.https.allow=always`, so only https works whatever your git config says;
- a clean environment: `PATH`, `HOME` set to the null device, `GIT_TERMINAL_PROMPT=0`, `GIT_CONFIG_GLOBAL` set to the null device, `GIT_CONFIG_NOSYSTEM=1` and `LC_ALL=C`. Only `SSL_CERT_FILE`, `SSL_CERT_DIR`, `GIT_SSL_CAINFO`, `HTTPS_PROXY`, `https_proxy` and `NO_PROXY` are passed through from the backend's own environment.

Symlinks: a clone keeps symlinks as real links. The tree walk doesn't follow or list them, so they are never indexed. (Older notes that mention `core.symlinks=false` are out of date.)

For a host with a private certificate authority, set `SSL_CERT_FILE` (or `GIT_SSL_CAINFO`) in the backend's environment.

## Source links in search results

Search hits carry a link to the exact lines. The format depends on the host and uses the indexed branch (or `HEAD` when none was set):

| Host | Link |
| --- | --- |
| github.com | `https://github.com/<owner>/<repo>/blob/<branch>/<file>#L<start>-L<end>` |
| `gitlab.com`, or any host whose name starts with `gitlab.` | `https://<host>/<path>/-/blob/<branch>/<file>#L<start>-<end>` |
| `bitbucket.org` | `https://bitbucket.org/<path>/src/<branch>/<file>#lines-<start>:<end>` |
| Any other host | No link |

The link points at the branch, not at a commit. If the file changes after indexing, the line numbers can drift until you reprocess. On the repository page the source link reads **View source** for hosts other than github.com.

## Refusal messages

For a non-GitHub URL, `add_repository` returns one of these, and nothing is created. (For github.com URLs, the tool uses GitHub's check and the messages in [the dashboard guide](/docs/guides/web-dashboard/#when-the-server-refuses-a-repository).)

| Message | Cause |
| --- | --- |
| `<host>/<path> was not found or is private; only public repositories are supported on <host>.` | The repository doesn't exist, or it needs a login |
| `Branch '<b>' does not exist in <host>/<path>.` | The branch is missing |
| `<host>/<path> is empty; there is nothing to index.` | The repository has no branches (checked only when no branch was given) |
| `<host> did not respond in time; try again.` | The 10 s check timed out |
| `Could not reach <host>; try again.` | The host failed in another way, or `git` couldn't be started |
| `<host>/<path> is already added as repository <id>.` | The URL already exists (case-insensitive) |
| `Search indexing is not configured on the server (Algolia credentials are missing).` | `ALGOLIA_APP_ID` or `ALGOLIA_ADMIN_API_KEY` is unset |
| `url: ...` | The URL was rejected, see the table above |

The check makes one attempt, with no retries.

A repository that passes the check can still fail while it runs. The reason is stored in `error_message` and shows in `list_repositories`, the dashboard card and the repository page:

| `error_message` | Cause |
| --- | --- |
| `<host> did not respond in time while cloning <host>/<path>` | The clone passed 120 s |
| `Could not run git to clone <host>/<path>` | `git` isn't installed or couldn't start |
| `Branch '<b>' not found in <host>/<path>` | The branch disappeared between the check and the clone |
| `<host>/<path> was not found or is private; only public repositories are supported on <host>` | The repository became private or was removed |
| `Could not clone <host>/<path> from <host>` | Any other clone failure |
| `No supported code files found in repository` | Nothing in the clone matched the file rules |

Fix the cause and reprocess from the repository page.

## Limits

- **Public only** on every host except github.com.
- **Not in the dashboard.** The web form and `POST /api/v1/repositories/` refuse other hosts with `422` and a message that the host must be github.com.
- **Tool limits.** `add_repository` needs the API key like every tool call and counts toward the 30 per minute limit.
- **Clone size.** A shallow clone of a huge repository must finish in 120 seconds and fit the 1000-file and 100 MB selection.

See also [MCP tools](/docs/reference/mcp-tools/), [Claude Desktop](/docs/guides/claude-desktop/) and [Troubleshooting](/docs/troubleshooting/).
