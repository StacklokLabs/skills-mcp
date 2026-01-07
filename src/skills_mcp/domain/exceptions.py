"""Domain exceptions for Skills MCP Server.

All domain-specific exceptions are defined here.
"""


class SkillError(Exception):
    """Base exception for all skill-related errors."""


class InvalidSkillNameError(SkillError):
    """Raised when a skill name doesn't match the specification."""

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason
        super().__init__(f"Invalid skill name '{name}': {reason}")


class SkillNotFoundError(SkillError):
    """Raised when a requested skill cannot be found."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Skill not found: {name}")


class ResourceNotFoundError(SkillError):
    """Raised when a requested resource cannot be found within a skill."""

    def __init__(self, skill_name: str, resource_type: str, resource_name: str) -> None:
        self.skill_name = skill_name
        self.resource_type = resource_type
        self.resource_name = resource_name
        msg = f"Resource not found: {resource_type}/{resource_name} "
        msg += f"in skill '{skill_name}'"
        super().__init__(msg)


class ManifestParseError(SkillError):
    """Raised when SKILL.md frontmatter cannot be parsed."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to parse manifest at '{path}': {reason}")


class MissingRequiredFieldError(ManifestParseError):
    """Raised when a required field is missing from the manifest."""

    def __init__(self, path: str, field: str) -> None:
        self.field = field
        super().__init__(path, f"missing required field '{field}'")


class SkillValidationError(SkillError):
    """Raised when skill validation fails."""

    def __init__(self, name: str, errors: list[str]) -> None:
        self.name = name
        self.errors = errors
        error_list = "; ".join(errors)
        super().__init__(f"Skill '{name}' validation failed: {error_list}")
