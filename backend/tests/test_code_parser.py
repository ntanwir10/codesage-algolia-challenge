"""Python entity extraction: every definition survives, with real line ranges"""

import textwrap
import time

from app.services.code_parser import CodeParser

SOURCE = textwrap.dedent(
    '''\
    """Module docstring mentioning import os, which is not an import."""
    import os
    from typing import (
        List,
        Optional,
    )


    def first(a, b: int = 1) -> int:
        return a + b


    def second(*args, key: str, **kwargs):
        return None


    class Widget(Base, Mixin):
        size = 3

        def render(self) -> str:
            def helper():
                return "x"
            return helper()

        async def refresh(self):
            pass


    @decorator
    def last():
        pass
    '''
)


async def parse(source, language="python"):
    return await CodeParser().extract_entities("pkg/module.py", source, language)


def by_name(entities, entity_type):
    return {e.name: e for e in entities if e.entity_type == entity_type}


async def test_every_definition_is_extracted():
    entities = await parse(SOURCE)

    functions = by_name(entities, "function")
    classes = by_name(entities, "class")

    assert set(functions) == {"first", "second", "render", "helper", "refresh", "last"}
    assert set(classes) == {"Widget"}


async def test_line_ranges_cover_whole_definitions():
    entities = await parse(SOURCE)
    functions = by_name(entities, "function")
    widget = by_name(entities, "class")["Widget"]

    assert (functions["first"].line_start, functions["first"].line_end) == (9, 10)
    assert (widget.line_start, widget.line_end) == (17, 26)
    assert (functions["refresh"].line_start, functions["refresh"].line_end) == (25, 26)
    # The def line, not the decorator line, starts the entity
    assert (functions["last"].line_start, functions["last"].line_end) == (30, 31)


async def test_signatures_and_context_are_captured():
    entities = await parse(SOURCE)
    functions = by_name(entities, "function")
    widget = by_name(entities, "class")["Widget"]

    assert functions["first"].parameters == ["a", "b: int"]
    assert functions["first"].return_type == "int"
    assert functions["second"].parameters == ["*args", "key: str", "**kwargs"]
    assert functions["render"].description == "Python method: Widget.render"
    assert functions["helper"].description == "Python function: Widget.render.helper"
    assert functions["first"].content == "def first(a, b: int = 1) -> int:"
    assert widget.parameters == ["Base, Mixin"]


async def test_imports_come_from_code_not_docstrings():
    entities = await parse(SOURCE)
    imports = [e.name for e in entities if e.entity_type == "import"]

    assert imports == ["import os", "from typing import ( List, Optional, )"]


async def test_unparseable_python_falls_back_without_losing_definitions():
    python2_source = textwrap.dedent(
        """\
        import sys

        def a():
            print "a"

        def b():
            print "b"

        class C:
            def m(self):
                print "m"

        def z():
            pass
        """
    )

    entities = await parse(python2_source)
    functions = by_name(entities, "function")
    classes = by_name(entities, "class")

    assert set(functions) == {"a", "b", "m", "z"}
    assert set(classes) == {"C"}
    assert (functions["a"].line_start, functions["a"].line_end) == (3, 4)
    assert (classes["C"].line_start, classes["C"].line_end) == (9, 11)
    assert (functions["z"].line_start, functions["z"].line_end) == (13, 14)


# --------------------------------------------------------------------- bodies / docstrings


async def test_python_body_and_docstring_description():
    source = textwrap.dedent(
        '''\
        class Box:
            """A box.

            More detail.
            """

            def open(self):
                """Open the box.

                Extra.
                """
                return 1


        def plain():
            return 2
        '''
    )
    entities = await parse(source)
    open_method = by_name(entities, "function")["open"]
    assert open_method.description == "Python method: Box.open — Open the box."
    assert by_name(entities, "class")["Box"].description == "Python class: Box — A box."
    assert by_name(entities, "function")["plain"].description == "Python function: plain"
    assert "return 1" in open_method.body
    assert open_method.body.startswith("    def open(self):")
    assert by_name(entities, "function")["plain"].body == "def plain():\n    return 2"


