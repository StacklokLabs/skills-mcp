"""Tests for SkillResource model."""

from pathlib import Path

import pytest

from skills_mcp.domain.models.resource import ResourceType, SkillResource


class TestResourceType:
    """Tests for ResourceType enum."""

    def test_script_value(self) -> None:
        """SCRIPT should have 'scripts' value."""
        assert ResourceType.SCRIPT.value == "scripts"

    def test_reference_value(self) -> None:
        """REFERENCE should have 'references' value."""
        assert ResourceType.REFERENCE.value == "references"

    def test_asset_value(self) -> None:
        """ASSET should have 'assets' value."""
        assert ResourceType.ASSET.value == "assets"

    def test_from_path_script(self) -> None:
        """Should detect script from path."""
        path = Path("/skills/my-skill/scripts/analyze.py")
        assert ResourceType.from_path(path) == ResourceType.SCRIPT

    def test_from_path_reference(self) -> None:
        """Should detect reference from path."""
        path = Path("/skills/my-skill/references/GUIDE.md")
        assert ResourceType.from_path(path) == ResourceType.REFERENCE

    def test_from_path_asset(self) -> None:
        """Should detect asset from path."""
        path = Path("/skills/my-skill/assets/template.json")
        assert ResourceType.from_path(path) == ResourceType.ASSET

    def test_from_path_unknown(self) -> None:
        """Should return None for unrecognized paths."""
        path = Path("/skills/my-skill/other/file.txt")
        assert ResourceType.from_path(path) is None


class TestSkillResource:
    """Tests for SkillResource dataclass."""

    def test_create_script_resource(self) -> None:
        """Should create a script resource."""
        resource = SkillResource(
            name="analyze.py",
            path=Path("/skills/my-skill/scripts/analyze.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=500,
        )
        assert resource.name == "analyze.py"
        assert resource.resource_type == ResourceType.SCRIPT
        assert resource.token_count == 500

    def test_from_path_creates_resource(self) -> None:
        """from_path should create resource correctly."""
        path = Path("/skills/my-skill/scripts/analyze.py")
        resource = SkillResource.from_path(path, token_count=500)
        assert resource.name == "analyze.py"
        assert resource.path == path
        assert resource.resource_type == ResourceType.SCRIPT
        assert resource.token_count == 500

    def test_from_path_invalid_directory(self) -> None:
        """from_path should raise for invalid directory."""
        path = Path("/skills/my-skill/other/file.txt")
        with pytest.raises(ValueError) as exc_info:
            SkillResource.from_path(path, token_count=100)
        assert "not in a recognized resource directory" in str(exc_info.value)

    def test_uri_path_for_script(self) -> None:
        """uri_path should return correct path for script."""
        resource = SkillResource(
            name="analyze.py",
            path=Path("/skills/my-skill/scripts/analyze.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=500,
        )
        assert resource.uri_path == "scripts/analyze.py"

    def test_uri_path_for_reference(self) -> None:
        """uri_path should return correct path for reference."""
        resource = SkillResource(
            name="GUIDE.md",
            path=Path("/skills/my-skill/references/GUIDE.md"),
            resource_type=ResourceType.REFERENCE,
            token_count=1200,
        )
        assert resource.uri_path == "references/GUIDE.md"

    def test_uri_path_for_asset(self) -> None:
        """uri_path should return correct path for asset."""
        resource = SkillResource(
            name="config.json",
            path=Path("/skills/my-skill/assets/config.json"),
            resource_type=ResourceType.ASSET,
            token_count=100,
        )
        assert resource.uri_path == "assets/config.json"

    def test_str_representation(self) -> None:
        """str should include type, name and tokens."""
        resource = SkillResource(
            name="analyze.py",
            path=Path("/skills/my-skill/scripts/analyze.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=500,
        )
        s = str(resource)
        assert "scripts/analyze.py" in s
        assert "500" in s
        assert "tokens" in s

    def test_immutable(self) -> None:
        """SkillResource should be immutable (frozen)."""
        resource = SkillResource(
            name="analyze.py",
            path=Path("/skills/my-skill/scripts/analyze.py"),
            resource_type=ResourceType.SCRIPT,
            token_count=500,
        )
        with pytest.raises(AttributeError):
            resource.name = "other.py"  # type: ignore[misc]
