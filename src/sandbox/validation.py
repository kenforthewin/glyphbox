"""
Skill code validation.

Validates Python code before execution in the sandbox to catch
syntax errors and security issues early.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import Optional

from .exceptions import SkillSecurityError, SkillSyntaxError, SkillValidationError

# Allowed imports for skill code
ALLOWED_IMPORTS = {
    # Standard library - safe modules
    "asyncio",
    "typing",
    "dataclasses",
    "enum",
    "collections",
    "itertools",
    "functools",
    "math",
    "random",
    "re",
    "json",
    "time",
    # Our API modules (will be provided via stub)
    "api",
}

# Forbidden module prefixes
FORBIDDEN_MODULE_PREFIXES = [
    "os",
    "sys",
    "subprocess",
    "socket",
    "http",
    "urllib",
    "ftplib",
    "smtplib",
    "pickle",
    "shelve",
    "marshal",
    "importlib",
    "builtins",
    "__builtins__",
    "ctypes",
    "multiprocessing",
    "threading",
    "concurrent",
    "signal",
    "resource",
    "pty",
    "tty",
    "termios",
    "fcntl",
    "mmap",
    "sysconfig",
    "platform",
    "getpass",
    "shutil",
    "tempfile",
    "pathlib",
    "glob",
    "fnmatch",
    "linecache",
    "tokenize",
    "code",
    "codeop",
    "compile",
]

# Forbidden function calls
# Note: hasattr/getattr are allowed as they're needed for defensive programming
# and can't be used for sandbox escapes (we block dangerous attribute names separately)
# Note: dir/type are allowed for API introspection - they're safe and useful for debugging
FORBIDDEN_CALLS = {
    "exec",
    "eval",
    "compile",
    "open",
    "input",
    "__import__",
    "globals",
    "locals",
    "vars",
    "setattr",
    "delattr",
    "issubclass",
    "super",
    "classmethod",
    "staticmethod",
    "property",
    "memoryview",
    "bytearray",
    "bytes",  # Can be used for binary exploits
    "breakpoint",
    "help",
    "license",
    "credits",
    "copyright",
    "quit",
    "exit",
}

# Forbidden attribute accesses
FORBIDDEN_ATTRIBUTES = {
    "__class__",
    "__bases__",
    "__subclasses__",
    "__mro__",
    "__code__",
    "__globals__",
    "__dict__",
    "__module__",
    "__import__",
    "__builtins__",
    "__loader__",
    "__spec__",
    "__file__",
    "__cached__",
    "__annotations__",
    "__kwdefaults__",
    "__closure__",
    "__func__",
    "__self__",
    "__name__",
    "__qualname__",
    "func_code",
    "func_globals",
    "gi_frame",
    "gi_code",
    "cr_frame",
    "cr_code",
    "ag_frame",
    "ag_code",
    "f_back",
    "f_builtins",
    "f_code",
    "f_globals",
    "f_locals",
    "tb_frame",
    "tb_next",
}


@dataclass
class ValidationResult:
    """Result of skill validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    function_name: Optional[str] = None
    has_correct_signature: bool = False


class SecurityVisitor(ast.NodeVisitor):
    """AST visitor that checks for security violations."""

    def __init__(self):
        self.violations: list[str] = []
        self.warnings: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        """Check import statements."""
        for alias in node.names:
            module = alias.name.split(".")[0]
            if module not in ALLOWED_IMPORTS:
                if any(module.startswith(prefix) for prefix in FORBIDDEN_MODULE_PREFIXES):
                    self.violations.append(
                        f"Forbidden import: '{alias.name}' (line {node.lineno})"
                    )
                else:
                    self.warnings.append(
                        f"Unknown import: '{alias.name}' may not be available (line {node.lineno})"
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from ... import statements."""
        if node.module:
            module = node.module.split(".")[0]
            if module not in ALLOWED_IMPORTS:
                if any(module.startswith(prefix) for prefix in FORBIDDEN_MODULE_PREFIXES):
                    self.violations.append(
                        f"Forbidden import: 'from {node.module}' (line {node.lineno})"
                    )
                else:
                    self.warnings.append(
                        f"Unknown import: 'from {node.module}' may not be available (line {node.lineno})"
                    )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls."""
        # Check direct calls like exec(), eval()
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                self.violations.append(
                    f"Forbidden function call: '{node.func.id}()' (line {node.lineno})"
                )

        # Check attribute calls like os.system()
        elif isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in {"system", "popen", "spawn", "exec", "execv", "execve"}:
                self.violations.append(
                    f"Forbidden method call: '.{attr}()' (line {node.lineno})"
                )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check attribute accesses."""
        if node.attr in FORBIDDEN_ATTRIBUTES:
            self.violations.append(
                f"Forbidden attribute access: '.{node.attr}' (line {node.lineno})"
            )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Check subscript accesses for string-based attribute bypass."""
        # Check for things like obj["__class__"]
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            if node.slice.value in FORBIDDEN_ATTRIBUTES:
                self.violations.append(
                    f"Forbidden subscript access: '[{node.slice.value!r}]' (line {node.lineno})"
                )
        self.generic_visit(node)


def validate_syntax(code: str, skill_name: str = "") -> None:
    """
    Validate Python syntax.

    Args:
        code: Python source code
        skill_name: Name of skill for error messages

    Raises:
        SkillSyntaxError: If code has syntax errors
    """
    try:
        ast.parse(code)
    except SyntaxError as e:
        raise SkillSyntaxError(
            f"Syntax error in skill code: {e.msg}",
            skill_name=skill_name,
            line=e.lineno or 0,
            column=e.offset or 0,
        ) from e


def validate_security(code: str, skill_name: str = "") -> list[str]:
    """
    Check code for security violations.

    Args:
        code: Python source code
        skill_name: Name of skill for error messages

    Returns:
        List of warning messages (non-fatal)

    Raises:
        SkillSecurityError: If code contains forbidden operations
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Syntax errors should be caught by validate_syntax first
        return []

    visitor = SecurityVisitor()
    visitor.visit(tree)

    if visitor.violations:
        raise SkillSecurityError(
            f"Security violations in skill code: {'; '.join(visitor.violations)}",
            skill_name=skill_name,
            violation=visitor.violations[0],
        )

    return visitor.warnings


def validate_signature(code: str, skill_name: str = "") -> tuple[bool, Optional[str]]:
    """
    Validate that code defines a skill function with correct signature.

    Expected signature:
        async def skill_name(nh: NetHackAPI, **params) -> SkillResult:

    Args:
        code: Python source code
        skill_name: Expected skill name (optional)

    Returns:
        Tuple of (is_valid, actual_function_name)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False, None

    # Find async function definitions
    async_functions = [
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)
    ]

    if not async_functions:
        return False, None

    # Check the first (or matching) async function
    for func in async_functions:
        if skill_name and func.name != skill_name:
            continue

        # Check it has at least one argument (nh: NetHackAPI)
        args = func.args
        if len(args.args) < 1:
            continue

        # Check for **kwargs (params)
        if args.kwarg is None:
            # No **kwargs, but that's okay - params can be explicit
            pass

        return True, func.name

    # If skill_name specified but not found, check if any async def exists
    if async_functions:
        return True, async_functions[0].name

    return False, None


