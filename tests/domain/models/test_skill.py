"""Tests for Skill aggregate model."""

from pathlib import Path

from skills_mcp.domain.models.manifest import SkillManifest
from skills_mcp.domain.models.resource import ResourceType, SkillResource
from skills_mcp.domain.models.skill import Skill
from skills_mcp.domain.models.skill_name import SkillName


def create_test_manifest(name: str = "test-skill") -> SkillManifest:
    """Create a test manifest with minimal fields."""
    return SkillManifest(
        name=SkillName(name),
        description="A test skill description",
    )


def create_test_resource(
    name: str, resource_type: ResourceType, token_count: int = 100
) -> SkillResource:
    """Create a test resource."""
    return SkillResource(
        name=name,
        path=Path(f"/test/{name}"),
        resource_type=resource_type,
        token_count=token_count,
    )


class TestSkillCreation:
    """Tests for Skill creation."""

    def test_create_minimal_skill(self, tmp_path: Path) -> None:
        """Should create skill with only required fields."""
        skill = Skill(
            manifest=create_test_manifest(),
            body="# Test Skill\n\nInstructions here",
            path=tmp_path,
        )

        assert skill.name.value == "test-skill"
        assert skill.body == "# Test Skill\n\nInstructions here"
        assert skill.path == tmp_path
        assert skill.scripts == []
        assert skill.references == []
        assert skill.assets == []
        assert skill.token_count == 0

    def test_create_skill_with_resources(self, tmp_path: Path) -> None:
        """Should create skill with resources."""
        scripts = [create_test_resource("script.py", ResourceType.SCRIPT, 100)]
        references = [create_test_resource("guide.md", ResourceType.REFERENCE, 200)]
        assets = [create_test_resource("config.json", ResourceType.ASSET, 50)]

        skill = Skill(
            manifest=create_test_manifest(),
            body="# Test Skill",
            path=tmp_path,
            scripts=scripts,
            references=references,
            assets=assets,
            token_count=500,
        )

        assert len(skill.scripts) == 1
        assert len(skill.references) == 1
        assert len(skill.assets) == 1
        assert skill.token_count == 500

    def test_legacy_positional_constructor_order_is_preserved(
        self, tmp_path: Path
    ) -> None:
        """New snapshot fields do not shift established positional arguments."""
        scripts = [create_test_resource("script.py", ResourceType.SCRIPT)]
        skill = Skill(
            create_test_manifest(),
            "body",
            tmp_path,
            scripts,
            [],
            [],
            123,
            None,
        )

        assert skill.scripts is scripts
        assert skill.token_count == 123
        assert skill.skill_path is not None


class TestSkillProperties:
    """Tests for Skill properties."""

    def test_name_property(self, tmp_path: Path) -> None:
        """Should return name from manifest."""
        skill = Skill(
            manifest=create_test_manifest("my-skill"),
            body="body",
            path=tmp_path,
        )

        assert skill.name.value == "my-skill"

    def test_description_property(self, tmp_path: Path) -> None:
        """Should return description from manifest."""
        skill = Skill(
            manifest=create_test_manifest(),
            body="body",
            path=tmp_path,
        )

        assert skill.description == "A test skill description"

    def test_all_resources_property(self, tmp_path: Path) -> None:
        """Should return all resources combined."""
        scripts = [create_test_resource("script.py", ResourceType.SCRIPT)]
        references = [create_test_resource("guide.md", ResourceType.REFERENCE)]
        assets = [
            create_test_resource("a.json", ResourceType.ASSET),
            create_test_resource("b.json", ResourceType.ASSET),
        ]

        skill = Skill(
            manifest=create_test_manifest(),
            body="body",
            path=tmp_path,
            scripts=scripts,
            references=references,
            assets=assets,
        )

        all_resources = skill.all_resources
        assert len(all_resources) == 4
        assert scripts[0] in all_resources
        assert references[0] in all_resources
        assert assets[0] in all_resources
        assert assets[1] in all_resources

    def test_total_resource_tokens(self, tmp_path: Path) -> None:
        """Should return sum of all resource token counts."""
        skill = Skill(
            manifest=create_test_manifest(),
            body="body",
            path=tmp_path,
            scripts=[create_test_resource("s.py", ResourceType.SCRIPT, 100)],
            references=[create_test_resource("r.md", ResourceType.REFERENCE, 200)],
            assets=[create_test_resource("a.json", ResourceType.ASSET, 50)],
        )

        assert skill.total_resource_tokens == 350


