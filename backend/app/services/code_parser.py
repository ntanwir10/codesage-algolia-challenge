import re
from typing import List, Dict, Any, Optional
import structlog
from dataclasses import dataclass

logger = structlog.get_logger()


@dataclass
class ParsedCodeEntity:
    """Represents a code entity (function, class, etc.) extracted from a file during parsing"""
    entity_type: str  # "function", "class", "import", "variable"
    name: str
    description: str
    line_start: int
    line_end: int
    parameters: List[str] = None
    return_type: str = None
    content: str = None
    imports: List[str] = None


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
        
    async def extract_entities(self, file_path: str, content: str, language: str) -> List[ParsedCodeEntity]:
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
            
    def _parse_python(self, content: str, file_path: str) -> List[ParsedCodeEntity]:
        """Parse Python code for functions, classes, imports"""
        entities = []
        lines = content.split('\n')
        
        # Extract imports
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith(('import ', 'from ')):
                entities.append(ParsedCodeEntity(
                    entity_type="import",
                    name=line,
                    description=f"Import statement: {line}",
                    line_start=i + 1,
                    line_end=i + 1,
                    content=line
                ))
        
        # Extract functions and classes
        in_function = False
        in_class = False
        current_entity = None
        indent_level = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Function definition
            if stripped.startswith('def '):
                match = re.match(r'def\s+(\w+)\s*\((.*?)\)(?:\s*->\s*(.+?))?:', stripped)
                if match:
                    func_name, params, return_type = match.groups()
                    parameters = [p.strip() for p in params.split(',') if p.strip()]
                    
                    current_entity = ParsedCodeEntity(
                        entity_type="function",
                        name=func_name,
                        description=f"Python function: {func_name}",
                        line_start=i + 1,
                        line_end=i + 1,  # Will be updated when function ends
                        parameters=parameters,
                        return_type=return_type.strip() if return_type else None,
                        content=line
                    )
                    in_function = True
                    indent_level = len(line) - len(line.lstrip())
                    
            # Class definition  
            elif stripped.startswith('class '):
                match = re.match(r'class\s+(\w+)(?:\((.*?)\))?:', stripped)
                if match:
                    class_name, inheritance = match.groups()
                    
                    current_entity = ParsedCodeEntity(
                        entity_type="class",
                        name=class_name,
                        description=f"Python class: {class_name}",
                        line_start=i + 1,
                        line_end=i + 1,
                        parameters=[inheritance] if inheritance else None,
                        content=line
                    )
                    in_class = True
                    indent_level = len(line) - len(line.lstrip())
                    
            # Check if we've exited the current function/class
            elif (in_function or in_class) and line.strip():
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= indent_level:
                    # End of function/class
                    if current_entity:
                        current_entity.line_end = i
                        entities.append(current_entity)
                        current_entity = None
                    in_function = False
                    in_class = False
                    
        # Handle case where function/class goes to end of file
        if current_entity:
            current_entity.line_end = len(lines)
            entities.append(current_entity)
            
        return entities
        
    def _parse_javascript(self, content: str, file_path: str) -> List[ParsedCodeEntity]:
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
        
    def _parse_typescript(self, content: str, file_path: str) -> List[ParsedCodeEntity]:
        """Parse TypeScript (similar to JavaScript but with types)"""
        return self._parse_javascript(content, file_path)  # Reuse JS parser for now
        
    def _parse_java(self, content: str, file_path: str) -> List[ParsedCodeEntity]:
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
        
    def _parse_go(self, content: str, file_path: str) -> List[ParsedCodeEntity]:
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
        
    def _parse_generic(self, content: str, file_path: str) -> List[ParsedCodeEntity]:
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