"""Skills MCP Server.

MCP server implementing the Agent Skills specification.
Enables AI agents to discover, validate, and execute skills via MCP protocol.
"""

from skills_mcp.domain.exceptions import (
    ManifestParseError,
    ResourceNotFoundError,
    SkillError,
    SkillNotFoundError,
)
from skills_mcp.domain.models.manifest import SkillManifest
from skills_mcp.domain.models.resource import ResourceType, SkillResource
from skills_mcp.domain.models.skill import Skill
from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.infrastructure.mcp.server import SkillsMCPServer
from skills_mcp.infrastructure.persistence.factory import create_local_repository


__version__ = "0.1.0"

__all__ = [
    "ManifestParseError",
    "ResourceNotFoundError",
    "ResourceType",
    "Skill",
    "SkillError",
    "SkillManifest",
    "SkillName",
    "SkillNotFoundError",
    "SkillResource",
    "SkillsMCPServer",
    "__version__",
    "create_local_repository",
]
