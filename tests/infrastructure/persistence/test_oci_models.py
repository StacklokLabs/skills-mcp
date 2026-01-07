"""Tests for OCI models."""

import pytest

from skills_mcp.infrastructure.persistence.oci_models import (
    DEFAULT_REGISTRY,
    DEFAULT_TAG,
    LABEL_SKILL_DESCRIPTION,
    LABEL_SKILL_NAME,
    MEDIA_TYPE_IMAGE_CONFIG,
    MEDIA_TYPE_IMAGE_INDEX,
    MEDIA_TYPE_IMAGE_MANIFEST,
    OCIAuthConfig,
    OCIDescriptor,
    OCIImageConfig,
    OCIImageIndex,
    OCIImageManifest,
    OCIPlatform,
    OCIRepositoryConfig,
    OCISkillReference,
    SkillConfig,
)


class TestOCISkillReference:
    """Tests for OCISkillReference parsing and properties."""

    def test_from_string_full_reference(self) -> None:
        """Should parse full OCI reference."""
        ref = OCISkillReference.from_string("ghcr.io/stacklok/skills/data:v1.0.0")

        assert ref.registry == "ghcr.io"
        assert ref.namespace == "stacklok/skills"
        assert ref.name == "data"
        assert ref.tag == "v1.0.0"

    def test_from_string_with_port(self) -> None:
        """Should parse reference with registry port."""
        ref = OCISkillReference.from_string("localhost:5000/test/skill:dev")

        assert ref.registry == "localhost:5000"
        assert ref.namespace == "test"
        assert ref.name == "skill"
        assert ref.tag == "dev"

    def test_from_string_default_registry(self) -> None:
        """Should use docker.io for references without registry."""
        ref = OCISkillReference.from_string("myorg/myskill:latest")

        assert ref.registry == DEFAULT_REGISTRY
        assert ref.namespace == "myorg"
        assert ref.name == "myskill"
        assert ref.tag == "latest"

    def test_from_string_default_tag(self) -> None:
        """Should use 'latest' for references without tag."""
        ref = OCISkillReference.from_string("ghcr.io/org/skill")

        assert ref.tag == DEFAULT_TAG

    def test_from_string_simple_name(self) -> None:
        """Should handle simple name (like 'alpine')."""
        ref = OCISkillReference.from_string("alpine")

        assert ref.registry == DEFAULT_REGISTRY
        assert ref.namespace == "library"
        assert ref.name == "alpine"
        assert ref.tag == DEFAULT_TAG

    def test_from_string_localhost(self) -> None:
        """Should recognize localhost as registry."""
        ref = OCISkillReference.from_string("localhost/myskill:v1")

        assert ref.registry == "localhost"
        assert ref.namespace == ""
        assert ref.name == "myskill"
        assert ref.tag == "v1"

    def test_from_string_empty_raises(self) -> None:
        """Should raise ValueError for empty reference."""
        with pytest.raises(ValueError, match="cannot be empty"):
            OCISkillReference.from_string("")

    def test_from_string_whitespace_only_raises(self) -> None:
        """Should raise ValueError for whitespace-only reference."""
        with pytest.raises(ValueError, match="cannot be empty"):
            OCISkillReference.from_string("   ")

    def test_repository_property(self) -> None:
        """Should return correct repository path."""
        ref = OCISkillReference.from_string("ghcr.io/org/name:v1")

        assert ref.repository == "org/name"

    def test_repository_property_no_namespace(self) -> None:
        """Should return just name when no namespace."""
        ref = OCISkillReference(
            registry="localhost", namespace="", name="skill", tag="v1"
        )

        assert ref.repository == "skill"

    def test_full_ref_property(self) -> None:
        """Should return full reference string."""
        ref = OCISkillReference.from_string("ghcr.io/org/skill:v1.0.0")

        assert ref.full_ref == "ghcr.io/org/skill:v1.0.0"

    def test_str_returns_full_ref(self) -> None:
        """Should return full_ref from __str__."""
        ref = OCISkillReference.from_string("ghcr.io/org/skill:v1")

        assert str(ref) == ref.full_ref


