import ast
import asyncio
import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

BODY_MAX_LINES = 60
BODY_MAX_CHARS = 2000


@dataclass
class ParsedCodeEntity:
    """Represents a code entity (function, class, import, doc section) extracted from a file"""
    entity_type: str  # "function", "class", "import", "doc_section", "terraform_block"
    name: str
    description: str
    line_start: int
    line_end: int
    parameters: list[str] = None
    return_type: str = None
    content: str = None  # signature or definition line
    body: str | None = None  # source text, capped at BODY_MAX_LINES / BODY_MAX_CHARS


def make_body(lines: list[str], line_start: int, line_end: int) -> str:
    """Source text of a 1-based inclusive line range, capped in lines and characters"""
    end = min(line_end, line_start - 1 + BODY_MAX_LINES)
    return "\n".join(lines[line_start - 1:end])[:BODY_MAX_CHARS]


@dataclass(frozen=True)
class LanguageSpec:
    """Tree-sitter node types that matter for one language"""
    label: str
    grammar: str
    functions: frozenset
    classes: frozenset
    imports: frozenset
    # Node types that are always methods when their parent scope is a class
    methods: frozenset = frozenset()
    return_fields: tuple = ("return_type",)


def _spec(label, grammar, functions, classes, imports, methods=(), return_fields=("return_type",)):
    return LanguageSpec(label, grammar, frozenset(functions), frozenset(classes),
                        frozenset(imports), frozenset(methods), tuple(return_fields))


_JS_FUNCTIONS = ("function_declaration", "generator_function_declaration", "method_definition")
_JS_CLASSES = ("class_declaration",)

LANGUAGE_SPECS = {
    "javascript": _spec("JavaScript", "javascript", _JS_FUNCTIONS, _JS_CLASSES, ("import_statement",),
                        return_fields=()),
    "typescript": _spec("TypeScript", "typescript", _JS_FUNCTIONS + ("function_signature",),
                        _JS_CLASSES + ("abstract_class_declaration", "interface_declaration",
                                       "type_alias_declaration", "enum_declaration"),
                        ("import_statement",)),
    "java": _spec("Java", "java", ("method_declaration", "constructor_declaration"),
                  ("class_declaration", "interface_declaration", "enum_declaration",
                   "record_declaration", "annotation_type_declaration"),
                  ("import_declaration",), return_fields=("type",)),
    "go": _spec("Go", "go", ("function_declaration", "method_declaration"),
                ("type_spec",), ("import_spec",), return_fields=("result",)),
    "rust": _spec("Rust", "rust", ("function_item", "function_signature_item"),
                  ("struct_item", "enum_item", "trait_item", "impl_item", "union_item"),
                  ("use_declaration",)),
    "cpp": _spec("C++", "cpp", ("function_definition",),
                 ("class_specifier", "struct_specifier", "union_specifier"),
                 ("preproc_include",), return_fields=("type",)),
    "c": _spec("C", "c", ("function_definition",), ("struct_specifier", "union_specifier"),
               ("preproc_include",), return_fields=("type",)),
    "csharp": _spec("C#", "csharp",
                    ("method_declaration", "constructor_declaration", "local_function_statement"),
                    ("class_declaration", "interface_declaration", "struct_declaration",
                     "enum_declaration", "record_declaration"),
                    ("using_directive",), return_fields=("returns", "type")),
    "php": _spec("PHP", "php", ("function_definition", "method_declaration"),
                 ("class_declaration", "interface_declaration", "trait_declaration"),
                 ("namespace_use_declaration",)),
    "ruby": _spec("Ruby", "ruby", ("method", "singleton_method"), ("class", "module"), (),
                  return_fields=()),
}

_ANON_FUNCTIONS = frozenset({"arrow_function", "function_expression", "function", "generator_function"})
# Expressions around a function that leave it a function: (fn), fn as T, fn satisfies T, fn!, <T>fn
_TRANSPARENT_WRAPPERS = frozenset({"parenthesized_expression", "as_expression", "satisfies_expression",
                                   "non_null_expression", "type_assertion"})
# How descriptions name class-like definitions that aren't classes
_CLASS_KIND_LABELS = {"interface_declaration": "interface", "type_alias_declaration": "type",
                      "enum_declaration": "enum"}
_WRAPPERS = frozenset({"export_statement", "lexical_declaration", "variable_declaration"})
_DECLARATOR_WRAPPERS = frozenset({"pointer_declarator", "reference_declarator", "parenthesized_declarator",
                                  "function_declarator", "array_declarator"})
