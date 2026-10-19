"""Manifest parser service for SKILL.md files.

Parses SKILL.md files with YAML frontmatter and markdown body
following the Agent Skills specification.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import frontmatter
import yaml
from yaml.tokens import AliasToken, AnchorToken

from skills_mcp.domain.exceptions import ManifestParseError, MissingRequiredFieldError
from skills_mcp.domain.models.manifest import SkillManifest
from skills_mcp.domain.models.skill_name import SkillName


if TYPE_CHECKING:
    from pathlib import Path


MAX_FRONTMATTER_BYTES = 1024 * 1024


class ManifestParser:
    """Service for parsing SKILL.md files.

    Parses the YAML frontmatter and markdown body from SKILL.md files,
    validating against the Agent Skills specification.

    Example:
        parser = ManifestParser()
        manifest, body = parser.parse_file(Path("./my-skill/SKILL.md"))
    """

    def parse_file(self, path: Path) -> tuple[SkillManifest, str]:
        """Parse a SKILL.md file from disk.

        Args:
            path: Path to the SKILL.md file.

        Returns:
            Tuple of (SkillManifest, body_content).

        Raises:
            ManifestParseError: If the file cannot be parsed.
            MissingRequiredFieldError: If required fields are missing.
        """
        try:
            content = path.read_bytes()
        except OSError as e:
            raise ManifestParseError(str(path), f"cannot read file: {e}") from e

        return self.parse_bytes(content, str(path))

    def parse_bytes(
        self, content: bytes, source: str = "<bytes>"
    ) -> tuple[SkillManifest, str]:
        """Parse exact UTF-8 ``SKILL.md`` bytes.

        Args:
            content: Complete manifest file bytes.
            source: Source identifier for error messages.

        Returns:
            Tuple of parsed manifest and Markdown body.

        Raises:
            ManifestParseError: If bytes are not UTF-8 or frontmatter is unsafe.
            MissingRequiredFieldError: If required fields are missing.
        """
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ManifestParseError(source, "SKILL.md must be UTF-8") from exc
        return self.parse_content(text, source)

    def parse_content(
        self, content: str, source: str = "<string>"
    ) -> tuple[SkillManifest, str]:
        """Parse SKILL.md content from a string.

        Args:
            content: The full SKILL.md content with frontmatter.
            source: Source identifier for error messages.

        Returns:
            Tuple of (SkillManifest, body_content).

        Raises:
            ManifestParseError: If the content cannot be parsed.
            MissingRequiredFieldError: If required fields are missing.
        """
        frontmatter_text = self._extract_frontmatter(content, source)
        try:
            if any(
                isinstance(token, (AliasToken, AnchorToken))
                for token in yaml.scan(frontmatter_text)
            ):
                raise ManifestParseError(
                    source, "YAML aliases and anchors are not allowed in frontmatter"
                )
            post = frontmatter.loads(content)
        except ManifestParseError:
            raise
        except Exception as e:
            raise ManifestParseError(source, f"invalid frontmatter: {e}") from e

        metadata = post.metadata
        body = post.content
        try:
            # Round-tripping through JSON both rejects YAML-only values (dates,
            # sets, custom objects) and detaches the preserved frontmatter.
            raw_frontmatter: dict[str, object] = json.loads(
                json.dumps(metadata, allow_nan=False)
            )
            if raw_frontmatter != metadata:
                raise ValueError("frontmatter changes shape when encoded as JSON")
        except (TypeError, ValueError) as exc:
            raise ManifestParseError(
                source, f"frontmatter must contain only JSON-compatible values: {exc}"
            ) from exc

        manifest = self._parse_metadata(metadata, source, raw_frontmatter)
        return manifest, body

    @staticmethod
    def _extract_frontmatter(content: str, source: str) -> str:
        """Extract a bounded YAML frontmatter document before parsing.

        Args:
            content: Complete ``SKILL.md`` text.
            source: Source identifier for errors.

        Returns:
            YAML text between the frontmatter delimiters.

        Raises:
            ManifestParseError: If the frontmatter exceeds the byte limit.
        """
        lines = content.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != "---":
            return ""
        size = 0
        collected: list[str] = []
        for line in lines[1:]:
            if line.rstrip("\r\n") == "---":
                return "".join(collected)
            size += len(line.encode("utf-8"))
            if size > MAX_FRONTMATTER_BYTES:
                raise ManifestParseError(
                    source,
                    f"frontmatter exceeds {MAX_FRONTMATTER_BYTES} bytes",
                )
            collected.append(line)
        return "".join(collected)

    def _parse_metadata(
        self,
        metadata: dict[str, Any],
        source: str,
        raw_frontmatter: dict[str, object],
    ) -> SkillManifest:
        """Parse the frontmatter metadata into a SkillManifest.

        Args:
            metadata: The parsed YAML frontmatter.
            source: Source identifier for error messages.
            raw_frontmatter: Complete JSON-compatible frontmatter as parsed.

        Returns:
            A validated SkillManifest.

        Raises:
            MissingRequiredFieldError: If required fields are missing.
            ManifestParseError: If fields have invalid values.
        """
        # Check required fields
        if "name" not in metadata:
            raise MissingRequiredFieldError(source, "name")
        if "description" not in metadata:
            raise MissingRequiredFieldError(source, "description")

        # Parse name
        name_str = metadata["name"]
        if not isinstance(name_str, str):
            raise ManifestParseError(
                source, f"'name' must be a string, got {type(name_str).__name__}"
            )

        try:
            name = SkillName(name_str)
        except Exception as e:
            raise ManifestParseError(source, str(e)) from e

        # Parse description
        description = metadata["description"]
        if not isinstance(description, str):
            raise ManifestParseError(
                source,
                f"'description' must be a string, got {type(description).__name__}",
            )

        # Parse optional fields
        license_val = self._parse_optional_string(metadata, "license", source)
        compatibility = self._parse_optional_string(metadata, "compatibility", source)
        skill_metadata = self._parse_metadata_field(metadata, source)
        allowed_tools = self._parse_allowed_tools(metadata, source)

        try:
            return SkillManifest(
                name=name,
                description=description,
                license=license_val,
                compatibility=compatibility,
                metadata=skill_metadata,
                allowed_tools=allowed_tools,
                raw_frontmatter=raw_frontmatter,
            )
        except ValueError as e:
            raise ManifestParseError(source, str(e)) from e

    def _parse_optional_string(
        self, metadata: dict[str, Any], field: str, source: str
    ) -> str | None:
        """Parse an optional string field.

        Args:
            metadata: The frontmatter metadata.
            field: The field name to parse.
            source: Source identifier for error messages.

        Returns:
            The string value, or None if not present.

        Raises:
            ManifestParseError: If the field is not a string.
        """
        if field not in metadata:
            return None

        value = metadata[field]
        if value is None:
            return None

        if not isinstance(value, str):
            raise ManifestParseError(
                source, f"'{field}' must be a string, got {type(value).__name__}"
            )

        return value

    def _parse_metadata_field(
        self, metadata: dict[str, Any], source: str
    ) -> dict[str, str]:
        """Parse the optional metadata field.

        Args:
            metadata: The frontmatter metadata.
            source: Source identifier for error messages.

        Returns:
            Dictionary of string key-value pairs.

        Raises:
            ManifestParseError: If metadata is not a valid dict.
        """
        if "metadata" not in metadata:
            return {}

        value = metadata["metadata"]
        if value is None:
            return {}

        if not isinstance(value, dict):
            raise ManifestParseError(
                source, f"'metadata' must be a mapping, got {type(value).__name__}"
            )

        result: dict[str, str] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise ManifestParseError(
                    source, f"metadata keys must be strings, got {type(k).__name__}"
                )
            result[k] = str(v)

        return result

    def _parse_allowed_tools(self, metadata: dict[str, Any], source: str) -> list[str]:
        """Parse the optional allowed-tools field.

        The allowed-tools field is space-delimited in YAML.

        Args:
            metadata: The frontmatter metadata.
            source: Source identifier for error messages.

        Returns:
            List of allowed tool names.

        Raises:
            ManifestParseError: If the field has an invalid format.
        """
        # Check both "allowed-tools" and "allowed_tools" for flexibility
        value = metadata.get("allowed-tools") or metadata.get("allowed_tools")

        if value is None:
            return []

        if isinstance(value, str):
            # Space-delimited string
            return [t.strip() for t in value.split() if t.strip()]

        if isinstance(value, list):
            # Already a list
            result = []
            for item in value:
                if not isinstance(item, str):
                    raise ManifestParseError(
                        source,
                        f"allowed-tools items must be strings, "
                        f"got {type(item).__name__}",
                    )
                result.append(item)
            return result

        raise ManifestParseError(
            source,
            f"'allowed-tools' must be a string or list, got {type(value).__name__}",
        )