class TestSkillConfig:
    """Tests for SkillConfig.from_labels."""

    def test_from_labels_minimal(self) -> None:
        """Should parse minimal required labels."""
        labels = {
            LABEL_SKILL_NAME: "test-skill",
            LABEL_SKILL_DESCRIPTION: "A test skill",
        }

        config = SkillConfig.from_labels(labels)

        assert config.name == "test-skill"
        assert config.description == "A test skill"
        assert config.version is None
        assert config.license is None
        assert config.allowed_tools == []
        assert config.files == []

    def test_from_labels_with_all_fields(self) -> None:
        """Should parse all labels."""
        labels = {
            LABEL_SKILL_NAME: "full-skill",
            LABEL_SKILL_DESCRIPTION: "A fully configured skill",
            "org.stacklok.skillet.version": "1.0.0",
            "org.stacklok.skillet.license": "MIT",
            "org.stacklok.skillet.allowedTools": '["Bash", "Read"]',
            "org.stacklok.skillet.files": '["SKILL.md", "scripts/run.py"]',
        }

        config = SkillConfig.from_labels(labels)

        assert config.name == "full-skill"
        assert config.description == "A fully configured skill"
        assert config.version == "1.0.0"
        assert config.license == "MIT"
        assert config.allowed_tools == ["Bash", "Read"]
        assert config.files == ["SKILL.md", "scripts/run.py"]

    def test_from_labels_missing_name_raises(self) -> None:
        """Should raise ValueError when name is missing."""
        labels = {LABEL_SKILL_DESCRIPTION: "No name"}

        with pytest.raises(ValueError, match="Missing required label"):
            SkillConfig.from_labels(labels)

    def test_from_labels_missing_description_raises(self) -> None:
        """Should raise ValueError when description is missing."""
        labels = {LABEL_SKILL_NAME: "no-desc"}

        with pytest.raises(ValueError, match="Missing required label"):
            SkillConfig.from_labels(labels)

    def test_from_labels_invalid_json_raises(self) -> None:
        """Should raise ValueError for invalid JSON in arrays."""
        labels = {
            LABEL_SKILL_NAME: "bad-json",
            LABEL_SKILL_DESCRIPTION: "Has bad JSON",
            "org.stacklok.skillet.allowedTools": "not valid json",
        }

        with pytest.raises(ValueError, match="Invalid JSON"):
            SkillConfig.from_labels(labels)


class TestOCIAuthConfig:
    """Tests for OCIAuthConfig."""

    def test_is_anonymous_true(self) -> None:
        """Should be anonymous when no credentials."""
        config = OCIAuthConfig(registry="ghcr.io")

        assert config.is_anonymous is True

    def test_is_anonymous_false_with_username(self) -> None:
        """Should not be anonymous with username."""
        config = OCIAuthConfig(registry="ghcr.io", username="user")

        assert config.is_anonymous is False

    def test_is_anonymous_false_with_password(self) -> None:
        """Should not be anonymous with password."""
        config = OCIAuthConfig(registry="ghcr.io", password="secret")  # noqa: S106

        assert config.is_anonymous is False


class TestOCIRepositoryConfig:
    """Tests for OCIRepositoryConfig."""

    def test_default_cache_dir(self) -> None:
        """Should return sensible default cache directory."""
        cache_dir = OCIRepositoryConfig.default_cache_dir()

        assert cache_dir.name == "oci"
        assert "skills-mcp" in str(cache_dir)
        assert ".cache" in str(cache_dir)

    def test_empty_config(self) -> None:
        """Should create empty config with defaults."""
        config = OCIRepositoryConfig()

        assert config.skills == []
        assert config.auth == {}
        assert config.cache_dir is None
        assert config.cache_ttl == 3600
        assert config.verify_tls is True


class TestOCIPlatform:
    """Tests for OCIPlatform.from_dict."""

    def test_from_dict_full(self) -> None:
        """Should parse platform with all fields."""
        data = {"architecture": "amd64", "os": "linux"}

        platform = OCIPlatform.from_dict(data)

        assert platform.architecture == "amd64"
        assert platform.os == "linux"

    def test_from_dict_empty(self) -> None:
        """Should handle empty dict with defaults."""
        platform = OCIPlatform.from_dict({})

        assert platform.architecture == ""
        assert platform.os == ""

    def test_from_dict_extra_fields_ignored(self) -> None:
        """Should ignore extra fields."""
        data = {
            "architecture": "arm64",
            "os": "linux",
            "variant": "v8",
            "os.version": "1.0",
        }

        platform = OCIPlatform.from_dict(data)

        assert platform.architecture == "arm64"
        assert platform.os == "linux"


