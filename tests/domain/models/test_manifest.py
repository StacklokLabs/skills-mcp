"""Tests for SkillManifest model."""

import pytest

from skills_mcp.domain.models.manifest import (
    MAX_COMPATIBILITY_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    SHORT_DESCRIPTION_ELLIPSIS_LENGTH,
    SHORT_DESCRIPTION_LENGTH,
    SkillManifest,
)
from skills_mcp.domain.models.skill_name import SkillName


class TestSkillManifestCreation:
    """Tests for SkillManifest creation and validation."""

    def test_create_minimal_manifest(self) -> None:
        """Should create manifest with only required fields."""
        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description="A test skill",
        )

        assert manifest.name.value == "test-skill"
        assert manifest.description == "A test skill"
        assert manifest.license is None
        assert manifest.compatibility is None
        assert manifest.metadata == {}
        assert manifest.allowed_tools == []

    def test_create_full_manifest(self) -> None:
        """Should create manifest with all fields."""
        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description="A test skill with all features",
            license="MIT",
            compatibility="Python >= 3.10",
            metadata={"author": "test", "version": "1.0"},
            allowed_tools=["read_file", "write_file"],
        )

        assert manifest.name.value == "test-skill"
        assert manifest.description == "A test skill with all features"
        assert manifest.license == "MIT"
        assert manifest.compatibility == "Python >= 3.10"
        assert manifest.metadata == {"author": "test", "version": "1.0"}
        assert manifest.allowed_tools == ["read_file", "write_file"]

    def test_manifest_is_frozen(self) -> None:
        """Manifest should be immutable."""
        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description="A test skill",
        )

        with pytest.raises(AttributeError):
            manifest.description = "modified"  # type: ignore[misc]


class TestSkillManifestValidation:
    """Tests for SkillManifest field validation."""

    def test_reject_empty_description(self) -> None:
        """Should reject empty description."""
        with pytest.raises(ValueError, match="description cannot be empty"):
            SkillManifest(
                name=SkillName("test-skill"),
                description="",
            )

    def test_reject_description_over_max_length(self) -> None:
        """Should reject description exceeding max length."""
        long_description = "a" * (MAX_DESCRIPTION_LENGTH + 1)

        with pytest.raises(ValueError, match="description exceeds maximum length"):
            SkillManifest(
                name=SkillName("test-skill"),
                description=long_description,
            )

    def test_accept_description_at_max_length(self) -> None:
        """Should accept description exactly at max length."""
        max_description = "a" * MAX_DESCRIPTION_LENGTH

        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description=max_description,
        )

        assert len(manifest.description) == MAX_DESCRIPTION_LENGTH

    def test_reject_compatibility_over_max_length(self) -> None:
        """Should reject compatibility exceeding max length."""
        long_compatibility = "a" * (MAX_COMPATIBILITY_LENGTH + 1)

        with pytest.raises(ValueError, match="compatibility exceeds maximum length"):
            SkillManifest(
                name=SkillName("test-skill"),
                description="A test skill",
                compatibility=long_compatibility,
            )

    def test_accept_compatibility_at_max_length(self) -> None:
        """Should accept compatibility exactly at max length."""
        max_compatibility = "a" * MAX_COMPATIBILITY_LENGTH

        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description="A test skill",
            compatibility=max_compatibility,
        )

        assert len(manifest.compatibility) == MAX_COMPATIBILITY_LENGTH  # type: ignore[arg-type]


class TestSkillManifestShortDescription:
    """Tests for description_short property."""

    def test_short_description_returns_full_when_under_limit(self) -> None:
        """Should return full description when under limit."""
        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description="Short description",
        )

        assert manifest.description_short == "Short description"

    def test_short_description_returns_full_at_exactly_limit(self) -> None:
        """Should return full description at exactly 100 chars."""
        description = "a" * SHORT_DESCRIPTION_LENGTH

        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description=description,
        )

        assert manifest.description_short == description
        assert len(manifest.description_short) == SHORT_DESCRIPTION_LENGTH

    def test_short_description_truncates_over_limit(self) -> None:
        """Should truncate description over 100 chars with ellipsis."""
        description = "a" * (SHORT_DESCRIPTION_LENGTH + 50)

        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description=description,
        )

        expected = "a" * SHORT_DESCRIPTION_ELLIPSIS_LENGTH + "..."
        assert manifest.description_short == expected
        assert len(manifest.description_short) == SHORT_DESCRIPTION_LENGTH


class TestSkillManifestToDict:
    """Tests for to_dict method."""

    def test_to_dict_minimal(self) -> None:
        """Should return dict with only required fields."""
        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description="A test skill",
        )

        result = manifest.to_dict()

        assert result == {
            "name": "test-skill",
            "description": "A test skill",
        }

    def test_to_dict_full(self) -> None:
        """Should return dict with all fields."""
        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description="A test skill",
            license="MIT",
            compatibility="Python >= 3.10",
            metadata={"key": "value"},
            allowed_tools=["tool1"],
        )

        result = manifest.to_dict()

        assert result == {
            "name": "test-skill",
            "description": "A test skill",
            "license": "MIT",
            "compatibility": "Python >= 3.10",
            "metadata": {"key": "value"},
            "allowed_tools": ["tool1"],
        }

    def test_to_dict_excludes_none_fields(self) -> None:
        """Should exclude None optional fields from dict."""
        manifest = SkillManifest(
            name=SkillName("test-skill"),
            description="A test skill",
            license="MIT",  # Only this optional field set
        )

        result = manifest.to_dict()

        assert "license" in result
        assert "compatibility" not in result
        assert "metadata" not in result
        assert "allowed_tools" not in result
