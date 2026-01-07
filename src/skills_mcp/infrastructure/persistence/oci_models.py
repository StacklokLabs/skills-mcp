"""OCI artifact models for skill distribution.

This module defines data models for OCI registry interactions,
compatible with skillet's artifact format.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# =============================================================================
# Media Type Constants (matching skillet)
# =============================================================================

# Artifact type identifying skill artifacts
ARTIFACT_TYPE_SKILL = "application/vnd.stacklok.skillet.skill.v1"

# Standard OCI media types for Kubernetes image volume compatibility
MEDIA_TYPE_IMAGE_INDEX = "application/vnd.oci.image.index.v1+json"
MEDIA_TYPE_IMAGE_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
MEDIA_TYPE_IMAGE_CONFIG = "application/vnd.oci.image.config.v1+json"
MEDIA_TYPE_IMAGE_LAYER = "application/vnd.oci.image.layer.v1.tar+gzip"


# =============================================================================
# Label Constants (matching skillet)
# =============================================================================

# Labels in OCI image config
LABEL_SKILL_NAME = "org.stacklok.skillet.name"
LABEL_SKILL_DESCRIPTION = "org.stacklok.skillet.description"
LABEL_SKILL_VERSION = "org.stacklok.skillet.version"
LABEL_SKILL_LICENSE = "org.stacklok.skillet.license"
LABEL_SKILL_ALLOWED_TOOLS = "org.stacklok.skillet.allowedTools"
LABEL_SKILL_FILES = "org.stacklok.skillet.files"

# Annotations in manifest
ANNOTATION_CREATED = "org.opencontainers.image.created"
ANNOTATION_SKILL_NAME = "org.stacklok.skillet.skill.name"
ANNOTATION_SKILL_DESCRIPTION = "org.stacklok.skillet.skill.description"
ANNOTATION_SKILL_VERSION = "org.stacklok.skillet.skill.version"


# =============================================================================
# Security Limits (matching skillet)
# =============================================================================

MAX_MANIFEST_SIZE = 1 * 1024 * 1024  # 1 MB
MAX_BLOB_SIZE = 100 * 1024 * 1024  # 100 MB


# =============================================================================
# OCI Reference Parsing
# =============================================================================

# Default registry if none specified
DEFAULT_REGISTRY = "docker.io"
DEFAULT_TAG = "latest"


@dataclass(frozen=True, slots=True)
class OCISkillReference:
    """Parsed OCI image reference for a skill artifact.

    Represents a reference to a skill stored in an OCI registry.
    Format: registry/namespace/name:tag

    Examples:
        - ghcr.io/stacklok/skills/data-analysis:v1.0.0
        - docker.io/myorg/skill-name:latest
        - localhost:5000/test/skill:dev

    Attributes:
        registry: The registry hostname (e.g., "ghcr.io").
        namespace: The namespace/repository path (e.g., "stacklok/skills").
        name: The skill/image name (e.g., "data-analysis").
        tag: The image tag (e.g., "v1.0.0" or "latest").
    """

    registry: str
    namespace: str
    name: str
    tag: str = DEFAULT_TAG

    @property
    def repository(self) -> str:
        """Return the full repository path without tag.

        Returns:
            Repository path like "stacklok/skills/data-analysis".
        """
        if self.namespace:
            return f"{self.namespace}/{self.name}"
        return self.name

    @property
    def full_ref(self) -> str:
        """Return the full OCI reference string.

        Returns:
            Full reference like "ghcr.io/stacklok/skills/data-analysis:v1.0.0".
        """
        return f"{self.registry}/{self.repository}:{self.tag}"

    @classmethod
    def from_string(cls, reference: str) -> OCISkillReference:
        """Parse an OCI reference string into components.

        Args:
            reference: OCI reference string like "ghcr.io/org/repo:tag".

        Returns:
            Parsed OCISkillReference.

        Raises:
            ValueError: If the reference format is invalid.
        """
        reference = reference.strip()
        if not reference:
            raise ValueError("OCI reference cannot be empty")

        # Handle tag - a tag is the part after : that comes after the last /
        # This handles registry:port/path:tag correctly
        tag = DEFAULT_TAG
        last_slash_idx = reference.rfind("/")
        last_colon_idx = reference.rfind(":")

        # If the last colon is after the last slash, it's a tag separator
        if last_colon_idx > last_slash_idx:
            tag = reference[last_colon_idx + 1 :]
            reference = reference[:last_colon_idx]

        # Split into registry and path
        parts = reference.split("/")

        if len(parts) == 1:
            # Just name, use defaults
            return cls(
                registry=DEFAULT_REGISTRY,
                namespace="library",
                name=parts[0],
                tag=tag,
            )

        # Check if first part looks like a registry (has dots or port)
        first_part = parts[0]
        if "." in first_part or ":" in first_part or first_part == "localhost":
            registry = first_part
            path_parts = parts[1:]
        else:
            registry = DEFAULT_REGISTRY
            path_parts = parts

        if not path_parts:
            raise ValueError(f"Invalid OCI reference: {reference}")

        # Last part is the name, rest is namespace
        name = path_parts[-1]
        namespace = "/".join(path_parts[:-1]) if len(path_parts) > 1 else ""

        return cls(
            registry=registry,
            namespace=namespace,
            name=name,
            tag=tag,
        )

    def __str__(self) -> str:
        """Return the full reference string."""
        return self.full_ref


# =============================================================================
# Skill Metadata from OCI Config
# =============================================================================


@dataclass(frozen=True, slots=True)
class SkillConfig:
    """Skill metadata extracted from OCI image config labels.

    This represents the metadata stored in an OCI image config's
    Labels field, as produced by skillet.

    Attributes:
        name: Skill name (required).
        description: Skill description (required).
        version: Skill version (optional).
        license: License identifier (optional).
        allowed_tools: List of allowed tool names (optional).
        files: List of files in the skill (optional).
    """

    name: str
    description: str
    version: str | None = None
    license: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    @classmethod
    def from_labels(cls, labels: dict[str, str]) -> SkillConfig:
        """Extract SkillConfig from OCI image config labels.

        Args:
            labels: Dictionary of labels from OCI config.

        Returns:
            Parsed SkillConfig.

        Raises:
            ValueError: If required labels are missing.
        """
        name = labels.get(LABEL_SKILL_NAME)
        if not name:
            raise ValueError(f"Missing required label: {LABEL_SKILL_NAME}")

        description = labels.get(LABEL_SKILL_DESCRIPTION)
        if not description:
            raise ValueError(f"Missing required label: {LABEL_SKILL_DESCRIPTION}")

        # Parse JSON arrays
        allowed_tools: list[str] = []
        if tools_json := labels.get(LABEL_SKILL_ALLOWED_TOOLS):
            try:
                allowed_tools = json.loads(tools_json)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON in {LABEL_SKILL_ALLOWED_TOOLS}: {e}"
                ) from e

        files: list[str] = []
        if files_json := labels.get(LABEL_SKILL_FILES):
            try:
                files = json.loads(files_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {LABEL_SKILL_FILES}: {e}") from e

        return cls(
            name=name,
            description=description,
            version=labels.get(LABEL_SKILL_VERSION),
            license=labels.get(LABEL_SKILL_LICENSE),
            allowed_tools=allowed_tools,
            files=files,
        )


# =============================================================================
# OCI Repository Configuration
# =============================================================================


@dataclass
class OCIAuthConfig:
    """Authentication configuration for an OCI registry.

    Attributes:
        registry: Registry hostname this auth applies to.
        username: Username for authentication (optional).
        password: Password or token for authentication (optional).
    """

    registry: str
    username: str | None = None
    password: str | None = None

    @property
    def is_anonymous(self) -> bool:
        """Check if this is anonymous authentication."""
        return self.username is None and self.password is None


@dataclass
class OCIRepositoryConfig:
    """Configuration for an OCI skill repository.

    Attributes:
        skills: List of skill references to pull from registries.
        auth: Authentication configs per registry.
        cache_dir: Local cache directory for pulled artifacts.
        cache_ttl: Cache TTL in seconds (0 = never expire).
        verify_tls: Whether to verify TLS certificates.
    """

    skills: list[OCISkillReference] = field(default_factory=list)
    auth: dict[str, OCIAuthConfig] = field(default_factory=dict)
    cache_dir: Path | None = None
    cache_ttl: int = 3600
    verify_tls: bool = True

    @staticmethod
    def default_cache_dir() -> Path:
        """Return the default cache directory.

        Returns:
            Path to ~/.cache/skills-mcp/oci/
        """
        return Path.home() / ".cache" / "skills-mcp" / "oci"


# =============================================================================
# OCI Manifest/Index Structures
# =============================================================================


@dataclass
class OCIPlatform:
    """Platform specification in an OCI manifest.

    Attributes:
        architecture: CPU architecture (e.g., "amd64").
        os: Operating system (e.g., "linux").
    """

    architecture: str
    os: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCIPlatform:
        """Create from dictionary."""
        return cls(
            architecture=data.get("architecture", ""),
            os=data.get("os", ""),
        )


@dataclass
class OCIDescriptor:
    """Descriptor for a blob or manifest in OCI.

    Attributes:
        media_type: Media type of the content.
        digest: Content-addressable digest (sha256:...).
        size: Size in bytes.
        annotations: Optional annotations.
        platform: Optional platform specification.
    """

    media_type: str
    digest: str
    size: int
    annotations: dict[str, str] = field(default_factory=dict)
    platform: OCIPlatform | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCIDescriptor:
        """Create from dictionary."""
        platform = None
        if "platform" in data:
            platform = OCIPlatform.from_dict(data["platform"])

        return cls(
            media_type=data.get("mediaType", ""),
            digest=data.get("digest", ""),
            size=data.get("size", 0),
            annotations=data.get("annotations", {}),
            platform=platform,
        )


@dataclass
class OCIImageIndex:
    """OCI image index (multi-platform manifest list).

    Attributes:
        schema_version: Schema version (always 2).
        media_type: Media type of the index.
        artifact_type: Type of artifact (for skills: ARTIFACT_TYPE_SKILL).
        manifests: List of manifest descriptors.
        annotations: Optional annotations.
    """

    schema_version: int
    media_type: str
    manifests: list[OCIDescriptor]
    artifact_type: str | None = None
    annotations: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCIImageIndex:
        """Create from dictionary."""
        manifests = [
            OCIDescriptor.from_dict(m) for m in data.get("manifests", [])
        ]
        return cls(
            schema_version=data.get("schemaVersion", 2),
            media_type=data.get("mediaType", MEDIA_TYPE_IMAGE_INDEX),
            artifact_type=data.get("artifactType"),
            manifests=manifests,
            annotations=data.get("annotations", {}),
        )


@dataclass
class OCIImageManifest:
    """OCI image manifest.

    Attributes:
        schema_version: Schema version (always 2).
        media_type: Media type of the manifest.
        artifact_type: Type of artifact.
        config: Descriptor for the config blob.
        layers: List of layer descriptors.
        annotations: Optional annotations.
    """

    schema_version: int
    media_type: str
    config: OCIDescriptor
    layers: list[OCIDescriptor]
    artifact_type: str | None = None
    annotations: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCIImageManifest:
        """Create from dictionary."""
        config = OCIDescriptor.from_dict(data.get("config", {}))
        layers = [OCIDescriptor.from_dict(layer) for layer in data.get("layers", [])]

        return cls(
            schema_version=data.get("schemaVersion", 2),
            media_type=data.get("mediaType", MEDIA_TYPE_IMAGE_MANIFEST),
            artifact_type=data.get("artifactType"),
            config=config,
            layers=layers,
            annotations=data.get("annotations", {}),
        )


@dataclass
class OCIImageConfig:
    """OCI image configuration.

    Attributes:
        architecture: CPU architecture.
        os: Operating system.
        labels: Labels containing skill metadata.
        rootfs_diff_ids: List of layer diff IDs.
    """

    architecture: str
    os: str
    labels: dict[str, str] = field(default_factory=dict)
    rootfs_diff_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCIImageConfig:
        """Create from dictionary."""
        config_data = data.get("config", {})
        labels = config_data.get("Labels", {}) or {}

        rootfs = data.get("rootfs", {})
        diff_ids = rootfs.get("diff_ids", [])

        return cls(
            architecture=data.get("architecture", ""),
            os=data.get("os", ""),
            labels=labels,
            rootfs_diff_ids=diff_ids,
        )