class TestOCIDescriptor:
    """Tests for OCIDescriptor.from_dict."""

    def test_from_dict_minimal(self) -> None:
        """Should parse descriptor with minimal fields."""
        data = {
            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
            "digest": "sha256:abc123",
            "size": 1024,
        }

        desc = OCIDescriptor.from_dict(data)

        assert desc.media_type == "application/vnd.oci.image.layer.v1.tar+gzip"
        assert desc.digest == "sha256:abc123"
        assert desc.size == 1024
        assert desc.annotations == {}
        assert desc.platform is None

    def test_from_dict_with_annotations(self) -> None:
        """Should parse descriptor with annotations."""
        data = {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": "sha256:def456",
            "size": 2048,
            "annotations": {
                "org.opencontainers.image.created": "2025-01-07T10:00:00Z",
            },
        }

        desc = OCIDescriptor.from_dict(data)

        assert desc.annotations == {
            "org.opencontainers.image.created": "2025-01-07T10:00:00Z"
        }

    def test_from_dict_with_platform(self) -> None:
        """Should parse descriptor with platform."""
        data = {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": "sha256:ghi789",
            "size": 4096,
            "platform": {"architecture": "amd64", "os": "linux"},
        }

        desc = OCIDescriptor.from_dict(data)

        assert desc.platform is not None
        assert desc.platform.architecture == "amd64"
        assert desc.platform.os == "linux"

    def test_from_dict_empty(self) -> None:
        """Should handle empty dict with defaults."""
        desc = OCIDescriptor.from_dict({})

        assert desc.media_type == ""
        assert desc.digest == ""
        assert desc.size == 0


class TestOCIImageIndex:
    """Tests for OCIImageIndex.from_dict."""

    def test_from_dict_minimal(self) -> None:
        """Should parse minimal image index."""
        data = {
            "schemaVersion": 2,
            "mediaType": MEDIA_TYPE_IMAGE_INDEX,
            "manifests": [],
        }

        index = OCIImageIndex.from_dict(data)

        assert index.schema_version == 2
        assert index.media_type == MEDIA_TYPE_IMAGE_INDEX
        assert index.manifests == []
        assert index.artifact_type is None
        assert index.annotations == {}

    def test_from_dict_with_manifests(self) -> None:
        """Should parse index with manifest descriptors."""
        data = {
            "schemaVersion": 2,
            "mediaType": MEDIA_TYPE_IMAGE_INDEX,
            "manifests": [
                {
                    "mediaType": MEDIA_TYPE_IMAGE_MANIFEST,
                    "digest": "sha256:manifest1",
                    "size": 1024,
                    "platform": {"architecture": "amd64", "os": "linux"},
                },
                {
                    "mediaType": MEDIA_TYPE_IMAGE_MANIFEST,
                    "digest": "sha256:manifest2",
                    "size": 1024,
                    "platform": {"architecture": "arm64", "os": "linux"},
                },
            ],
        }

        index = OCIImageIndex.from_dict(data)

        assert len(index.manifests) == 2
        assert index.manifests[0].digest == "sha256:manifest1"
        assert index.manifests[0].platform.architecture == "amd64"
        assert index.manifests[1].digest == "sha256:manifest2"
        assert index.manifests[1].platform.architecture == "arm64"

    def test_from_dict_with_artifact_type(self) -> None:
        """Should parse index with artifact type."""
        data = {
            "schemaVersion": 2,
            "mediaType": MEDIA_TYPE_IMAGE_INDEX,
            "artifactType": "application/vnd.stacklok.skillet.skill.v1",
            "manifests": [],
            "annotations": {"org.stacklok.skillet.skill.name": "my-skill"},
        }

        index = OCIImageIndex.from_dict(data)

        assert index.artifact_type == "application/vnd.stacklok.skillet.skill.v1"
        assert index.annotations == {"org.stacklok.skillet.skill.name": "my-skill"}

    def test_from_dict_empty_uses_defaults(self) -> None:
        """Should use defaults for empty dict."""
        index = OCIImageIndex.from_dict({})

        assert index.schema_version == 2
        assert index.media_type == MEDIA_TYPE_IMAGE_INDEX
        assert index.manifests == []


