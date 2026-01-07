"""Tests for OCI models."""

import pytest

from skills_mcp.infrastructure.persistence.oci_models import (
    DEFAULT_REGISTRY,
    DEFAULT_TAG,
    LABEL_SKILL_DESCRIPTION,
    LABEL_SKILL_NAME,
    OCIAuthConfig,
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
