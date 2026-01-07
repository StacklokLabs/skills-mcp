"""Configuration models for skills-mcp.

This module defines Pydantic models for configuration validation.
The configuration supports both local filesystem and OCI registry sources.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class LocalSourceConfig(BaseModel):
    """Configuration for local filesystem skill sources.

    Attributes:
        paths: List of directories to scan for skills.
    """

    paths: list[Path] = Field(default_factory=list)

    @field_validator("paths", mode="before")
    @classmethod
    def expand_paths(cls, v: list[str | Path]) -> list[Path]:
        """Expand ~ and resolve paths."""
        return [Path(p).expanduser() for p in v]


class OCIAuthConfig(BaseModel):
    """Authentication configuration for an OCI registry.

    Attributes:
        username: Username for authentication (optional).
        password: Password or token for authentication (optional).
    """

    username: str | None = None
    password: str | None = None


class OCISkillConfig(BaseModel):
    """Configuration for a single OCI skill reference.

    Attributes:
        image: Full OCI image reference (e.g., ghcr.io/org/skill:v1.0.0).
    """

    image: str


class OCISourceConfig(BaseModel):
    """Configuration for OCI registry skill sources.

    Attributes:
        cache_dir: Local cache directory for pulled artifacts.
        cache_ttl: Cache TTL in seconds (0 = never expire).
        verify_tls: Whether to verify TLS certificates.
        skills: List of OCI skill references to pull.
        auth: Per-registry authentication configuration.
    """

    cache_dir: Path | None = None
    cache_ttl: Annotated[int, Field(ge=0)] = 3600
    verify_tls: bool = True
    skills: list[OCISkillConfig] = Field(default_factory=list)
    auth: dict[str, OCIAuthConfig] = Field(default_factory=dict)

    @field_validator("cache_dir", mode="before")
    @classmethod
    def expand_cache_dir(cls, v: str | Path | None) -> Path | None:
        """Expand ~ in cache directory path."""
        if v is None:
            return None
        return Path(v).expanduser()


class SkillsConfig(BaseModel):
    """Root configuration model for skills-mcp.

    This is the main configuration model that represents a skills.yaml file.

    Attributes:
        version: Configuration schema version.
        local: Configuration for local filesystem sources.
        oci: Configuration for OCI registry sources.

    Example:
        ```yaml
        version: "1"

        local:
          paths:
            - ./skills
            - ~/.local/share/skills

        oci:
          cache_ttl: 3600
          skills:
            - image: ghcr.io/stacklok/skills/data-analysis:v1.0.0
            - image: ghcr.io/stacklok/skills/code-review:latest
          auth:
            ghcr.io:
              username: ${GITHUB_USER}
              password: ${GITHUB_TOKEN}
        ```
    """

    version: str = "1"
    local: LocalSourceConfig | None = None
    oci: OCISourceConfig | None = None

    def has_local_sources(self) -> bool:
        """Check if local sources are configured."""
        return self.local is not None and len(self.local.paths) > 0

    def has_oci_sources(self) -> bool:
        """Check if OCI sources are configured."""
        return self.oci is not None and len(self.oci.skills) > 0

    def is_empty(self) -> bool:
        """Check if no sources are configured."""
        return not self.has_local_sources() and not self.has_oci_sources()
