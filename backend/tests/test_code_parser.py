"""Python entity extraction: every definition survives, with real line ranges"""

import textwrap

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
