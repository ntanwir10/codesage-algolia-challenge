import ast
import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class ParsedCodeEntity:
    """Represents a code entity (function, class, etc.) extracted from a file during parsing"""
    entity_type: str  # "function", "class", "import", "variable"
    name: str
    description: str
    line_start: int
    line_end: int
    parameters: list[str] = None
    return_type: str = None
    content: str = None
    imports: list[str] = None


class CodeParser:
    """
    Parse code files to extract entities for Algolia indexing.
    Based on architecture.md: File Parsing & Analysis → Algolia Indexing
    """
    
    def __init__(self):
        # Pattern matching for different languages
        self.parsers = {
            "python": self._parse_python,
            "javascript": self._parse_javascript,
            "typescript": self._parse_typescript,
            "java": self._parse_java,
            "go": self._parse_go,
        }
        
    async def extract_entities(self, file_path: str, content: str, language: str) -> list[ParsedCodeEntity]:
        """
        Extract code entities from file content.
        Returns list of functions, classes, imports for Algolia indexing.
        """
        try:
            if not content or not content.strip():
                return []
                
            # Get appropriate parser for language
            parser = self.parsers.get(language, self._parse_generic)
            
            entities = parser(content, file_path)
            
            logger.debug(
                "Extracted code entities",
                file_path=file_path,
                language=language,
                entities_count=len(entities)
            )
            
            return entities
            
        except Exception as e:
            logger.error("Failed to parse code file", file_path=file_path, error=str(e))
            return []
            
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
                    description=f"Python {kind}: {qualified_name}",
                    line_start=node.lineno,
                    line_end=node.end_lineno,
                    parameters=self._python_parameters(node.args),
                    return_type=ast.unparse(node.returns) if node.returns else None,
                    content=lines[node.lineno - 1]
                ))
                self._collect_python_definitions(node, lines, f"{qualified_name}.", False, entities)

            elif isinstance(node, ast.ClassDef):
                qualified_name = f"{scope}{node.name}"
                inheritance = ", ".join(ast.unparse(base) for base in node.bases)
                entities.append(ParsedCodeEntity(
                    entity_type="class",
                    name=node.name,
                    description=f"Python class: {qualified_name}",
                    line_start=node.lineno,
                    line_end=node.end_lineno,
                    parameters=[inheritance] if inheritance else None,
                    content=lines[node.lineno - 1]
                ))
                self._collect_python_definitions(node, lines, f"{qualified_name}.", True, entities)

            elif not isinstance(node, ast.expr):
                # Definitions nested in if/try/with blocks keep the enclosing scope.
                # Expressions can't contain def/class, so skipping them avoids deep recursion.
                self._collect_python_definitions(node, lines, scope, in_class, entities)

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
            elif match := re.match(r'(?:async\s+)?def\s+(\w+)\s*\((.*?)\)(?:\s*->\s*(.+?))?:', stripped):
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

        return entities
        
    def _parse_javascript(self, content: str, file_path: str) -> list[ParsedCodeEntity]:
        """Parse JavaScript code for functions, classes, imports"""
        entities = []
        lines = content.split('\n')
        
        # Extract imports/requires
        for i, line in enumerate(lines):
            line = line.strip()
            if (line.startswith(('import ', 'const ')) and 'require(' in line) or \
               line.startswith(('import ', 'export ')):
                entities.append(ParsedCodeEntity(
                    entity_type="import",
                    name=line,
                    description=f"Import/require statement: {line}",
                    line_start=i + 1,
                    line_end=i + 1,
                    content=line
                ))
        
        # Extract functions (function declarations, arrow functions, methods)
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Function declarations: function name() {}
            func_match = re.match(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*?)\)', stripped)
            if func_match:
                func_name, params = func_match.groups()
                parameters = [p.strip() for p in params.split(',') if p.strip()]
                
                entities.append(ParsedCodeEntity(
                    entity_type="function",
                    name=func_name,
                    description=f"JavaScript function: {func_name}",
                    line_start=i + 1,
                    line_end=i + 1,
                    parameters=parameters,
                    content=stripped
                ))
                
            # Arrow functions: const name = () => {}
            arrow_match = re.match(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>', stripped)
            if arrow_match:
                func_name, params = arrow_match.groups()
                parameters = [p.strip() for p in params.split(',') if p.strip()]
                
                entities.append(ParsedCodeEntity(
                    entity_type="function",
                    name=func_name,
                    description=f"Arrow function: {func_name}",
                    line_start=i + 1,
                    line_end=i + 1,
                    parameters=parameters,
                    content=stripped
                ))
                
            # Class definitions
            class_match = re.match(r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', stripped)
            if class_match:
                class_name, parent_class = class_match.groups()
                
                entities.append(ParsedCodeEntity(
                    entity_type="class",
                    name=class_name,
                    description=f"JavaScript class: {class_name}",
                    line_start=i + 1,
                    line_end=i + 1,
                    parameters=[parent_class] if parent_class else None,
                    content=stripped
                ))
                
        return entities
        
    def _parse_typescript(self, content: str, file_path: str) -> list[ParsedCodeEntity]:
        """Parse TypeScript (similar to JavaScript but with types)"""
        return self._parse_javascript(content, file_path)  # Reuse JS parser for now
        
    def _parse_java(self, content: str, file_path: str) -> list[ParsedCodeEntity]:
        """Parse Java code for classes, methods, imports"""
        entities = []
        lines = content.split('\n')
        
        # Extract imports
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith('import '):
                entities.append(ParsedCodeEntity(
                    entity_type="import",
                    name=line,
                    description=f"Java import: {line}",
                    line_start=i + 1,
                    line_end=i + 1,
                    content=line
                ))
        
        # Extract classes and methods
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Class definitions
            class_match = re.match(r'(?:public\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', stripped)
            if class_match:
                class_name, parent_class = class_match.groups()
                
                entities.append(ParsedCodeEntity(
                    entity_type="class",
                    name=class_name,
                    description=f"Java class: {class_name}",
                    line_start=i + 1,
                    line_end=i + 1,
                    parameters=[parent_class] if parent_class else None,
                    content=stripped
                ))
                
            # Method definitions
            method_match = re.match(r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(\w+)\s+(\w+)\s*\((.*?)\)', stripped)
            if method_match and not stripped.startswith('class'):
                return_type, method_name, params = method_match.groups()
                parameters = [p.strip() for p in params.split(',') if p.strip()]
                
                entities.append(ParsedCodeEntity(
                    entity_type="function",
                    name=method_name,
                    description=f"Java method: {method_name}",
                    line_start=i + 1,
                    line_end=i + 1,
                    parameters=parameters,
                    return_type=return_type,
                    content=stripped
                ))
                
        return entities
        
    def _parse_go(self, content: str, file_path: str) -> list[ParsedCodeEntity]:
        """Parse Go code for functions, structs, imports"""
        entities = []
        lines = content.split('\n')
        
        # Extract imports
        in_import_block = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == 'import (':
                in_import_block = True
            elif stripped == ')' and in_import_block:
                in_import_block = False
            elif in_import_block or stripped.startswith('import '):
                entities.append(ParsedCodeEntity(
                    entity_type="import",
                    name=stripped,
                    description=f"Go import: {stripped}",
                    line_start=i + 1,
                    line_end=i + 1,
                    content=stripped
                ))
        
        # Extract functions and structs
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Function definitions
            func_match = re.match(r'func\s+(?:\([^)]*\)\s+)?(\w+)\s*\((.*?)\)(?:\s*(.+?))?', stripped)
            if func_match:
                func_name, params, return_type = func_match.groups()
                parameters = [p.strip() for p in params.split(',') if p.strip()]
                
                entities.append(ParsedCodeEntity(
                    entity_type="function",
                    name=func_name,
                    description=f"Go function: {func_name}",
                    line_start=i + 1,
                    line_end=i + 1,
                    parameters=parameters,
                    return_type=return_type.strip() if return_type else None,
                    content=stripped
                ))
                
            # Struct definitions
            struct_match = re.match(r'type\s+(\w+)\s+struct', stripped)
            if struct_match:
                struct_name = struct_match.group(1)
                
                entities.append(ParsedCodeEntity(
                    entity_type="class",
                    name=struct_name,
                    description=f"Go struct: {struct_name}",
                    line_start=i + 1,
                    line_end=i + 1,
                    content=stripped
                ))
                
        return entities
        
    def _parse_generic(self, content: str, file_path: str) -> list[ParsedCodeEntity]:
        """Generic parser for unsupported languages - extract basic patterns"""
        entities = []
        lines = content.split('\n')
        
        # Look for function-like patterns
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Generic function pattern (something with parentheses)
            if re.match(r'\w+.*\([^)]*\)', stripped) and not stripped.startswith(('if', 'while', 'for')):
                entities.append(ParsedCodeEntity(
                    entity_type="function",
                    name="unknown_function",
                    description=f"Generic function pattern: {stripped[:50]}",
                    line_start=i + 1,
                    line_end=i + 1,
                    content=stripped
                ))
                
        return entities 