def validate_adhoc_code(code: str) -> ValidationResult:
    """
    Validate ad-hoc code for execute_code (no async def signature required).

    This validates syntax and security but does NOT require the code to
    define an async function. The code will be wrapped in an async function
    at execution time.

    Args:
        code: Python source code

    Returns:
        ValidationResult with validation status and any errors/warnings
    """
    result = ValidationResult(valid=True)
    errors = []
    warnings = []

    # 1. Syntax validation
    try:
        validate_syntax(code)
    except SkillSyntaxError as e:
        errors.append(f"Syntax error at line {e.line}: {str(e)}")
        result.valid = False
        result.errors = errors
        return result

    # 2. Security validation
    try:
        security_warnings = validate_security(code)
        warnings.extend(security_warnings)
    except SkillSecurityError as e:
        errors.append(f"Security violation: {e.violation}")
        result.valid = False
        result.errors = errors
        result.warnings = warnings
        return result

    # No signature validation for ad-hoc code
    result.errors = errors
    result.warnings = warnings
    return result


def validate_skill(code: str, skill_name: str = "") -> ValidationResult:
    """
    Perform complete validation of skill code.

    Args:
        code: Python source code
        skill_name: Expected skill name

    Returns:
        ValidationResult with validation status and any errors/warnings
    """
    result = ValidationResult(valid=True)
    errors = []
    warnings = []

    # 1. Syntax validation
    try:
        validate_syntax(code, skill_name)
    except SkillSyntaxError as e:
        errors.append(f"Syntax error at line {e.line}: {str(e)}")
        result.valid = False
        result.errors = errors
        return result

    # 2. Security validation
    try:
        security_warnings = validate_security(code, skill_name)
        warnings.extend(security_warnings)
    except SkillSecurityError as e:
        errors.append(f"Security violation: {e.violation}")
        result.valid = False
        result.errors = errors
        result.warnings = warnings
        return result

    # 3. Signature validation
    has_signature, func_name = validate_signature(code, skill_name)
    result.function_name = func_name
    result.has_correct_signature = has_signature

    if not has_signature:
        errors.append(
            "Skill must define an async function with signature: "
            "async def skill_name(nh: NetHackAPI, **params) -> SkillResult"
        )
        result.valid = False

    result.errors = errors
    result.warnings = warnings
    return result


def extract_skill_metadata(code: str) -> dict:
    """
    Extract metadata from skill code docstring.

    Expected format in docstring:
        '''
        Description of what the skill does.

        Category: exploration
        Stops when: monster spotted, low HP
        '''

    Returns:
        Dict with extracted metadata
    """
    metadata = {
        "description": "",
        "category": "general",
        "stops_when": [],
    }

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return metadata

    # Find the first async function
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            docstring = ast.get_docstring(node)
            if docstring:
                lines = docstring.strip().split("\n")

                # First paragraph is description
                desc_lines = []
                for line in lines:
                    if line.strip() and not line.strip().startswith(("Category:", "Stops")):
                        desc_lines.append(line.strip())
                    elif not line.strip():
                        if desc_lines:
                            break
                    else:
                        break
                metadata["description"] = " ".join(desc_lines)

                # Parse metadata fields
                for line in lines:
                    line = line.strip()
                    if line.lower().startswith("category:"):
                        metadata["category"] = line.split(":", 1)[1].strip().lower()
                    elif line.lower().startswith("stops when:"):
                        stops = line.split(":", 1)[1].strip()
                        metadata["stops_when"] = [s.strip() for s in stops.split(",")]

            break

    return metadata
