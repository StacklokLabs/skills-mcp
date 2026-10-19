"""Tests for ManifestParser service."""

import pytest

from skills_mcp.domain.exceptions import ManifestParseError, MissingRequiredFieldError
from skills_mcp.domain.services.manifest_parser import ManifestParser


class TestManifestParserParseContent:
    """Tests for ManifestParser.parse_content method."""

    def test_parse_minimal_manifest(self) -> None:
        """Should parse minimal valid manifest."""
        content = """---
name: my-skill
description: A simple skill
---

# Instructions

Do something useful.
"""
        parser = ManifestParser()
        manifest, body = parser.parse_content(content)

        assert manifest.name.value == "my-skill"
        assert manifest.description == "A simple skill"
        assert "Instructions" in body

    def test_parse_full_manifest(self) -> None:
        """Should parse manifest with all fields."""
        content = """---
name: data-analysis
description: Analyze data from various sources
license: MIT
compatibility: claude-3
metadata:
  author: test-author
  version: "1.0"
allowed-tools: Read Write Bash
---

# Data Analysis

Detailed instructions here.
"""
        parser = ManifestParser()
        manifest, body = parser.parse_content(content)

        assert manifest.name.value == "data-analysis"
        assert manifest.description == "Analyze data from various sources"
        assert manifest.license == "MIT"
        assert manifest.compatibility == "claude-3"
        assert manifest.metadata["author"] == "test-author"
        assert manifest.metadata["version"] == "1.0"
        assert manifest.allowed_tools == ["Read", "Write", "Bash"]
        assert "Data Analysis" in body

    def test_parse_allowed_tools_list_format(self) -> None:
        """Should parse allowed-tools as list format."""
        content = """---
name: my-skill
description: Test skill
allowed-tools:
  - Read
  - Write
  - Bash
---

Body
"""
        parser = ManifestParser()
        manifest, _ = parser.parse_content(content)
        assert manifest.allowed_tools == ["Read", "Write", "Bash"]

    def test_parse_allowed_tools_underscore_variant(self) -> None:
        """Should parse allowed_tools with underscore."""
        content = """---
name: my-skill
description: Test skill
allowed_tools: Read Write
---

Body
"""
        parser = ManifestParser()
        manifest, _ = parser.parse_content(content)
        assert manifest.allowed_tools == ["Read", "Write"]

    def test_missing_name_raises_error(self) -> None:
        """Should raise MissingRequiredFieldError for missing name."""
        content = """---
description: A skill without a name
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(MissingRequiredFieldError) as exc_info:
            parser.parse_content(content)
        assert "name" in str(exc_info.value)

    def test_missing_description_raises_error(self) -> None:
        """Should raise MissingRequiredFieldError for missing description."""
        content = """---
name: my-skill
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(MissingRequiredFieldError) as exc_info:
            parser.parse_content(content)
        assert "description" in str(exc_info.value)

    def test_invalid_name_type_raises_error(self) -> None:
        """Should raise ManifestParseError for non-string name."""
        content = """---
name: 123
description: A skill
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(ManifestParseError) as exc_info:
            parser.parse_content(content)
        assert "string" in str(exc_info.value).lower()

    def test_invalid_name_format_raises_error(self) -> None:
        """Should raise ManifestParseError for invalid name format."""
        content = """---
name: Invalid_Name
description: A skill
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(ManifestParseError):
            parser.parse_content(content)

    def test_invalid_description_type_raises_error(self) -> None:
        """Should raise ManifestParseError for non-string description."""
        content = """---
name: my-skill
description:
  - item1
  - item2
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(ManifestParseError) as exc_info:
            parser.parse_content(content)
        assert "string" in str(exc_info.value).lower()

    def test_invalid_metadata_type_raises_error(self) -> None:
        """Should raise ManifestParseError for non-dict metadata."""
        content = """---
name: my-skill
description: A skill
metadata: not-a-dict
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(ManifestParseError) as exc_info:
            parser.parse_content(content)
        assert "mapping" in str(exc_info.value).lower()

    def test_invalid_allowed_tools_type_raises_error(self) -> None:
        """Should raise ManifestParseError for invalid allowed-tools type."""
        content = """---
name: my-skill
description: A skill
allowed-tools:
  key: value
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(ManifestParseError) as exc_info:
            parser.parse_content(content)
        assert "allowed-tools" in str(exc_info.value).lower()

    def test_invalid_yaml_raises_error(self) -> None:
        """Should raise ManifestParseError for invalid YAML."""
        content = """---
name: [invalid yaml
description: A skill
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(ManifestParseError) as exc_info:
            parser.parse_content(content)
        assert "frontmatter" in str(exc_info.value).lower()

    def test_no_frontmatter_raises_error(self) -> None:
        """Should raise MissingRequiredFieldError for content without frontmatter."""
        content = """# Just markdown

No frontmatter here.
"""
        parser = ManifestParser()
        with pytest.raises(MissingRequiredFieldError):
            parser.parse_content(content)

    def test_empty_frontmatter_raises_error(self) -> None:
        """Should raise MissingRequiredFieldError for empty frontmatter."""
        content = """---
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(MissingRequiredFieldError):
            parser.parse_content(content)

    def test_null_optional_fields_are_none(self) -> None:
        """Null optional fields should be None."""
        content = """---
name: my-skill
description: A skill
license: ~
compatibility: null
---

Body
"""
        parser = ManifestParser()
        manifest, _ = parser.parse_content(content)
        assert manifest.license is None
        assert manifest.compatibility is None

    def test_null_metadata_returns_empty_dict(self) -> None:
        """Null metadata should return empty dict."""
        content = """---
name: my-skill
description: A skill
metadata: ~
---

Body
"""
        parser = ManifestParser()
        manifest, _ = parser.parse_content(content)
        assert manifest.metadata == {}

    def test_metadata_normalizes_strings_and_raw_frontmatter_preserves_types(
        self,
    ) -> None:
        """Compatibility metadata stays string-valued while raw data is typed."""
        content = """---
name: my-skill
description: A skill
metadata:
  number: 42
  boolean: true
  float: 3.14
---

Body
"""
        parser = ManifestParser()
        manifest, _ = parser.parse_content(content)
        assert manifest.metadata == {
            "number": "42",
            "boolean": "True",
            "float": "3.14",
        }
        assert manifest.raw_frontmatter["metadata"] == {
            "number": 42,
            "boolean": True,
            "float": 3.14,
        }

    def test_alias_amplification_is_rejected_before_yaml_conversion(self) -> None:
        """Anchors and aliases cannot amplify a small manifest during parsing."""
        aliases = ", ".join("*item" for _ in range(1000))
        content = (
            "---\nname: alias-skill\ndescription: test\n"
            f"item: &item [one, two, three]\nexpanded: [{aliases}]\n---\nBody\n"
        )

        with pytest.raises(ManifestParseError, match="aliases and anchors"):
            ManifestParser().parse_content(content)

    def test_source_in_error_message(self) -> None:
        """Source identifier should appear in error messages."""
        content = """---
description: Missing name
---

Body
"""
        parser = ManifestParser()
        with pytest.raises(MissingRequiredFieldError) as exc_info:
            parser.parse_content(content, source="test-file.md")
        assert "test-file.md" in str(exc_info.value)
