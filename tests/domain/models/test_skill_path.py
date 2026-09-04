"""Tests for canonical skill path identity."""

import pytest

from skills_mcp.domain.models.skill_path import SkillPath


def test_skill_path_retains_only_normalized_domain_identity() -> None:
    """Domain identity contains no MCP URI construction behavior."""
    path = SkillPath("team tools/review-skill")
    assert path.value == "team tools/review-skill"
    assert not hasattr(path, "skill_uri")


@pytest.mark.parametrize(
    "value",
    ["", "/absolute", "../escape", "a/../b", "a\\b", "a/", "./a"],
)
def test_skill_path_invalid_relative_path_rejected(value: str) -> None:
    """Traversal and non-normalized path forms are rejected."""
    with pytest.raises(ValueError):
        SkillPath(value)