_RUBY_REQUIRES = frozenset({"require", "require_relative", "load"})


class CodeParser:
    """
    Parse code files to extract entities for Algolia indexing.
    Python uses ast, Markdown a heading scanner, and everything else tree-sitter.
    """

    def __init__(self):
        self.parsers = {
            "python": self._parse_python,
            "markdown": self._parse_markdown,
            "terraform": self._parse_hcl,
            "hcl": self._parse_hcl,
        }
        self._ts_parsers = {}

    async def extract_entities(self, file_path: str, content: str, language: str) -> list[ParsedCodeEntity]:
        """
        Extract code entities from file content.
        Returns list of functions, classes, imports, doc sections for Algolia indexing.

        Parsing is CPU-bound, so it runs in a worker thread to keep the event
        loop (API, WebSocket, MCP) responsive while a repository is indexed.
        """
        return await asyncio.to_thread(self.parse, file_path, content, language)

    def parse(self, file_path: str, content: str, language: str) -> list[ParsedCodeEntity]:
        """Synchronous entity extraction; [] for unsupported input. Raises if parsing fails,
        so the caller can report the file instead of counting it as cleanly processed."""
        if not content or not content.strip():
            return []

        if language in self.parsers:
            entities = self.parsers[language](content, file_path)
        elif language in LANGUAGE_SPECS:
            entities = self._parse_tree_sitter(content, file_path, language)
        else:
            # No entities for config/markup languages (css, html, json, yaml, ...) or unknown ones
            entities = []

        logger.debug(
            "Extracted code entities",
            file_path=file_path,
            language=language,
            entities_count=len(entities)
        )

        return entities

    def _parse_python(self, content: str, file_path: str) -> list[ParsedCodeEntity]:
        """Parse Python code for functions, classes, imports"""
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError, RecursionError):
            # Python 2 sources, templates, pathologically nested code, etc.
            return self._parse_python_lines(content)

        lines = content.split('\n')
        entities = []

        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                segment = ast.get_source_segment(content, node) or lines[node.lineno - 1]
                statement = " ".join(segment.split())
                entities.append(ParsedCodeEntity(
                    entity_type="import",
                    name=statement,
                    description=f"Import statement: {statement}",
                    line_start=node.lineno,
                    line_end=node.end_lineno,
                    content=statement
                ))

        # Extract functions, methods and classes at any nesting depth
        self._collect_python_definitions(tree, lines, "", False, entities)
        return entities

    def _collect_python_definitions(
        self, parent: ast.AST, lines: list[str], scope: str, in_class: bool,
        entities: list[ParsedCodeEntity]
    ):
        """Walk definitions in source order, recording each one with its full line range"""
        for node in ast.iter_child_nodes(parent):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified_name = f"{scope}{node.name}"
                kind = "method" if in_class else "function"
                entities.append(ParsedCodeEntity(
                    entity_type="function",
                    name=node.name,
                    description=self._python_description(node, f"Python {kind}: {qualified_name}"),
                    line_start=node.lineno,
                    line_end=node.end_lineno,
                    parameters=self._python_parameters(node.args),
                    return_type=ast.unparse(node.returns) if node.returns else None,
                    content=lines[node.lineno - 1],
                    body=make_body(lines, node.lineno, node.end_lineno)
                ))
                self._collect_python_definitions(node, lines, f"{qualified_name}.", False, entities)

            elif isinstance(node, ast.ClassDef):
                qualified_name = f"{scope}{node.name}"
                inheritance = ", ".join(ast.unparse(base) for base in node.bases)
                entities.append(ParsedCodeEntity(
                    entity_type="class",
                    name=node.name,
                    description=self._python_description(node, f"Python class: {qualified_name}"),
                    line_start=node.lineno,
                    line_end=node.end_lineno,
                    parameters=[inheritance] if inheritance else None,
                    content=lines[node.lineno - 1],
                    body=make_body(lines, node.lineno, node.end_lineno)
                ))
                self._collect_python_definitions(node, lines, f"{qualified_name}.", True, entities)

            elif not isinstance(node, ast.expr):
                # Definitions nested in if/try/with blocks keep the enclosing scope.
                # Expressions can't contain def/class, so skipping them avoids deep recursion.
                self._collect_python_definitions(node, lines, scope, in_class, entities)

    @staticmethod
    def _python_description(node: ast.AST, base: str) -> str:
        """Append the first docstring line, if any"""
        docstring = ast.get_docstring(node)
        if docstring and docstring.strip():
            return f"{base} \u2014 {docstring.strip().splitlines()[0].strip()}"
        return base

    @staticmethod
    def _python_parameters(args: ast.arguments) -> list[str]:
        """Render parameters as 'name' or 'name: annotation', with * and ** prefixes"""
        def render(arg: ast.arg, prefix: str = "") -> str:
            if arg.annotation:
                return f"{prefix}{arg.arg}: {ast.unparse(arg.annotation)}"
            return f"{prefix}{arg.arg}"

        parameters = [render(arg) for arg in args.posonlyargs + args.args]
        if args.vararg:
            parameters.append(render(args.vararg, "*"))
        parameters.extend(render(arg) for arg in args.kwonlyargs)
        if args.kwarg:
            parameters.append(render(args.kwarg, "**"))
        return parameters

    def _parse_python_lines(self, content: str) -> list[ParsedCodeEntity]:
        """Line-based fallback for Python that ast can't parse.

        Keeps a stack of open definitions so every def/class is recorded, and
        closes each one at the last code line before indentation returns to its level.
        """
        entities = []
        open_definitions = []  # (indent, entity) whose body hasn't ended yet
        last_code_line = 0

        for line_number, line in enumerate(content.split('\n'), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            indent = len(line) - len(line.lstrip())
            while open_definitions and indent <= open_definitions[-1][0]:
                open_definitions.pop()[1].line_end = last_code_line

            entity = None
            if stripped.startswith(('import ', 'from ')):
                entities.append(ParsedCodeEntity(
                    entity_type="import",
                    name=stripped,
                    description=f"Import statement: {stripped}",
                    line_start=line_number,
                    line_end=line_number,
                    content=stripped
                ))
            # A match ends at a ':', so cutting after the last one changes nothing but keeps
            # the lazy groups from rescanning the line for every ')' (quadratic on hostile input)
            elif match := re.match(
                r'(?:async\s+)?def\s+(\w+)\s*\((.*?)\)(?:\s*->\s*(.+?))?:',
                stripped[:stripped.rfind(':') + 1],
            ):
                func_name, params, return_type = match.groups()
                entity = ParsedCodeEntity(
                    entity_type="function",
                    name=func_name,
                    description=f"Python function: {func_name}",
                    line_start=line_number,
                    line_end=line_number,
                    parameters=[p.strip() for p in params.split(',') if p.strip()],
                    return_type=return_type.strip() if return_type else None,
                    content=line
                )
            elif match := re.match(r'class\s+(\w+)(?:\((.*?)\))?:', stripped):
                class_name, inheritance = match.groups()
                entity = ParsedCodeEntity(
                    entity_type="class",
                    name=class_name,
                    description=f"Python class: {class_name}",
                    line_start=line_number,
                    line_end=line_number,
                    parameters=[inheritance] if inheritance else None,
                    content=line
                )

            if entity:
                entities.append(entity)
                open_definitions.append((indent, entity))
            last_code_line = line_number

        # Definitions still open run to the end of the file
        for _, entity in open_definitions:
            entity.line_end = last_code_line

        source_lines = content.split('\n')
        for entity in entities:
            if entity.entity_type != "import":
                entity.body = make_body(source_lines, entity.line_start, entity.line_end)

        return entities

    # ------------------------------------------------------------------ Markdown

    # The optional closing #s are stripped in code: a lazy regex for them is quadratic on long blank runs
    _HEADING = re.compile(r' {0,3}(#{1,6})[ \t]+(.*)')
    _FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})')

    def _parse_markdown(self, content: str, file_path: str) -> list[ParsedCodeEntity]:
        """Each ATX heading becomes a doc_section running to the next heading of the same or higher level"""
        lines = content.splitlines()
        headings = []  # (line_number, level, text)
        fence = None
        for number, line in enumerate(lines, start=1):
            fence_match = self._FENCE.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if fence is None:
                    fence = marker
                elif marker[0] == fence[0] and len(marker) >= len(fence) and not line.strip().strip(marker[0]):
                    fence = None
                continue
            if fence is not None:
                continue
            heading = self._HEADING.match(line)
            if heading is None:
                continue
            text = heading.group(2).rstrip(' \t')
            without_closing = text.rstrip('#')
            if not without_closing or without_closing[-1] in ' \t':  # closing #s need a space before them
                text = without_closing
            if text.strip('# \t'):
                headings.append((number, len(heading.group(1)), text.strip()))

        entities = []
        for index, (number, level, text) in enumerate(headings):
            line_end = len(lines)
            for next_number, next_level, _ in headings[index + 1:]:
                if next_level <= level:
                    line_end = next_number - 1
                    break
            if not any(line.strip() for line in lines[number:line_end]):
                continue
            entities.append(ParsedCodeEntity(
                entity_type="doc_section",
                name=text,
                description=f"Documentation section: {text}",
                line_start=number,
                line_end=line_end,
                content=lines[number - 1],
                body=make_body(lines, number, line_end),
            ))
        return entities

    def _parse_hcl(self, content: str, file_path: str) -> list[ParsedCodeEntity]:
        """Each top-level Terraform/HCL block becomes a terraform_block, named from its type and labels"""
        lines = content.splitlines()
        root = self._get_ts_parser("hcl").parse(content.encode()).root_node
        entities = []
        # config_file > body > block; a leading # or // comment run is the docstring
        body = next((c for c in root.children if c.type == "body"), None)
        # tree-sitter puts comments before the first block at the root, beside body
        comments: list = []
        for node in [c for c in root.children if c.type == "comment"] + list(body.children if body else []):
            if node.type == "comment":
                if comments and node.start_point[0] != comments[-1].end_point[0] + 1:
                    comments = []
                comments.append(node)
                continue
            if node.type == "block":
                kind = self._text(node.children[0])
                labels = [
                    self._text(c).strip('"') for c in node.children[1:]
                    if c.type in ("string_lit", "identifier")
                ]
                name = kind
                if labels:
                    name += " " + ".".join(labels) if kind in ("resource", "data") else " " + " ".join(labels)
                line_start, line_end = node.start_point[0] + 1, node.end_point[0] + 1
                doc = ""
                if comments and comments[-1].end_point[0] + 1 == node.start_point[0]:
                    doc = " ".join(
                        line.strip().lstrip("#/* \t").removesuffix("*/").rstrip()
                        for c in comments for line in self._text(c).splitlines()
                    ).strip()
                entities.append(ParsedCodeEntity(
                    entity_type="terraform_block",
                    name=name,
                    description=doc or f"Terraform {name}",
                    line_start=line_start,
                    line_end=line_end,
                    content=lines[line_start - 1],
                    body=make_body(lines, line_start, line_end),
                ))
            comments = []
        return entities

    # --------------------------------------------------------------- tree-sitter

    def _get_ts_parser(self, grammar: str):
        if grammar not in self._ts_parsers:
            from tree_sitter_language_pack import get_parser
            self._ts_parsers[grammar] = get_parser(grammar)
        return self._ts_parsers[grammar]

    def _parse_tree_sitter(self, content: str, file_path: str, language: str) -> list[ParsedCodeEntity]:
        """One generic walk over the syntax tree, driven by LANGUAGE_SPECS"""
        spec = LANGUAGE_SPECS[language]
        grammar = spec.grammar
        if language == "typescript" and file_path.lower().endswith(".tsx"):
            grammar = "tsx"
        tree = self._get_ts_parser(grammar).parse(content.encode("utf-8"))
        lines = content.split("\n")
        entities = []
        claimed = set()  # anonymous function nodes already emitted under another name

        # Iterative DFS keeps source order and avoids Python recursion limits on deep trees.
        # Stack items: (node, owner scope string, directly inside a class body)
        stack = [(tree.root_node, "", False)]
        while stack:
            node, scope, in_class = stack.pop()
            kind = node.type
            child_scope, child_in_class = scope, in_class

            if (kind in spec.imports
                    or (language == "ruby" and kind == "call" and self._is_ruby_require(node))
                    or (language in ("javascript", "typescript") and self._is_js_require(node))):
                self._emit_import(spec, node, lines, entities)
                continue

            if kind in spec.classes:
                name = self._class_name(language, node)
                if name and not (language in ("c", "cpp") and node.child_by_field_name("body") is None):
                    if language != "go" or self._is_go_struct_like(node):
                        self._emit_class(spec, node, name, lines, entities)
                        child_scope, child_in_class = f"{scope}{name}.", True
            elif kind in spec.functions:
                name, owner = self._function_name(language, node)
                if name:
                    is_method = in_class or bool(owner)
                    if owner:
                        qualified = f"{owner}.{name}"
                    else:
                        qualified = f"{scope}{name}"
                    self._emit_function(spec, node, node, name, qualified, is_method, lines, entities)
                    child_scope, child_in_class = f"{qualified}.", False
            elif language in ("javascript", "typescript"):
                handled = self._js_named_function(spec, node, scope, lines, entities, claimed)
                if handled:
                    child_scope, child_in_class = handled, False

            for child in reversed(node.children):
                if child.is_named:
                    stack.append((child, child_scope, child_in_class))
        return entities

    @staticmethod
    def _text(node) -> str:
        return node.text.decode("utf-8", errors="replace") if node is not None else ""

    @staticmethod
    def _line_range(node) -> tuple[int, int]:
        """1-based inclusive lines; a node ending at column 0 (trailing newline) stops on the previous line"""
        start, end = node.start_point[0] + 1, node.end_point[0] + 1
        if node.end_point[1] == 0 and end > start:
            end -= 1
        return start, end

    def _outer(self, node):
        """Widen a node's range to include wrappers such as `export` and `const x =`"""
        outer = node
        while outer.parent is not None and outer.parent.type in _WRAPPERS:
            outer = outer.parent
        return outer

    def _emit_import(self, spec, node, lines, entities):
        statement = " ".join(self._text(node).split())
        if spec.grammar in ("c", "cpp"):
            statement = statement.removeprefix("#include").strip()
            label_text = f"#include {statement}"
        else:
            label_text = statement
        entities.append(ParsedCodeEntity(
            entity_type="import",
            name=label_text,
            description=f"{spec.label} import: {label_text}",
            line_start=self._line_range(node)[0],
            line_end=self._line_range(node)[1],
            content=label_text,
        ))

    def _emit_class(self, spec, node, name, lines, entities):
        outer = self._outer(node)
        start, end = self._line_range(outer)
        parents = self._class_parents(node)
        entities.append(ParsedCodeEntity(
            entity_type="class",
            name=name,
            description=f"{spec.label} {_CLASS_KIND_LABELS.get(node.type, 'class')}: {name}",
            line_start=start,
            line_end=end,
            parameters=parents or None,
            content=lines[start - 1].strip(),
            body=make_body(lines, start, end),
        ))

    def _emit_function(self, spec, node, range_node, name, qualified, is_method, lines, entities,
                       parameters=None, return_type=None):
        outer = self._outer(range_node)
        start, end = self._line_range(outer)
        if parameters is None:
            parameters = self._parameters(spec, node)
        if return_type is None:
            return_type = self._return_type(spec, node)
        kind = "method" if is_method else "function"
        entities.append(ParsedCodeEntity(
            entity_type="function",
            name=name,
            description=f"{spec.label} {kind}: {qualified}",
            line_start=start,
            line_end=end,
            parameters=parameters,
            return_type=return_type,
            content=lines[start - 1].strip(),
            body=make_body(lines, start, end),
        ))

    def _parameters(self, spec, node) -> list[str]:
        params = node.child_by_field_name("parameters")
        if params is None and spec.grammar in ("c", "cpp"):
            declarator = self._find_function_declarator(node)
            params = declarator.child_by_field_name("parameters") if declarator is not None else None
        if params is None:
            single = node.child_by_field_name("parameter")  # x => x
            return [self._text(single)] if single is not None else []
        return [" ".join(self._text(c).split()) for c in params.named_children if c.type != "comment"]

    def _return_type(self, spec, node) -> str | None:
        for field in spec.return_fields:
            found = node.child_by_field_name(field)
            if found is not None:
                text = " ".join(self._text(found).split()).lstrip(":-> ").strip()
                return text or None
        return None

    def _find_function_declarator(self, node):
        declarator = node.child_by_field_name("declarator")
        while declarator is not None and declarator.type in _DECLARATOR_WRAPPERS:
            if declarator.type == "function_declarator":
                return declarator
            declarator = declarator.child_by_field_name("declarator")
        return None

    def _function_name(self, language, node) -> tuple[str | None, str | None]:
        """Return (name, explicit owner) for a function-like node"""
        if language in ("c", "cpp"):
            declarator = self._find_function_declarator(node)
            if declarator is None:
                return None, None
            ident = declarator.child_by_field_name("declarator")
            text = self._text(ident)
            if "::" in text:
                owner, _, name = text.rpartition("::")
                return name, owner
            return text or None, None
        name = self._text(node.child_by_field_name("name")) or None
        if language == "go" and node.type == "method_declaration":
            receiver = node.child_by_field_name("receiver")
            owner = self._first_descendant(receiver, "type_identifier") if receiver is not None else None
            return name, self._text(owner) or None
        return name, None

    def _class_name(self, language, node) -> str | None:
        if language == "rust" and node.type == "impl_item":
            target = node.child_by_field_name("type")
            return re.split(r'[<\s]', self._text(target), maxsplit=1)[0] or None
        return self._text(node.child_by_field_name("name")) or None

    def _class_parents(self, node) -> list[str]:
        parents = []
        for field in ("superclass", "superclasses", "interfaces", "trait"):
            found = node.child_by_field_name(field)
            if found is not None:
                parents.append(" ".join(self._text(found).split()))
        for child in node.named_children:
            if child.type in ("class_heritage", "extends_clause", "base_class_clause", "base_list",
                              "superclass", "super_interfaces", "extends_interfaces"):
                parents.append(" ".join(self._text(child).split()))
        cleaned = [re.sub(r'^(?:extends|implements|[:<])\s*', '', p).strip() for p in parents]
        return [p for p in dict.fromkeys(cleaned) if p]

    @staticmethod
    def _is_go_struct_like(node) -> bool:
        type_node = node.child_by_field_name("type")
        return type_node is not None and type_node.type in ("struct_type", "interface_type")

    @staticmethod
    def _first_descendant(node, node_type):
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type == node_type:
                return current
            stack.extend(reversed(current.children))
        return None

    def _is_ruby_require(self, node) -> bool:
        method = node.child_by_field_name("method")
        return (method is not None and self._text(method) in _RUBY_REQUIRES
                and node.child_by_field_name("receiver") is None)

    def _is_js_require(self, node) -> bool:
        """CommonJS `const x = require('m')` declarations and bare `require('m');` statements"""
        if node.type in ("lexical_declaration", "variable_declaration"):
            values = [d.child_by_field_name("value") for d in node.named_children
                      if d.type == "variable_declarator"]
            # A declaration that also defines a function is left to the function walk
            return bool(values) and all(self._is_require_call(v) for v in values)
        if node.type == "expression_statement":
            return any(self._is_require_call(child) for child in node.named_children)
        return False

    def _is_require_call(self, node) -> bool:
        while node is not None and node.type == "member_expression":  # require('m').prop
            node = node.child_by_field_name("object")
        return (node is not None and node.type == "call_expression"
                and self._text(node.child_by_field_name("function")) == "require")

    def _js_named_function(self, spec, node, scope, lines, entities, claimed) -> str | None:
        """Functions that get their name from context: variables, assignments, properties, export default.

        Returns the scope prefix for children when something was emitted.
        """
        kind = node.type
        name = value = None
        if kind == "variable_declarator":
            name, value = self._text(node.child_by_field_name("name")), node.child_by_field_name("value")
        elif kind in ("field_definition", "public_field_definition"):
            name = self._text(node.child_by_field_name("property") or node.child_by_field_name("name"))
            value = node.child_by_field_name("value")
        elif kind == "pair":
            name, value = self._text(node.child_by_field_name("key")), node.child_by_field_name("value")
        elif kind == "assignment_expression":
            left = node.child_by_field_name("left")
            if left is not None and left.type == "member_expression":
                left = left.child_by_field_name("property")
            name, value = self._text(left), node.child_by_field_name("right")
        elif kind in _ANON_FUNCTIONS and node.parent is not None and node.parent.type == "export_statement":
            name, value = "default", node
        while value is not None and value.type in _TRANSPARENT_WRAPPERS:
            # <T>fn puts the type first; every other wrapper puts the expression first
            inner = value.named_children
            value = (inner[-1] if value.type == "type_assertion" else inner[0]) if inner else None
        if not name or value is None or value.type not in _ANON_FUNCTIONS or value.id in claimed:
            return None
        claimed.add(value.id)
        range_node = node if kind in ("variable_declarator", "field_definition", "public_field_definition",
                                      "pair") else value
        if kind == "assignment_expression":
            range_node = node.parent if node.parent is not None and node.parent.type == "expression_statement" else node
        is_method = kind in ("field_definition", "public_field_definition")
        qualified = f"{scope}{name}"
        self._emit_function(spec, value, range_node, name, qualified, is_method and bool(scope), lines, entities)
        return f"{qualified}."
