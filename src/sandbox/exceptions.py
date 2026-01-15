"""
Exceptions for the skill execution sandbox.
"""


class SkillExecutionError(Exception):
    """Base exception for skill execution errors."""

    def __init__(self, message: str, skill_name: str = "", details: str = ""):
        self.skill_name = skill_name
        self.details = details
        super().__init__(message)


class SkillSyntaxError(SkillExecutionError):
    """Raised when skill code has invalid Python syntax."""

    def __init__(self, message: str, skill_name: str = "", line: int = 0, column: int = 0):
        self.line = line
        self.column = column
        super().__init__(message, skill_name)


class SkillSecurityError(SkillExecutionError):
    """Raised when skill code contains forbidden operations."""

    def __init__(self, message: str, skill_name: str = "", violation: str = ""):
        self.violation = violation
        super().__init__(message, skill_name)


class SkillTimeoutError(SkillExecutionError):
    """Raised when skill execution exceeds time limit."""

    def __init__(self, message: str, skill_name: str = "", timeout_seconds: float = 0):
        self.timeout_seconds = timeout_seconds
        super().__init__(message, skill_name)


class SkillValidationError(SkillExecutionError):
    """Raised when skill code fails validation checks."""

    def __init__(self, message: str, skill_name: str = "", errors: list[str] | None = None):
        self.errors = errors or []
        super().__init__(message, skill_name)


class SandboxError(Exception):
    """Base exception for sandbox infrastructure errors."""

    pass