async def test_python_fallback_scanner_fills_body():
    entities = await parse("print 'py2'\ndef f(x):\n    return x\n")
    func = by_name(entities, "function")["f"]
    assert func.body == "def f(x):\n    return x"


async def test_hostile_long_lines_parse_in_linear_time():
    # The old lazy regexes took ~7s on these (quadratic, so ~1MB lines took hours); now ~0s
    started = time.perf_counter()
    entities = await parse("print 'py2'\ndef a(" + ") -> x" * 8000 + "\n")
    await parse("# a" + " " * 16000 + "x\n", "markdown")
    assert time.perf_counter() - started < 1
    assert "a" not in by_name(entities, "function")  # no ':' so not a definition


async def test_python_fallback_return_type_and_nested_parens():
    entities = await parse("print 'py2'\ndef f(a=g()) -> Dict[str, int]:\n    return {}\n")
    func = by_name(entities, "function")["f"]
    assert func.parameters == ["a=g()"]
    assert func.return_type == "Dict[str, int]"


async def test_body_is_capped_in_lines():
    source = "def big():\n" + "".join(f"    x{i} = {i}\n" for i in range(200))
    func = by_name(await parse(source), "function")["big"]
    assert func.line_end == 201
    assert len(func.body.splitlines()) == 60


async def test_body_is_capped_in_characters():
    source = "def big():\n    s = '" + "a" * 5000 + "'\n"
    func = by_name(await parse(source), "function")["big"]
    assert len(func.body) == 2000

    js = "function big() {\n  var s = '" + "a" * 5000 + "';\n}\n"
    entities = await parse(js, "javascript")
    assert len(by_name(entities, "function")["big"].body) == 2000


# --------------------------------------------------------------------------- markdown

MARKDOWN = textwrap.dedent(
    '''\
    # Title

    Intro text.

    ## Install ##

    ```bash
    # this is a comment, not a heading
    pip install thing
    ```

    ### Extras

    More.

    ## Empty

    ## Usage

    Use it.
    '''
)


async def test_markdown_sections_nested_levels_and_ranges():
    entities = await parse(MARKDOWN, "markdown")
    assert {e.entity_type for e in entities} == {"doc_section"}
    sections = {e.name: e for e in entities}

    assert list(sections) == ["Title", "Install", "Extras", "Usage"]
    assert "Empty" not in sections
    assert "this is a comment, not a heading" not in sections

    title = sections["Title"]
    assert (title.line_start, title.line_end) == (1, 20)
    assert title.content == "# Title"
    assert title.description == "Documentation section: Title"

    install = sections["Install"]  # trailing ## stripped; runs through its ### child
    assert (install.line_start, install.line_end) == (5, 15)
    assert "pip install thing" in install.body
    assert install.body.startswith("## Install ##")

    assert (sections["Extras"].line_start, sections["Extras"].line_end) == (12, 15)
    assert (sections["Usage"].line_start, sections["Usage"].line_end) == (18, 20)


# ------------------------------------------------------------ languages with no entities


async def test_markup_languages_produce_nothing():
    samples = {
        "css": "a { color: rgb(0, 0, 0); }\n.btn:hover { margin: calc(1px + 2px); }",
        "scss": "@mixin foo($a) { width: darken($a, 10%); }",
        "html": "<script>init(window)</script>\n<div onclick=\"go(1)\">x</div>",
        "json": '{"scripts": {"test": "jest(1)"}}',
        "yaml": "run: echo $(date)\nother: foo(bar)",
        "xml": "<a b='c(d)'/>",
        "sql": "SELECT count(*) FROM t;",
        "text": "Call us (now) at foo(bar)",
        "unknown-lang": "foo(bar)",
    }
    for language, source in samples.items():
        assert await parse(source, language) == [], language


# -------------------------------------------------------------------------- javascript

