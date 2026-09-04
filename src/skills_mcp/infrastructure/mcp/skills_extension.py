"""MCP models for the accepted SEP-2640 skills extension snapshot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from mcp.server.context import ServerRequestContext
from mcp.server.extension import Extension, MethodBinding
from mcp.types import RequestParams, Result
from pydantic import BaseModel, ConfigDict


class SkillsListParams(RequestParams):
    """Parameters for ``skills/list``."""

    cursor: str | None = None
    model_config = ConfigDict(extra="forbid")


class SkillsGetParams(RequestParams):
    """Parameters for ``skills/get``."""

    uri: str
    model_config = ConfigDict(extra="forbid")


class ListedSkill(BaseModel):
    """A discoverable static skill."""

    uri: str
    name: str
    description: str
    resources: str = "static"


class SkillFileDescription(BaseModel):
    """Digest and size metadata for one canonical resource."""

    uri: str
    digest: str
    size: int


class SkillsListResult(Result):
    """One complete page of skills."""

    skills: list[ListedSkill]
    nextCursor: str | None = None


class SkillsGetResult(Result):
    """Complete metadata for one static skill."""

    uri: str
    name: str
    description: str
    frontmatter: dict[str, object]
    resources: list[SkillFileDescription]


ExtensionHandler = Callable[
    [ServerRequestContext[Any], Any], Awaitable[SkillsListResult | SkillsGetResult]
]


class SkillsExtension(Extension):
    """SEP-2640 method bindings for the skills extension."""

    identifier = "io.modelcontextprotocol/skills"

    def __init__(
        self,
        list_handler: ExtensionHandler,
        get_handler: ExtensionHandler,
    ) -> None:
        """Initialize extension handlers.

        Args:
            list_handler: Handler for ``skills/list``.
            get_handler: Handler for ``skills/get``.
        """
        self._list_handler = list_handler
        self._get_handler = get_handler

    def methods(self) -> Sequence[MethodBinding]:
        """Return the two accepted SEP method bindings.

        Returns:
            Bindings for ``skills/list`` and ``skills/get``.
        """
        return (
            MethodBinding("skills/list", SkillsListParams, self._list_handler),
            MethodBinding("skills/get", SkillsGetParams, self._get_handler),
        )
