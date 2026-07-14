"""Offline integration tests for GitSkillRepository against real dulwich.

These tests build a genuine local Git repository with dulwich and clone it via
a local-path ``url_override`` (which ``from_string`` never produces, so no SSRF
surface is exercised). No network is touched.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
from dulwich import porcelain

from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.infrastructure.persistence.git_models import (
    GitRepositoryConfig,
    GitSkillReference,
)
from skills_mcp.infrastructure.persistence.git_repository import (
    CACHE_COMPLETE_MARKER,
    GitSkillRepository,
)


if TYPE_CHECKING:
    from pathlib import Path


RESOURCE_BYTES = b"#!/usr/bin/env python3\nprint('byte-identical\\x00\\xff')\n"

SKILL_MD = (
    "---\n"
    "name: demo\n"
    "description: A demo skill built by the integration fixture\n"
    "license: Apache-2.0\n"
    "---\n\n"
    "# Demo\n\nBody content.\n"
)


def _build_local_repo(root: Path) -> str:
    """Build a real local repo with a P1 skill tree; return the commit SHA."""
    root.mkdir(parents=True)
    repo = porcelain.init(str(root))
    try:
        skill_dir = root / "skills" / "demo"
        (skill_dir / "scripts").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SKILL_MD)
        (skill_dir / "scripts" / "run.py").write_bytes(RESOURCE_BYTES)
        porcelain.add(
            str(root),
            paths=[
                str(skill_dir / "SKILL.md"),
                str(skill_dir / "scripts" / "run.py"),
            ],
        )
        sha = porcelain.commit(
            str(root),
            message=b"initial skill",
            author=b"Test <test@example.com>",
            committer=b"Test <test@example.com>",
        )
    finally:
        repo.close()
    return sha.decode("ascii")


def _local_ref(root: Path, sha: str) -> GitSkillReference:
    return GitSkillReference(
        host="localhost",
        owner="t",
        repo="t",
        ref=sha,
        url_override=str(root),
    )


class TestGitIntegration:
    async def test_pinned_clone_lists_skill_with_manifest(self, tmp_path: Path) -> None:
        sha = _build_local_repo(tmp_path / "src")
        ref = _local_ref(tmp_path / "src", sha)
        repo = GitSkillRepository(
            GitRepositoryConfig(skills=[ref], cache_dir=tmp_path / "cache")
        )

        skills = await repo.list_all()
        assert len(skills) == 1
        skill = skills[0]
        assert skill.name.value == "demo"
        assert skill.manifest.description.startswith("A demo skill")
        assert skill.manifest.license == "Apache-2.0"

    async def test_resource_bytes_are_byte_identical(self, tmp_path: Path) -> None:
        sha = _build_local_repo(tmp_path / "src")
        ref = _local_ref(tmp_path / "src", sha)
        repo = GitSkillRepository(
            GitRepositoryConfig(skills=[ref], cache_dir=tmp_path / "cache")
        )

        content = await repo.get_resource_content(
            SkillName("demo"), "scripts", "run.py"
        )
        assert content == RESOURCE_BYTES

    async def test_git_dir_absent_from_cache(self, tmp_path: Path) -> None:
        sha = _build_local_repo(tmp_path / "src")
        ref = _local_ref(tmp_path / "src", sha)
        cache = tmp_path / "cache"
        repo = GitSkillRepository(GitRepositoryConfig(skills=[ref], cache_dir=cache))

        await repo.list_all()

        sha_dir = repo._sha_dir(ref, sha)
        assert (sha_dir / CACHE_COMPLETE_MARKER).is_file()
        assert not (sha_dir / ".git").exists()
        assert (sha_dir / "skills" / "demo" / "SKILL.md").is_file()

    async def test_sha_pin_cache_immutable_after_source_deleted(
        self, tmp_path: Path
    ) -> None:
        """A second instance loads purely from cache; the source is gone."""
        src = tmp_path / "src"
        sha = _build_local_repo(src)
        ref = _local_ref(src, sha)
        cache = tmp_path / "cache"

        first = GitSkillRepository(GitRepositoryConfig(skills=[ref], cache_dir=cache))
        assert len(await first.list_all()) == 1

        # Delete the source repository: any network/source access would fail.
        shutil.rmtree(src)
        assert not src.exists()

        second = GitSkillRepository(GitRepositoryConfig(skills=[ref], cache_dir=cache))
        skills = await second.list_all()
        assert len(skills) == 1
        assert skills[0].name.value == "demo"
        # Resource content is still served entirely from the snapshot.
        content = await second.get_resource_content(
            SkillName("demo"), "scripts", "run.py"
        )
        assert content == RESOURCE_BYTES

    async def test_default_branch_via_head(self, tmp_path: Path) -> None:
        """A ref-less reference resolves the default branch (HEAD)."""
        src = tmp_path / "src"
        _build_local_repo(src)
        ref = GitSkillReference(
            host="localhost", owner="t", repo="t", ref=None, url_override=str(src)
        )
        repo = GitSkillRepository(
            GitRepositoryConfig(skills=[ref], cache_dir=tmp_path / "cache")
        )
        names = {s.name.value for s in await repo.list_all()}
        assert names == {"demo"}

    def test_url_override_not_constructible_from_string(self) -> None:
        """The parser never yields url_override; local paths are rejected."""
        with pytest.raises(ValueError, match="scheme"):
            GitSkillReference.from_string("/tmp/src")  # noqa: S108
        with pytest.raises(ValueError, match="scheme"):
            GitSkillReference.from_string("file:///tmp/src")
        # A parsed reference always has url_override unset.
        parsed = GitSkillReference.from_string("git://github.com/org/repo@main")
        assert parsed.url_override is None