class TestOCIImageManifest:
    """Tests for OCIImageManifest.from_dict."""

    def test_from_dict_minimal(self) -> None:
        """Should parse minimal manifest."""
        data = {
            "schemaVersion": 2,
            "mediaType": MEDIA_TYPE_IMAGE_MANIFEST,
            "config": {
                "mediaType": MEDIA_TYPE_IMAGE_CONFIG,
                "digest": "sha256:config123",
                "size": 512,
            },
            "layers": [],
        }

        manifest = OCIImageManifest.from_dict(data)

        assert manifest.schema_version == 2
        assert manifest.media_type == MEDIA_TYPE_IMAGE_MANIFEST
        assert manifest.config.digest == "sha256:config123"
        assert manifest.layers == []
        assert manifest.artifact_type is None

    def test_from_dict_with_layers(self) -> None:
        """Should parse manifest with layers."""
        data = {
            "schemaVersion": 2,
            "mediaType": MEDIA_TYPE_IMAGE_MANIFEST,
            "config": {
                "mediaType": MEDIA_TYPE_IMAGE_CONFIG,
                "digest": "sha256:config456",
                "size": 512,
            },
            "layers": [
                {
                    "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": "sha256:layer1",
                    "size": 10240,
                },
                {
                    "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": "sha256:layer2",
                    "size": 20480,
                },
            ],
        }

        manifest = OCIImageManifest.from_dict(data)

        assert len(manifest.layers) == 2
        assert manifest.layers[0].digest == "sha256:layer1"
        assert manifest.layers[1].digest == "sha256:layer2"

    def test_from_dict_with_artifact_type_and_annotations(self) -> None:
        """Should parse manifest with artifact type and annotations."""
        data = {
            "schemaVersion": 2,
            "mediaType": MEDIA_TYPE_IMAGE_MANIFEST,
            "artifactType": "application/vnd.stacklok.skillet.skill.v1",
            "config": {
                "mediaType": MEDIA_TYPE_IMAGE_CONFIG,
                "digest": "sha256:config789",
                "size": 512,
            },
            "layers": [],
            "annotations": {
                "org.stacklok.skillet.skill.name": "data-analysis",
                "org.stacklok.skillet.skill.version": "1.0.0",
            },
        }

        manifest = OCIImageManifest.from_dict(data)

        assert manifest.artifact_type == "application/vnd.stacklok.skillet.skill.v1"
        skill_name = manifest.annotations["org.stacklok.skillet.skill.name"]
        assert skill_name == "data-analysis"

    def test_from_dict_empty_uses_defaults(self) -> None:
        """Should use defaults for empty dict."""
        manifest = OCIImageManifest.from_dict({})

        assert manifest.schema_version == 2
        assert manifest.media_type == MEDIA_TYPE_IMAGE_MANIFEST
        assert manifest.config.digest == ""
        assert manifest.layers == []


class TestOCIImageConfig:
    """Tests for OCIImageConfig.from_dict."""

    def test_from_dict_minimal(self) -> None:
        """Should parse minimal config."""
        data = {
            "architecture": "amd64",
            "os": "linux",
        }

        config = OCIImageConfig.from_dict(data)

        assert config.architecture == "amd64"
        assert config.os == "linux"
        assert config.labels == {}
        assert config.rootfs_diff_ids == []

    def test_from_dict_with_labels(self) -> None:
        """Should parse config with labels."""
        data = {
            "architecture": "amd64",
            "os": "linux",
            "config": {
                "Labels": {
                    "org.stacklok.skillet.name": "my-skill",
                    "org.stacklok.skillet.description": "A test skill",
                }
            },
        }

        config = OCIImageConfig.from_dict(data)

        assert config.labels["org.stacklok.skillet.name"] == "my-skill"
        assert config.labels["org.stacklok.skillet.description"] == "A test skill"

    def test_from_dict_with_rootfs(self) -> None:
        """Should parse config with rootfs diff_ids."""
        data = {
            "architecture": "arm64",
            "os": "linux",
            "rootfs": {
                "type": "layers",
                "diff_ids": [
                    "sha256:abc123",
                    "sha256:def456",
                ],
            },
        }

        config = OCIImageConfig.from_dict(data)

        assert config.rootfs_diff_ids == ["sha256:abc123", "sha256:def456"]

    def test_from_dict_handles_null_labels(self) -> None:
        """Should handle null Labels gracefully."""
        data = {
            "architecture": "amd64",
            "os": "linux",
            "config": {
                "Labels": None,
            },
        }

        config = OCIImageConfig.from_dict(data)

        assert config.labels == {}

    def test_from_dict_empty_uses_defaults(self) -> None:
        """Should use defaults for empty dict."""
        config = OCIImageConfig.from_dict({})

        assert config.architecture == ""
        assert config.os == ""
        assert config.labels == {}
        assert config.rootfs_diff_ids == []

    def test_from_dict_full_skill_config(self) -> None:
        """Should parse full skill configuration as produced by skillet."""
        data = {
            "architecture": "amd64",
            "os": "linux",
            "config": {
                "Labels": {
                    "org.stacklok.skillet.name": "data-analysis",
                    "org.stacklok.skillet.description": "Analyze data using Python",
                    "org.stacklok.skillet.version": "1.0.0",
                    "org.stacklok.skillet.license": "MIT",
                    "org.stacklok.skillet.allowedTools": '["Bash", "Read"]',
                    "org.stacklok.skillet.files": '["SKILL.md", "scripts/analyze.py"]',
                }
            },
            "rootfs": {
                "type": "layers",
                "diff_ids": ["sha256:abc123"],
            },
        }

        config = OCIImageConfig.from_dict(data)

        assert config.labels["org.stacklok.skillet.name"] == "data-analysis"
        assert config.labels["org.stacklok.skillet.version"] == "1.0.0"
        assert len(config.rootfs_diff_ids) == 1

        # Verify labels can be parsed by SkillConfig
        skill = SkillConfig.from_labels(config.labels)
        assert skill.name == "data-analysis"
        assert skill.allowed_tools == ["Bash", "Read"]
