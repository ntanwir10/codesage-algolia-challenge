---
title: MCP tools reference
description: Arguments, constraints, result shapes, limits and errors for the seven CodeSage MCP tools and the two resources.
---

CodeSage serves seven tools and two resources to any MCP client. Claude Desktop reaches them through a stdio bridge that forwards each call to the backend over HTTP. This page lists every argument, every result field and every error message the tools produce. For the HTTP side of the same calls, see [MCP HTTP endpoints](/docs/reference/mcp-endpoints/). For setup, see [Claude Desktop](/docs/guides/claude-desktop/).

Argument schemas live in [`backend/codesage_mcp/schemas.py`](https://github.com/ntanwir10/codesage-algolia-challenge/blob/master/backend/codesage_mcp/schemas.py). The bridge answers `tools/list` from that file, so the list works even while the backend is down. Only tool calls and resource reads need the backend.

## Overview

| Tool | Reads from | Needs a `completed` repository | Required arguments | What it returns |
| --- | --- | --- | --- | --- |
| [`list_repositories`](#list_repositories) | SQLite | No | none | Every repository with status and size |
| [`search_code`](#search_code) | Algolia | Only if `repository` is given | `query` | Ranked hits with file locations, snippets and source links |
| [`get_file`](#get_file) | SQLite | Yes | `repository`, `path` | A file with line numbers, at most 400 lines per call |
| [`list_definitions`](#list_definitions) | SQLite | Yes | `repository` | Entities ordered by file and line |
| [`analyze_repository`](#analyze_repository) | SQLite | Yes | `repository` | Counts, languages, top directories, largest files |
| [`find_patterns`](#find_patterns) | SQLite | Yes | `repository`, `pattern` | Lines matching a literal string or regular expression |
| [`add_repository`](#add_repository) | Git host, SQLite | No | `url` | The new repository's ID and status; indexing continues in the background |

Every tool call counts toward the rate limit of 30 per minute per client address. See [Configuration](/docs/reference/configuration/#rate-limits).

### Shared rules

- **Unknown arguments are rejected.** Every argument model sets `additionalProperties: false`. The bridge checks arguments first, and the backend checks them again.
- **Failures are tool errors.** A failure the caller can act on (an unknown repository, a repository still indexing) comes back as a tool result with `is_error: true` and a one-line message. Transport and HTTP failures also come back as tool errors; see [How failures reach Claude](/docs/reference/mcp-endpoints/#how-failures-reach-claude).
- **Results are JSON text.** The bridge returns the `result` object as pretty-printed JSON in one text block.

## Resolving the `repository` argument

Five tools take a `repository` argument. It accepts three forms, and the backend resolves it the same way for all of them.

| You pass | Matches |
| --- | --- |
| `12` | The repository whose numeric ID is 12 |
| `octo/demo` | A repository whose name, or whose GitHub `owner/name` taken from its URL, equals the text, ignoring case |
| `gitlab.com/group/project` | A repository named `<host>/<path>`, which is how repositories on other hosts are named. The stored URL (`https://gitlab.com/group/project`) also matches |

The rules, in order:

1. The text is trimmed.
2. If it is made only of ASCII digits, it is looked up as an ID and never as a name. A repository whose name is a number can only be reached by its ID. An all-digit value longer than 19 digits is treated as not found, because no ID can be that long.
3. Otherwise the text is lowercased and compared with each repository's name and URL path. One match wins.
4. Several matches are an error that lists the candidates. Use the numeric ID.
5. No match is an error that lists the repository names that exist.

After resolution, every tool except `list_repositories` and `add_repository` checks that the repository is ready.

| Situation | Error message |
| --- | --- |
| No match | `Repository 'nope' not found. Available repositories: gitlab.com/gitlab-org/gitlab-test, pmndrs/zustand` |
| No match and nothing indexed | `Repository 'nope' not found. Available repositories: none indexed yet` |
| More than one match | `Repository 'demo' is ambiguous: demo (id 3), demo (id 7). Use the numeric ID.` |
| Status `failed` | `Repository 'octo/demo' failed to index: <error_message>. Reprocess it from the dashboard.` The `: <error_message>` part is left out when there is none |
| Status `pending` or `processing` | `Repository 'octo/demo' is still indexing (120/400 files); try again when it completes.` The `(n/m files)` part appears only when the total file count is known |

:::note
A repository that finished with `Partially indexed: ...` in `error_message` has status `completed`, so the tools accept it. Read `error_message` in `list_repositories` to see what was left out.
:::

## `list_repositories`

Lists every repository CodeSage knows about, ordered by ID. It does not require a ready repository, so it also shows ones that are indexing or failed. Use it to see IDs, names and progress.

### Arguments

None. The schema is `{"type": "object", "properties": {}, "additionalProperties": false}`.

### Result

| Field | Type | Meaning |
| --- | --- | --- |
| `repositories` | array | One object per repository |
| `repositories[].id` | integer | Numeric ID |
| `repositories[].name` | string | `owner/name` for GitHub, `<host>/<path>` for other hosts |
| `repositories[].url` | string or null | Normalised `https://` URL |
| `repositories[].branch` | string or null | `null` means the default branch |
| `repositories[].status` | string | `pending`, `processing`, `completed` or `failed` |
| `repositories[].total_files` | integer | Files selected for the last run |
| `repositories[].total_entities` | integer | Entities stored in SQLite |
| `repositories[].error_message` | string or null | Why the last run failed, or what a completed run left out |
| `repositories[].processed_at` | string or null | ISO 8601 time the last run finished |

The real result, from a backend holding one finished and one failed repository:

```json title="Result"
{
  "repositories": [
    {
      "id": 1,
      "name": "gitlab.com/gitlab-org/gitlab-test",
      "url": "https://gitlab.com/gitlab-org/gitlab-test",
      "branch": null,
      "status": "failed",
      "total_files": 0,
      "total_entities": 0,
      "error_message": "Processing was interrupted by a server restart; reprocess the repository",
      "processed_at": null
    },
    {
      "id": 2,
      "name": "pmndrs/zustand",
      "url": "https://github.com/pmndrs/zustand",
      "branch": null,
      "status": "completed",
      "total_files": 120,
      "total_entities": 1025,
      "error_message": null,
      "processed_at": "2026-10-26T23:32:50.170474"
    }
  ]
}
```

### Limits and errors

The list is not paged or truncated. This tool has no tool-level errors beyond the transport failures in [How failures reach Claude](/docs/reference/mcp-endpoints/#how-failures-reach-claude).

### Example prompt

> Which repositories does CodeSage have indexed, and are they all finished?

## `search_code`

Full-text search over the Algolia index of functions, classes, imports, Markdown sections and Terraform blocks. Without `repository`, it searches every indexed repository.

### Arguments

| Argument | Type | Required | Default | Constraints |
| --- | --- | --- | --- | --- |
| `query` | string | Yes | none | `minLength` 1 |
| `repository` | string or null | No | all repositories | ID, name or `owner/name`; the repository must be `completed` |
| `language` | string or null | No | none | Exact language label such as `python`, `typescript`, `cpp`, `csharp`. See [Languages](/docs/reference/languages/) |
| `entity_type` | string or null | No | none | One of `function`, `class`, `import`, `doc_section`, `terraform_block` |
| `limit` | integer | No | 10 | 1 to 50. Results per page |
| `page` | integer | No | 0 | 0 or more. Zero-based |

### How the search runs

- Each query asks Algolia to drop words that miss when nothing matches every word (`removeWordsIfNoResults: allOptional`), ignore stop words and plurals, and use English (`queryLanguages: ["en"]`). A question in plain words returns the best partial matches instead of nothing.
- `repository`, `language` and `entity_type` become filters joined with `AND`. Values are quoted and escaped, so input cannot add filter clauses.
- On a relevance tie, `rank_weight` decides the order: classes, then functions and Terraform blocks, then doc sections, then imports. See [Algolia record fields](/docs/reference/languages/#algolia-record-fields).
- With no `repository`, hits can come from repositories that are being reprocessed.

### Result

| Field | Type | Meaning |
| --- | --- | --- |
| `query` | string | The query as sent |
| `repository` | string or null | Name of the repository you filtered by, otherwise `null` |
| `total_hits` | integer | Total matches reported by Algolia (`nbHits`) |
| `page` | integer | The page returned |
| `pages` | integer | Total pages (`nbPages`) |
| `results` | array | Hits for this page |
| `results[].entity_name` | string | Bare name, for example `parse_repository_url` |
| `results[].entity_type` | string | One of the five entity types |
| `results[].file_path` | string | Path inside the repository |
| `results[].line_start`, `line_end` | integer | 1-based line range |
| `results[].language` | string | Language label of the file |
| `results[].signature` | string or null | The definition line, cut at 300 characters; `null` when empty |
| `results[].snippet` | string | Signature plus body, cut at 600 characters |
| `results[].description` | string or null | For example `Python function: GitSource._read_tree`, cut at 300 characters; `null` when empty |
| `results[].url` | string or null | Source link at the exact lines, or `null` when the host has no known link format |

Source link formats:

| Host | Link |
| --- | --- |
| github.com | `https://github.com/<owner>/<repo>/blob/<ref>/<path>#L<start>-L<end>` |
| gitlab.com and hosts starting with `gitlab.` | `https://<host>/<path>/-/blob/<ref>/<file>#L<start>-<end>` |
| bitbucket.org | `https://bitbucket.org/<path>/src/<ref>/<file>#lines-<start>:<end>` |
| Any other host | `null` |

`<ref>` is the repository's branch, or `HEAD` when it has none. Path segments are percent-encoded.

Real output for `query: "createStoreImpl"`, `repository: "pmndrs/zustand"` and `limit: 2`. The `snippet` strings are trimmed here with `…`:

```json title="Result"
{
  "query": "createStoreImpl",
  "repository": "pmndrs/zustand",
  "total_hits": 5,
  "page": 0,
  "pages": 3,
  "results": [
    {
      "entity_name": "createStoreImpl",
      "entity_type": "function",
      "file_path": "src/vanilla.ts",
      "line_start": 60,
      "line_end": 97,
      "language": "typescript",
      "signature": "const createStoreImpl: CreateStoreImpl = (createState) => {",
      "snippet": "const createStoreImpl: CreateStoreImpl = (createState) => {\n  type TState = ReturnType<typeof createState>\n  type Listener = (state: TState, prevState: TState) => void\n  let state: TState\n  const listeners: Set<Listener> = new Set…",
      "description": "TypeScript function: createStoreImpl",
      "url": "https://github.com/pmndrs/zustand/blob/HEAD/src/vanilla.ts#L60-L97"
    },
    {
      "entity_name": "setState",
      "entity_type": "function",
      "file_path": "src/vanilla.ts",
      "line_start": 66,
      "line_end": 81,
      "language": "typescript",
      "signature": "const setState: StoreApi<TState>['setState'] = (partial, replace) => {",
      "snippet": "  const setState: StoreApi<TState>['setState'] = (partial, replace) => {\n    // TODO: Remove type assertion once https://github.com/microsoft/TypeScript/issues/37663 is resolved\n    // https://github.com/microsoft/TypeScript/issue…",
      "description": "TypeScript function: createStoreImpl.setState",
      "url": "https://github.com/pmndrs/zustand/blob/HEAD/src/vanilla.ts#L66-L81"
    }
  ]
}
```

### Limits and truncation

- `limit` is capped at 50 per page. Use `page` for more.
- Snippets are cut at 600 characters, and signatures and descriptions at 300.
- The index stores at most 2,000 characters of each entity's body, so a snippet never shows more than that.

### Errors

| Message | Cause |
| --- | --- |
| Any message from [Resolving the repository argument](#resolving-the-repository-argument) | The `repository` is unknown, ambiguous, failed or still indexing |
| `Search is not configured on the server (ALGOLIA_APP_ID / ALGOLIA_ADMIN_API_KEY are missing).` | The backend has no Algolia credentials |
| `Search is unavailable; try again later.` | Algolia rejected the query or could not be reached. The detail is logged on the backend only, because it can name the Algolia host or app ID |

### Example prompt

> Search the octo/demo repository for where the Algolia index settings are applied.

## `get_file`

Reads one stored file with line numbers. The text comes from SQLite, so it matches what was indexed, not the live branch.

### Arguments

| Argument | Type | Required | Default | Constraints |
| --- | --- | --- | --- | --- |
| `repository` | string | Yes | none | ID, name or `owner/name`; must be `completed` |
| `path` | string | Yes | none | Exact path, case-sensitive, relative to the repository root |
| `start_line` | integer or null | No | 1 | 1 or more |
| `end_line` | integer or null | No | end of file | 1 or more |

### Result

| Field | Type | Meaning |
| --- | --- | --- |
| `repository` | string | Repository name |
| `path` | string | The stored path |
| `language` | string | Language label |
| `total_lines` | integer | Lines in the whole file |
| `start_line` | integer | First line returned |
| `end_line` | integer | Last line returned |
| `truncated` | boolean | `true` if the 400-line or 100,000-character cap cut the output short |
| `content` | string | Lines formatted as `<number>\| <text>`, with the number right-aligned to at least 4 characters |

Real output for `repository: "pmndrs/zustand"`, `path: "src/vanilla.ts"`, `start_line: 1` and `end_line: 6`:

```json title="Result"
{
  "repository": "pmndrs/zustand",
  "path": "src/vanilla.ts",
  "language": "typescript",
  "total_lines": 100,
  "start_line": 1,
  "end_line": 6,
  "truncated": false,
  "content": "   1| type SetStateInternal<T> = {\n   2|   _(\n   3|     partial: T | Partial<T> | { _(state: T): T | Partial<T> }['_'],\n   4|     replace?: false,\n   5|   ): void\n   6|   _(state: T | { _(state: T): T }['_'], replace: true): void"
}
```

### Limits and truncation

- At most 400 lines per call (`MAX_FILE_LINES`). The returned `end_line` is the smaller of your `end_line`, the last line and `start_line + 399`.
- At most 100,000 characters of formatted `content`.
- When `truncated` is `true`, call again with `start_line` set to the returned `end_line + 1`.

### Errors

| Message | Cause |
| --- | --- |
| `File 'src/mian.py' not found in octo/demo. Close paths: src/main.py, src/main_test.py` | No stored file has that exact path. Up to 10 similar paths (similarity cutoff 0.4) are suggested. The `Close paths:` part is left out when none are close |
| `start_line 500 is past the end of the file (104 lines)` | `start_line` is greater than the line count |
| `end_line must not be before start_line` | `end_line` is smaller than `start_line` |
| Repository errors | See [Resolving the repository argument](#resolving-the-repository-argument) |

### Example prompt

> Show me lines 1 to 120 of backend/app/main.py in octo/demo.

## `list_definitions`

Lists stored entities for one repository, ordered by file path, then start line, then ID. It reads SQLite, so it is exact and unranked.

### Arguments

| Argument | Type | Required | Default | Constraints |
| --- | --- | --- | --- | --- |
| `repository` | string | Yes | none | ID, name or `owner/name`; must be `completed` |
| `path_prefix` | string or null | No | none | Only files whose path starts with this text. Literal match, no wildcards |
| `entity_type` | string or null | No | none | `function`, `class`, `import`, `doc_section` or `terraform_block` |
| `name` | string or null | No | none | Case-insensitive substring of the entity name. Literal match |
| `limit` | integer | No | 100 | 1 to 500 |

### Result

| Field | Type | Meaning |
| --- | --- | --- |
| `repository` | string | Repository name |
| `total` | integer | All entities that match the filters, not only those returned |
| `definitions` | array | Up to `limit` entities |
| `definitions[].entity_type` | string | One of the five entity types |
| `definitions[].entity_name` | string | Bare name; methods are not prefixed with their class |
| `definitions[].file_path` | string | Path inside the repository |
| `definitions[].line_start`, `line_end` | integer | 1-based range |
| `definitions[].signature` | string or null | Cut at 300 characters |
| `definitions[].description` | string or null | The stored description, cut at 300 characters |

Real output for `repository: "pmndrs/zustand"`, `path_prefix: "src/vanilla"` and `limit: 3`. `total` is 14, so the response holds the first three of 14 matches:

```json title="Result"
{
  "repository": "pmndrs/zustand",
  "total": 14,
  "definitions": [
    {
      "entity_type": "class",
      "entity_name": "StoreApi",
      "file_path": "src/vanilla.ts",
      "line_start": 9,
      "line_end": 14,
      "signature": "export interface StoreApi<T> {",
      "description": "TypeScript class: StoreApi"
    },
    {
      "entity_type": "class",
      "entity_name": "StoreMutators",
      "file_path": "src/vanilla.ts",
      "line_start": 40,
      "line_end": 40,
      "signature": "export interface StoreMutators<S, A> {}",
      "description": "TypeScript class: StoreMutators"
    },
    {
      "entity_type": "function",
      "entity_name": "createStoreImpl",
      "file_path": "src/vanilla.ts",
      "line_start": 60,
      "line_end": 97,
      "signature": "const createStoreImpl: CreateStoreImpl = (createState) => {",
      "description": "TypeScript function: createStoreImpl"
    }
  ]
}
```

### Limits and errors

`limit` caps the page at 500 and there is no paging, so narrow the filters when `total` is larger than the number returned. Errors are the repository errors from [Resolving the repository argument](#resolving-the-repository-argument).

### Example prompt

> List every class in octo/demo under backend/app/services.

## `analyze_repository`

Returns measured counts and layout, with no interpretation. Use it first to learn what a repository contains.

### Arguments

| Argument | Type | Required | Constraints |
| --- | --- | --- | --- |
| `repository` | string | Yes | ID, name or `owner/name`; must be `completed` |

### Result

| Field | Type | Meaning |
| --- | --- | --- |
| `repository` | string | Repository name |
| `repository_id` | integer | Numeric ID |
| `status` | string | Always `completed` here |
| `total_files` | integer | Files stored |
| `processed_files` | integer | Files processed in the last run |
| `total_lines` | integer | Lines across stored files |
| `total_entities` | integer | Entities stored |
| `entities_by_type` | object | Entity count per type, for example `{"function": 910}` |
| `files_by_language` | object | File count per language label |
| `language` | string or null | Primary programming language chosen by the last run |
| `framework` | string or null | Framework guessed from `package.json` or Python imports |
| `top_directories` | array | Up to 10 `{directory, files}` pairs by file count. The directory is the first path segment, or `(root)` for files at the top |
| `largest_files` | array | The 10 files with the most lines, as `{file_path, line_count}` |
| `definitions_by_language` | object | Entity count per file language. A file with an unknown language is grouped under `unknown` |

Real output for `repository: "pmndrs/zustand"`. The `top_directories` and `largest_files` lists are trimmed to three entries (the tool returns up to 10):

```json title="Result"
{
  "repository": "pmndrs/zustand",
  "repository_id": 2,
  "status": "completed",
  "total_files": 120,
  "processed_files": 120,
  "total_lines": 25117,
  "total_entities": 1025,
  "entities_by_type": {
    "class": 22,
    "doc_section": 398,
    "function": 474,
    "import": 131
  },
  "files_by_language": {
    "css": 3,
    "html": 2,
    "javascript": 14,
    "json": 7,
    "markdown": 47,
    "typescript": 34,
    "yaml": 13
  },
  "language": "typescript",
  "framework": "react",
  "top_directories": [
    {
      "directory": "docs",
      "files": 42
    },
    {
      "directory": "examples",
      "files": 27
    },
    {
      "directory": "src",
      "files": 16
    }
  ],
  "largest_files": [
    {
      "file_path": "tests/devtools.test.tsx",
      "line_count": 2926
    },
    {
      "file_path": "docs/learn/guides/tutorial-tic-tac-toe.md",
      "line_count": 1429
    },
    {
      "file_path": "tests/persistAsync.test.tsx",
      "line_count": 1244
    }
  ],
  "definitions_by_language": {
    "javascript": 64,
    "markdown": 398,
    "typescript": 563
  }
}
```

### Limits and errors

The lists are capped at 10 entries. Errors are the repository errors from [Resolving the repository argument](#resolving-the-repository-argument).

### Example prompt

> Analyze octo/demo: how big is it, which languages does it use and where is the code?

## `find_patterns`

Finds lines in the stored files that match a literal string or a regular expression. Use it when search ranking is not what you want, for example to find every call to a function. Files are scanned in path order.

### Arguments

| Argument | Type | Required | Default | Constraints |
| --- | --- | --- | --- | --- |
| `repository` | string | Yes | none | ID, name or `owner/name`; must be `completed` |
| `pattern` | string | Yes | none | 1 to 200 characters |
| `regex` | boolean | No | `false` | `true` treats `pattern` as a regular expression |
| `path_glob` | string or null | No | none | Matched against the whole path, case-sensitive |
| `max_results` | integer | No | 100 | 1 to 500 |

Matching rules:

- A literal pattern is a case-sensitive substring test on each line.
- A regular expression is compiled with the Python `regex` package and searched in each line. It is not anchored, so use `^` and `$` if you need that. Add `(?i)` for a case-insensitive match.
- `path_glob` uses `fnmatch` semantics on the full path, and `*` also matches `/`. `src/*.py` therefore matches `src/a/b.py`.

### Result

| Field | Type | Meaning |
| --- | --- | --- |
| `repository` | string | Repository name |
| `pattern` | string | The pattern as sent |
| `regex` | boolean | Whether it was treated as a regular expression |
| `total_matches` | integer | Number of matches returned (never more than `max_results`) |
| `truncated` | boolean | `true` if more matches exist, or if a regex time budget ran out |
| `matches` | array | `{file_path, line, text}` objects. `text` is the line with surrounding whitespace removed, cut at 300 characters |
| `skipped_files` | array | Present only when files were skipped. The first 50 paths |
| `skipped_count` | integer | Present only when files were skipped. The full count |

Real output for `repository: "pmndrs/zustand"`, `pattern: "createStoreImpl"` and `max_results: 3`:

```json title="Result"
{
  "repository": "pmndrs/zustand",
  "pattern": "createStoreImpl",
  "regex": false,
  "total_matches": 2,
  "truncated": false,
  "matches": [
    {
      "file_path": "src/vanilla.ts",
      "line": 60,
      "text": "const createStoreImpl: CreateStoreImpl = (createState) => {"
    },
    {
      "file_path": "src/vanilla.ts",
      "line": 100,
      "text": "createState ? createStoreImpl(createState) : createStoreImpl) as CreateStore"
    }
  ]
}
```

### Limits and truncation

| Limit | Value | Effect |
| --- | --- | --- |
| Matches | `max_results` (1 to 500) | The scan stops at the first extra match and sets `truncated: true` |
| Regex time per file | 1 second | The file is added to `skipped_files`; the scan goes on |
| Regex time per call | 10 seconds | The remaining files are added to `skipped_files` and `truncated` is `true` |
| Regex file size | Files over 1,000,000 characters | Skipped and listed in `skipped_files` |
| Literal search | No time limit | Not subject to the regex limits |

### Errors

| Message | Cause |
| --- | --- |
| `Invalid regular expression: <detail>` | `regex` is `true` and `pattern` does not compile |
| Repository errors | See [Resolving the repository argument](#resolving-the-repository-argument) |

### Example prompt

> In octo/demo, find every place that matches `TODO|FIXME` in Python files under backend/, as a regular expression.

## `add_repository`

Adds a repository by `https` URL and starts indexing it in the background. It works with GitHub, GitLab (nested groups too), Bitbucket and self-hosted git servers. It runs the same pre-flight checks as the REST endpoint, and nothing is created if a check fails.

### Arguments

| Argument | Type | Required | Default | Constraints |
| --- | --- | --- | --- | --- |
| `url` | string | Yes | none | `minLength` 1. An `https` repository URL. `http://` and `git@host:path` forms are rewritten to `https://`. A branch URL such as `.../tree/dev`, `.../-/tree/dev` or Bitbucket's `.../src/dev` is understood |
| `branch` | string or null | No | default branch | At most 100 characters. Must not contain a `..` path segment or a NUL, and must not start with `-`. An explicit value wins over a branch in the URL |
| `description` | string or null | No | none | Free text note |

The URL is refused if it has a port, credentials, a query or fragment, the host `localhost` (or `*.localhost`), or a private or loopback IP address. A path that is not `owner/repo` (plus a recognised branch suffix) is refused as well.

Private repositories work only on github.com, and only when the server's `GITHUB_TOKEN` can read them. On every other host the repository must be public.

### Result

| Field | Type | Meaning |
| --- | --- | --- |
| `repository_id` | integer | ID to pass to the other tools |
| `name` | string | `owner/name` for GitHub, `<host>/<path>` otherwise |
| `status` | string | `pending` at creation |
| `message` | string | Always `Indexing started; check list_repositories for progress.` |

The values below are illustrative. This call writes, so it was not run against a live backend; the shape follows the response schema in the code.

```json title="Result"
{
  "repository_id": 5,
  "name": "gitlab.com/group/project",
  "status": "pending",
  "message": "Indexing started; check list_repositories for progress."
}
```

Indexing runs after the tool returns. Poll `list_repositories` until the status is `completed`, then search it.

### Limits

The pre-flight check takes up to 10 seconds. A later clone on a non-GitHub host takes up to 120 seconds. Indexing keeps at most 1,000 files and 100 MB, and skips files of 1 MB or more. See [Indexing pipeline](/docs/concepts/indexing-pipeline/).

### Errors

| Message | Cause |
| --- | --- |
| `url: <reason>` | The URL failed validation, for example `Invalid repository URL (only https is supported): ...` |
| `branch: Invalid branch name` | The branch contains `..`, a NUL, or starts with `-` |
| `octo/demo is already added as repository 1.` | The URL (case-insensitive) already exists |
| `Search indexing is not configured on the server (Algolia credentials are missing).` | `ALGOLIA_APP_ID` or `ALGOLIA_ADMIN_API_KEY` is unset |
| `<host>/<path> was not found or is private; only public repositories are supported on <host>.` | Non-GitHub host: the repository is missing or needs credentials |
| `GitHub repository octo/demo was not found. Check the URL; if it's private, the server's GITHUB_TOKEN needs access.` | github.com: missing, or private without token access |
| `GitHub denied access to octo/demo.` | github.com answered 403 |
| `Branch 'x' does not exist in octo/demo.` | The branch is missing |
| `octo/demo is empty; there is nothing to index.` | No commits |
| `GitHub's API rate limit was reached; try again in about 2 minutes.` | GitHub is rate limiting the server's token |
| `GitHub rejected the server's GITHUB_TOKEN; check the token configured on the CodeSage server.` | The token is invalid |
| `Could not reach GitHub; try again.` or `Could not reach <host>; try again.` | The host or git failed in another way |
| `GitHub did not respond in time; try again.` or `<host> did not respond in time; try again.` | The 10-second check timed out |

### Example prompt

> Add https://gitlab.com/group/project to CodeSage, on the dev branch, then tell me when it is ready.

## Resources

The bridge also answers `resources/list` and `resources/read`. Reading needs the API key, because no public endpoint exposes the file list.

| URI | MIME type | Listed by `resources/list` | Content |
| --- | --- | --- | --- |
| `codesage://repositories` | `application/json` | Yes (name `Repositories`) | The same object as [`list_repositories`](#list_repositories) |
| `codesage://repositories/{id}/files` | `application/json` | No | The files of one repository |

`{id}` is the numeric ID, 1 to 19 digits. Names are not accepted here. The files resource is readable even when the repository is not `completed`.

Real output for `codesage://repositories/2/files`, with `files` trimmed to the first two entries:

```json title="codesage://repositories/2/files"
{
  "repository": "pmndrs/zustand",
  "total_files": 120,
  "truncated": false,
  "files": [
    {
      "file_path": ".github/DISCUSSION_TEMPLATE/bug-report.yml",
      "language": "yaml",
      "line_count": 17
    },
    {
      "file_path": ".github/FUNDING.yml",
      "language": "yaml",
      "line_count": 16
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `total_files` | Every stored file for the repository |
| `truncated` | `true` when `total_files` is above the 5,000-file cap, so only the first 5,000 by path are listed |
| `files[]` | `file_path`, `language` and `line_count`, ordered by path |

### Resource errors

Resource reads fail as MCP protocol errors, not tool errors. The backend answers `404` and the bridge words it as `Resource or repository not found: <detail>`.

| Detail | Cause |
| --- | --- |
| `Unknown resource '<uri>'` | The URI is neither of the two forms above, or the ID has more than 19 digits |
| `Repository 99 not found` | No repository has that ID. IDs at or above 2^63 are treated the same way |

## Related pages

- [MCP HTTP endpoints](/docs/reference/mcp-endpoints/) for the request and response envelope.
- [Search](/docs/concepts/search/) for how ranking and filters work.
- [Troubleshooting](/docs/troubleshooting/) for symptoms and fixes.