JS = textwrap.dedent(
    '''\
    import fs from 'fs';
    import { a, b } from './x';
    export const VERSION = 1;
    export { a, b };
    export default function (x) {
      return x;
    }
    export async function load(a, b) {
      return a;
    }
    const arrow = (a, b) => {
      return a + b;
    };
    export const exported = async x => x;
    var fe = function (z) { return z; };
    class Foo extends Bar {
      constructor(x) { super(x); }
      render() {
        return 1;
      }
    }
    '''
)


async def test_javascript_functions_classes_and_line_ranges():
    entities = await parse(JS, "javascript")
    functions = by_name(entities, "function")

    assert set(functions) == {"default", "load", "arrow", "exported", "fe", "constructor", "render"}
    assert (functions["default"].line_start, functions["default"].line_end) == (5, 7)
    assert (functions["load"].line_start, functions["load"].line_end) == (8, 10)
    assert (functions["arrow"].line_start, functions["arrow"].line_end) == (11, 13)
    assert functions["arrow"].parameters == ["a", "b"]
    assert functions["exported"].parameters == ["x"]
    assert functions["load"].content == "export async function load(a, b) {"
    assert "return a + b;" in functions["arrow"].body

    foo = by_name(entities, "class")["Foo"]
    assert (foo.line_start, foo.line_end) == (16, 21)
    assert foo.parameters == ["Bar"]
    assert functions["render"].description == "JavaScript method: Foo.render"
    assert (functions["render"].line_start, functions["render"].line_end) == (18, 20)
    assert functions["arrow"].description == "JavaScript function: arrow"


async def test_javascript_export_is_not_an_import():
    entities = await parse(JS, "javascript")
    imports = [e for e in entities if e.entity_type == "import"]
    assert [e.name for e in imports] == ["import fs from 'fs';", "import { a, b } from './x';"]


async def test_commonjs_require_is_an_import():
    source = textwrap.dedent("""\
        const fs = require('fs');
        var { join } = require("path"), y = require('x').y;
        require('./polyfill');
        const notRequire = load('x');
        const a = require('a'), f = () => 1;
        function main() { const lazy = require('lazy'); return lazy; }
        """)
    for language in ("javascript", "typescript"):
        entities = await parse(source, language)
        imports = [(e.name, e.line_start) for e in entities if e.entity_type == "import"]
        assert imports == [
            ("const fs = require('fs');", 1),
            ("var { join } = require(\"path\"), y = require('x').y;", 2),
            ("require('./polyfill');", 3),
            ("const lazy = require('lazy');", 6),
        ]
        # A declaration that also defines a function keeps the function
        assert {"f", "main"} <= set(by_name(entities, "function"))


async def test_javascript_has_no_junk_entities():
    entities = await parse(JS, "javascript")
    assert all(e.name != "unknown_function" for e in entities)
    assert {e.entity_type for e in entities} <= {"function", "class", "import"}


async def test_javascript_assignment_and_object_functions():
    source = "lodash.foo = function (a) {\n  return a;\n};\nconst o = { m() {}, k: function () {} };\n"
    functions = by_name(await parse(source, "javascript"), "function")
    assert set(functions) == {"foo", "m", "k"}
    assert (functions["foo"].line_start, functions["foo"].line_end) == (1, 3)


# -------------------------------------------------------------------------- typescript

TS = textwrap.dedent(
    '''\
    import { X } from 'x';
    export interface Shape { area(): number }
    export abstract class Base<T> implements Shape {
      constructor(private x: number) {}
      area(): number {
        return 1;
      }
    }
    export function typed<T>(a: string, b?: number): Promise<T> {
      return null as any;
    }
    const f = async (a: number): Promise<void> => {};
    '''
)


