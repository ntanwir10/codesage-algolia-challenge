---
title: Supported languages
description: Which files CodeSage indexes, how each language is parsed, how entities are named, what is skipped, and the fields of each Algolia record.
---

CodeSage selects files by extension, parses each one into entities (functions, classes, imports, documentation sections and Terraform blocks), stores the file and its entities in SQLite, and indexes the entities in Algolia. This page lists exactly what that means for each language. The code is in [`github_service.py`](https://github.com/ntanwir10/codesage-algolia-challenge/blob/master/backend/app/services/github_service.py) (file selection), [`code_parser.py`](https://github.com/ntanwir10/codesage-algolia-challenge/blob/master/backend/app/services/code_parser.py) (parsing) and [`algolia_service.py`](https://github.com/ntanwir10/codesage-algolia-challenge/blob/master/backend/app/services/algolia_service.py) (records). For the run as a whole, see [Indexing pipeline](/docs/concepts/indexing-pipeline/).

## Extensions and parsers

A file's language comes from the text after the last `.` in its name, lowercased. A name with no dot, or an extension not in this table, maps to `text`, and `text` files are not indexed.

| Language label | Extensions | Parser | Entities extracted |
| --- | --- | --- | --- |
| `python` | `.py` | Python `ast`, with a [line scanner fallback](#python-fallback-scanner) | functions, methods, classes, imports |
| `javascript` | `.js`, `.jsx` | tree-sitter `javascript` | functions, methods, classes, imports |
| `typescript` | `.ts`, `.tsx` | tree-sitter `typescript` (`tsx` for `.tsx`) | functions, methods, classes, interfaces, imports |
| `java` | `.java` | tree-sitter `java` | methods, constructors, classes, interfaces, enums, records, annotations, imports |
| `go` | `.go` | tree-sitter `go` | functions, methods, structs and interfaces, imports |
| `rust` | `.rs` | tree-sitter `rust` | functions, structs, enums, traits, impl blocks, unions, imports |
| `cpp` | `.cpp` | tree-sitter `cpp` | functions, classes, structs, unions, includes |
| `c` | `.c` | tree-sitter `c` | functions, structs, unions, includes |
| `csharp` | `.cs` | tree-sitter `csharp` | methods, constructors, local functions, classes, interfaces, structs, enums, records, usings |
| `php` | `.php` | tree-sitter `php` | functions, methods, classes, interfaces, traits, use declarations |
| `ruby` | `.rb` | tree-sitter `ruby` | methods, singleton methods, classes, modules, `require`/`require_relative`/`load` calls |
| `markdown` | `.md` | Heading scanner | one `doc_section` per heading |
| `terraform` | `.tf`, `.tfvars` | tree-sitter `hcl` | one `terraform_block` per top-level block |
| `hcl` | `.hcl` | tree-sitter `hcl` | one `terraform_block` per top-level block |
| `html` | `.html` | None | None |
| `css` | `.css` | None | None |
| `scss` | `.scss` | None | None |
| `sql` | `.sql` | None | None |
| `json` | `.json` | None | None |
| `yaml` | `.yaml`, `.yml` | None | None |
| `xml` | `.xml` | None | None |

Other extensions are not indexed at all. Examples: `.h`, `.hpp`, `.cc`, `.mjs`, `.cjs`, `.kt`, `.swift`, `.sh`, `.toml`, `.mdx`, and files such as `Makefile` or `Dockerfile`.

:::note
The README lists only CSS, HTML, JSON, YAML and XML as stored-without-entities. The code also maps `.scss` and `.sql` to a language without a parser, so those two behave the same way.
:::

### Files stored without entities

These files are stored and readable through [`get_file`](/docs/reference/mcp-tools/#get_file) and found by [`find_patterns`](/docs/reference/mcp-tools/#find_patterns), but they produce no Algolia records and so never appear in [`search_code`](/docs/reference/mcp-tools/#search_code) or [`list_definitions`](/docs/reference/mcp-tools/#list_definitions):

- Files in `html`, `css`, `scss`, `sql`, `json`, `yaml` and `xml`.
- Files that are empty or contain only whitespace.
- Files whose parser raised an error. The file is still stored, and the run's `error_message` ends with `N files could not be parsed` under `Partially indexed:`.
- Source files that simply define nothing, such as a Python file with only constants.

If no file in the whole run produces an entity, the run fails with `No code entities were indexed from N files (M failed to process)`.

## Entity types

| `entity_type` | Produced by |
| --- | --- |
| `function` | Functions and methods in all programming languages. A method is still `function`; its description says "method" |
| `class` | Classes, and in some languages interfaces, structs, enums, traits, modules and similar |
| `import` | Import, use, include and require statements |
| `doc_section` | Markdown headings |
| `terraform_block` | Top-level Terraform and HCL blocks |

## How entities are named

Every entity has a `name` and a `description`. The name is what you search by and what `list_definitions` filters on. The description carries the qualified form.

### Functions and methods

- **Name.** The bare name, for example `get_repository_files`. A method is not prefixed with its class.
- **Description.** `<Language> function: <qualified>` or `<Language> method: <qualified>`. The qualified name joins the enclosing scopes with dots, for example `Python method: GitSource.get_repository_files`.
- **Python.** A function defined in a class body is a method. A function nested in another function is a function with the scope in its name, such as `Python function: outer.inner`. If a docstring exists, its first line is appended after an em dash.
- **Go.** A method is named by its method name, with the receiver type as the owner: `Go method: Server.Start`.
- **C and C++.** A definition written `Foo::bar` has the name `bar` and the owner `Foo`.
- **JavaScript and TypeScript.** Beyond declarations, a function assigned to a name is recorded under that name. That covers `const f = () => {}`, `const f = function () {}`, object properties (`{ run: () => {} }`), class fields, assignments such as `obj.run = function () {}`, and `export default () => {}` (named `default`). Such functions inside a class body count as methods.
- **Parameters.** Python parameters are written `name` or `name: annotation`, with `*args` and `**kwargs` prefixes. Tree-sitter languages store each parameter's source text with whitespace collapsed.
- **Return type.** From the annotation in Python. For tree-sitter languages it is read from the `return_type` field (Java and C-family: `type`; Go: `result`; C#: `returns` or `type`). JavaScript and Ruby store none.

### Classes and similar

- **Name.** The declared name. A Rust `impl` block is named after the type it implements, so a struct and its `impl` appear as two `class` entities with the same name. A Go `type` becomes a class only when it is a struct or interface.
- **Description.** `<Language> class: <Name>` for every class-like kind, including interfaces, structs, enums, traits and modules. Python adds the first docstring line.
- **Parents.** Base classes, interfaces and traits are stored in the entity's parameters list. Python stores its bases as one comma-joined string.
- **C and C++.** A `class`, `struct` or `union` is recorded only when it has a body, so forward declarations are skipped.

### Imports

- **Name.** The statement with whitespace collapsed, for example `from fastapi import FastAPI, Request`. For C and C++ it is written `#include <stdio.h>`.
- **Description.** `Import statement: <statement>` for Python, and `<Language> import: <statement>` for the others.
- **Python.** Every `import` and `from ... import` is recorded, at any depth, so imports inside functions count.
- **JavaScript and TypeScript.** `import` statements and CommonJS `const x = require("m")` declarations, plus bare `require("m");` statements.
- **Ruby.** Calls to `require`, `require_relative` and `load` without a receiver.
- **Body.** Imports have no body, so their searchable content is just the statement.

### Markdown

- Only ATX headings (`#` to `######`, up to three leading spaces, a space after the hashes) count. Setext headings (underlined with `===` or `---`) are ignored.
- Headings inside fenced code blocks (backticks or tildes) are ignored.
- A closing run of `#` after a space is stripped. A heading with no text is skipped.
- The name is the heading text. The description is `Documentation section: <text>`.
- A section runs from its heading to the line before the next heading of the same or a higher level, so a section includes its subsections. Two nested sections can overlap.
- A section whose lines after the heading are all blank is skipped.

### Terraform and HCL

Only top-level blocks become entities. Top-level attributes (as in a `.tfvars` file) produce nothing.

| Block | Name |
| --- | --- |
| `resource "aws_s3_bucket" "logs"` | `resource aws_s3_bucket.logs` |
| `data "aws_ami" "base"` | `data aws_ami.base` |
| `module "network"` | `module network` |
| `variable "region"` | `variable region` |
| `output "api_url"` | `output api_url` |
| `provider "aws"` | `provider aws` |
| `locals` | `locals` |

Labels of `resource` and `data` blocks are joined with a dot. Labels of every other block are joined with spaces. The description is the run of `#`, `//` or `/* */` comments directly above the block, joined into one line. With no comment, it is `Terraform <name>`.

### Python fallback scanner

When `ast` cannot parse a Python file (a `SyntaxError`, `ValueError` or `RecursionError`, as with Python 2 code or templates), a line scanner takes over. It is less precise:

- It matches `import ` and `from ` lines, `def` lines and `class` lines. A `def` must have its parameter list and colon on one line, so a signature split over several lines is missed.
- Nesting is tracked by indentation. A definition ends at the last code line before the indentation returns to its level.
- Descriptions are plain, `Python function: name` and `Python class: name`, with no scope and no docstring.
- Bodies are cut the same way as for `ast`.

## What is skipped

### Denied directories

A file is dropped when any parent directory has one of these names, at any depth:

`node_modules`, `dist`, `build`, `vendor`, `third_party`, `.git`, `__pycache__`, `.next`, `coverage`

### Denied file patterns

Matched against the lowercased file name:

| Pattern | Covers |
| --- | --- |
| `*.min.js`, `*.min.css`, `*.bundle.js` | Minified and bundled output |
| `*.map` | Source maps |
| `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`, `cargo.lock` | Lockfiles. `Cargo.lock` matches because the match ignores case |

Other lockfiles are not on the list but are not indexed anyway, because their extensions (`.lock`, `.sum`) are not supported.

### Size and count limits

| Limit | Value | Effect |
| --- | --- | --- |
| Largest file | under 1 MB | A file of 1 MB or more is dropped |
| Files per run | 1,000 | The rest are skipped |
| Bytes per run | 100 MB | The rest are skipped |
| Selection order | By path, ascending | The first files by path are kept |
| Empty or binary files | Skipped when downloaded | A file containing a NUL byte is binary |
| Symlinks | Never listed or followed | On GitHub, tree entries with mode `120000` are ignored. On other hosts, a clone keeps symlinks as real links and the tree walk skips them |

Files over the file-count or byte limit are counted, and a completed run says so: `Partially indexed: N files over the 1000-file or 100 MB limit were skipped`. A listing that GitHub marks truncated is walked through the contents API, one request per directory, up to 300 directories. See [Limitations](/docs/limitations/).

Text is decoded as UTF-8 (a leading byte order mark is removed), and invalid bytes are replaced.

### Primary language

After a run, the repository's `language` is the most common label among its files, ignoring `text`, `markdown`, `json`, `yaml`, `xml`, `css`, `scss` and `html`. `sql`, `terraform` and `hcl` do count.

## Algolia record fields

Each entity becomes one Algolia record. The index name is `ALGOLIA_INDEX_NAME`.

| Field | Type | Content |
| --- | --- | --- |
| `objectID` | string | `<repository_id>_<sha1 of "path:type:name:line_start">`. Stable, so re-indexing overwrites instead of duplicating |
| `repository_id` | integer | The owning repository |
| `file_path` | string | Path inside the repository |
| `entity_type` | string | `function`, `class`, `import`, `doc_section` or `terraform_block` |
| `entity_name` | string | Name, cut at 500 characters |
| `description` | string | Description, cut at 500 characters |
| `parameters` | array of strings | Parameters, or base classes for a class. Empty array if none |
| `return_type` | string or null | Cut at 500 characters |
| `line_start`, `line_end` | integer | 1-based inclusive range |
| `language` | string | The file's language label |
| `signature` | string | The definition line, cut at 500 characters |
| `content` | string | Signature, then the body. If the body already starts with the signature, only the body |
| `rank_weight` | integer | See below |
| `parameter_count` | integer | Number of parameters |
| `lines_of_code` | integer | `line_end - line_start + 1`, at least 1 |

Limits on the stored text:

- The parser keeps at most 60 lines and 2,000 characters of an entity's body.
- The record keeps at most 2,000 characters of body.
- A whole record is trimmed to 9,000 bytes of JSON, `content` first and then `parameters`, because Algolia rejects a batch if one record is over 10 KB.
- Records are sent 1,000 at a time.

### `rank_weight`

On a relevance tie, a higher weight ranks first (`customRanking: desc(rank_weight)`).

| `entity_type` | `rank_weight` |
| --- | --- |
| `class` | 3 |
| `function` | 2 |
| `terraform_block` | 2 |
| `doc_section` | 1 |
| `import` | 0 |

### Index settings

| Setting | Value |
| --- | --- |
| `searchableAttributes` | `entity_name`, `description`, `content`, `parameters`, `file_path` (in this order) |
| `attributesForFaceting` | `filterOnly(repository_id)`, `entity_type`, `language`, `file_path` |
| `customRanking` | `desc(rank_weight)` |
| `highlightPreTag`, `highlightPostTag` | `<mark>`, `</mark>` |
| `hitsPerPage` | 20 |
| `maxValuesPerFacet` | 100 |

The backend applies these once per process, and only when they differ from the live settings. See [Search](/docs/concepts/search/) for how queries use them.

## Related pages

- [MCP tools](/docs/reference/mcp-tools/) for what each tool returns from these records.
- [Data model](/docs/concepts/data-model/) for the SQLite tables.
- [Limitations](/docs/limitations/) for the known gaps.