class TestSkillGetResource:
    """Tests for get_resource method."""

    def test_get_existing_script(self, tmp_path: Path) -> None:
        """Should find existing script by name."""
        script = create_test_resource("analyze.py", ResourceType.SCRIPT)
        skill = Skill(
            manifest=create_test_manifest(),
            body="body",
            path=tmp_path,
            scripts=[script],
        )

        found = skill.get_resource(ResourceType.SCRIPT, "analyze.py")

        assert found is script

    def test_get_existing_reference(self, tmp_path: Path) -> None:
        """Should find existing reference by name."""
        reference = create_test_resource("guide.md", ResourceType.REFERENCE)
        skill = Skill(
            manifest=create_test_manifest(),
            body="body",
            path=tmp_path,
            references=[reference],
        )

        found = skill.get_resource(ResourceType.REFERENCE, "guide.md")

        assert found is reference

    def test_get_existing_asset(self, tmp_path: Path) -> None:
        """Should find existing asset by name."""
        asset = create_test_resource("config.json", ResourceType.ASSET)
        skill = Skill(
            manifest=create_test_manifest(),
            body="body",
            path=tmp_path,
            assets=[asset],
        )

        found = skill.get_resource(ResourceType.ASSET, "config.json")

        assert found is asset

    def test_get_nonexistent_resource(self, tmp_path: Path) -> None:
        """Should return None for nonexistent resource."""
        skill = Skill(
            manifest=create_test_manifest(),
            body="body",
            path=tmp_path,
            scripts=[create_test_resource("other.py", ResourceType.SCRIPT)],
        )

        found = skill.get_resource(ResourceType.SCRIPT, "nonexistent.py")

        assert found is None

    def test_get_wrong_type(self, tmp_path: Path) -> None:
        """Should return None when resource exists but type is wrong."""
        skill = Skill(
            manifest=create_test_manifest(),
            body="body",
            path=tmp_path,
            scripts=[create_test_resource("analyze.py", ResourceType.SCRIPT)],
        )

        # Looking for analyze.py as reference, not script
        found = skill.get_resource(ResourceType.REFERENCE, "analyze.py")

        assert found is None


class TestSkillToMetadataDict:
    """Tests for to_metadata_dict method."""

    def test_returns_only_name_and_description(self, tmp_path: Path) -> None:
        """Should return only name and description (Tier 1)."""
        skill = Skill(
            manifest=create_test_manifest("my-skill"),
            body="Full body content here",
            path=tmp_path,
            scripts=[create_test_resource("s.py", ResourceType.SCRIPT)],
            token_count=1000,
        )

        result = skill.to_metadata_dict()

        assert result == {
            "name": "my-skill",
            "description": "A test skill description",
        }
        # Should NOT include body or resources
        assert "body" not in result
        assert "scripts" not in result
        assert "token_count" not in result


class TestSkillToInstructionsDict:
    """Tests for to_instructions_dict method."""

    def test_returns_full_instructions(self, tmp_path: Path) -> None:
        """Should return full instructions (Tier 2)."""
        skill = Skill(
            manifest=create_test_manifest("my-skill"),
            body="# Full Instructions",
            path=tmp_path,
            scripts=[create_test_resource("analyze.py", ResourceType.SCRIPT, 100)],
            references=[create_test_resource("guide.md", ResourceType.REFERENCE, 200)],
            assets=[create_test_resource("config.json", ResourceType.ASSET, 50)],
            token_count=500,
        )

        result = skill.to_instructions_dict()

        assert result["name"] == "my-skill"
        assert result["description"] == "A test skill description"
        assert result["body"] == "# Full Instructions"
        assert result["token_count"] == 500
        assert result["resources"] == {
            "scripts": [{"name": "analyze.py", "tokens": 100}],
            "references": [{"name": "guide.md", "tokens": 200}],
            "assets": [{"name": "config.json", "tokens": 50}],
        }

    def test_empty_resources_list(self, tmp_path: Path) -> None:
        """Should include empty lists for resources."""
        skill = Skill(
            manifest=create_test_manifest(),
            body="body",
            path=tmp_path,
        )

        result = skill.to_instructions_dict()

        assert result["resources"] == {
            "scripts": [],
            "references": [],
            "assets": [],
        }