async def test_typescript_type_annotations():
    entities = await parse(TS, "typescript")
    functions = by_name(entities, "function")
    classes = by_name(entities, "class")

    assert set(classes) == {"Shape", "Base"}
    assert (classes["Base"].line_start, classes["Base"].line_end) == (3, 8)
    assert set(functions) == {"constructor", "area", "typed", "f"}
    assert functions["typed"].parameters == ["a: string", "b?: number"]
    assert functions["typed"].return_type == "Promise<T>"
    assert (functions["typed"].line_start, functions["typed"].line_end) == (9, 11)
    assert functions["area"].return_type == "number"
    assert functions["area"].description == "TypeScript method: Base.area"
    assert functions["f"].return_type == "Promise<void>"
    assert [e.name for e in entities if e.entity_type == "import"] == ["import { X } from 'x';"]


async def test_tsx_files_parse_jsx():
    source = "export function App() {\n  return <div>hi</div>;\n}\n"
    entities = await CodeParser().extract_entities("src/App.tsx", source, "typescript")
    assert [(e.name, e.line_end) for e in entities] == [("App", 3)]


# ------------------------------------------------------------------------------ java

JAVA = textwrap.dedent(
    '''\
    package p;
    import java.util.List;
    public class Foo extends Bar {
        public Foo(int x) { this.x = x; }
        public static String run(List<String> a, int b) {
            Helper h = new Helper(b);
            return foo(a);
        }
    }
    '''
)


async def test_java_methods_without_call_sites():
    entities = await parse(JAVA, "java")
    functions = by_name(entities, "function")
    assert set(functions) == {"Foo", "run"}  # no `foo`, `Helper`, `return`
    run = functions["run"]
    assert (run.line_start, run.line_end) == (5, 8)
    assert run.return_type == "String"
    assert run.parameters == ["List<String> a", "int b"]
    assert run.description == "Java method: Foo.run"
    foo = by_name(entities, "class")["Foo"]
    assert (foo.line_start, foo.line_end) == (3, 9)
    assert [e.name for e in entities if e.entity_type == "import"] == ["import java.util.List;"]


# -------------------------------------------------------------------------------- go

GO = textwrap.dedent(
    '''\
    package main
    import (
        "fmt"
        "os"
    )
    type Server struct { a int }
    type ID int
    func New(a int) *Server { return &Server{} }
    func (s *Server) Start(port int) error {
        fmt.Println("x")
        return nil
    }
    '''
)


async def test_go_func_and_method_with_receiver():
    entities = await parse(GO, "go")
    functions = by_name(entities, "function")
    assert set(functions) == {"New", "Start"}
    start = functions["Start"]
    assert start.description == "Go method: Server.Start"
    assert (start.line_start, start.line_end) == (9, 12)
    assert start.return_type == "error"
    assert functions["New"].description == "Go function: New"
    assert set(by_name(entities, "class")) == {"Server"}
    assert [e.name for e in entities if e.entity_type == "import"] == ['"fmt"', '"os"']


# ------------------------------------------------------------------ other tree-sitter languages


async def test_rust():
    source = "use std::io;\nstruct P { x: i32 }\nimpl P {\n    fn new(x: i32) -> Self {\n        P { x }\n    }\n}\npub fn main() {}\n"
    entities = await parse(source, "rust")
    functions = by_name(entities, "function")
    assert functions["new"].description == "Rust method: P.new"
    assert functions["new"].return_type == "Self"
    assert (functions["new"].line_start, functions["new"].line_end) == (4, 6)
    assert functions["main"].description == "Rust function: main"
    assert "P" in by_name(entities, "class")
    assert [e.name for e in entities if e.entity_type == "import"] == ["use std::io;"]


async def test_c():
    source = "#include <stdio.h>\nstruct P { int x; };\nstatic int add(int a, int b) {\n  return a + b;\n}\n"
    entities = await parse(source, "c")
    add = by_name(entities, "function")["add"]
    assert (add.line_start, add.line_end) == (3, 5)
    assert add.parameters == ["int a", "int b"]
    assert add.return_type == "int"
    assert [e.name for e in entities if e.entity_type == "import"] == ["#include <stdio.h>"]
    assert "P" in by_name(entities, "class")


async def test_cpp():
    source = "#include <vector>\nclass W {\npublic:\n  void draw(int a) {\n  }\n};\nvoid W::other(int q) {}\nint top() { return 1; }\n"
    entities = await parse(source, "cpp")
    functions = by_name(entities, "function")
    assert functions["draw"].description == "C++ method: W.draw"
    assert functions["other"].description == "C++ method: W.other"
    assert functions["top"].description == "C++ function: top"
    w = by_name(entities, "class")["W"]
    assert (w.line_start, w.line_end) == (2, 6)


async def test_csharp():
    source = "using System;\nnamespace N {\npublic class Foo : Bar {\n    public int Add(int a, int b) {\n        return a + b;\n    }\n}\n}\n"
    entities = await parse(source, "csharp")
    add = by_name(entities, "function")["Add"]
    assert add.description == "C# method: Foo.Add"
    assert (add.line_start, add.line_end) == (4, 6)
    assert add.return_type == "int"
    assert (by_name(entities, "class")["Foo"].line_end) == 7
    assert [e.name for e in entities if e.entity_type == "import"] == ["using System;"]


async def test_php():
    source = "<?php\nuse Foo\\Bar;\nfunction top($a) { return $a; }\nclass A {\n  public function f(int $x): int {\n    return 1;\n  }\n}\n"
    entities = await parse(source, "php")
    functions = by_name(entities, "function")
    assert functions["f"].description == "PHP method: A.f"
    assert (functions["f"].line_start, functions["f"].line_end) == (5, 7)
    assert functions["top"].description == "PHP function: top"
    assert [e.name for e in entities if e.entity_type == "import"] == ["use Foo\\Bar;"]


async def test_ruby():
    source = "require 'json'\nclass A < B\n  def f(a, b)\n    1\n  end\nend\n"
    entities = await parse(source, "ruby")
    f = by_name(entities, "function")["f"]
    assert f.description == "Ruby method: A.f"
    assert (f.line_start, f.line_end) == (3, 5)
    assert f.parameters == ["a", "b"]
    assert (by_name(entities, "class")["A"].line_end) == 6
    assert [e.name for e in entities if e.entity_type == "import"] == ["require 'json'"]


async def test_syntax_errors_do_not_raise():
    assert isinstance(await parse("function ((( {{{", "javascript"), list)


TERRAFORM = textwrap.dedent(
    '''\
    terraform {
      required_version = ">= 1.5"
    }

    provider "aws" {
      region = var.region
    }

    # Access logs for the API
    // kept in S3
    resource "aws_s3_bucket" "logs" {
      bucket = "logs"
      lifecycle {
        prevent_destroy = true
      }
    }

    data "aws_iam_policy_document" "x" {
      statement {
        actions = ["s3:*"]
      }
    }

    module "network" {
      source = "./network"
    }

    variable "region" {
      default = "us-east-1"
    }

    locals {
      user_data = <<-EOT
        #!/bin/bash
        resource "fake" "block" { }
        }
      EOT
    }

    output "api_url" {
      value = "x"
    }
    '''
)


def test_terraform_top_level_blocks_become_named_entities():
    entities = CodeParser().parse("main.tf", TERRAFORM, "terraform")

    assert [(e.entity_type, e.name, e.line_start, e.line_end) for e in entities] == [
        ("terraform_block", "terraform", 1, 3),
        ("terraform_block", "provider aws", 5, 7),
        ("terraform_block", "resource aws_s3_bucket.logs", 11, 16),
        ("terraform_block", "data aws_iam_policy_document.x", 18, 22),
        ("terraform_block", "module network", 24, 26),
        ("terraform_block", "variable region", 28, 30),
        ("terraform_block", "locals", 32, 38),
        ("terraform_block", "output api_url", 40, 42),
    ]
    logs = entities[2]
    assert logs.description == "Access logs for the API kept in S3"
    assert logs.content == 'resource "aws_s3_bucket" "logs" {'
    assert "prevent_destroy" in logs.body
    assert CodeParser().parse("main.hcl", TERRAFORM, "hcl") == entities
