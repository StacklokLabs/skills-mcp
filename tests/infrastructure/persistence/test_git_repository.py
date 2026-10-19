"""Tests for the Git skill repository (discovery, cache, security)."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from skills_mcp.domain.exceptions import ResourceNotFoundError, SkillNotFoundError
from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.domain.repositories import SkillRepository
from skills_mcp.infrastructure.mcp.server import SkillsMCPServer
from skills_mcp.infrastructure.persistence.git_models import (
    GitAuthConfig,
    GitRepositoryConfig,
    GitSkillReference,
)
from skills_mcp.infrastructure.persistence.git_repository import (
    CACHE_COMPLETE_MARKER,
    MAX_RESOURCE_SIZE_BYTES,
    GitSkillRepository,
)


if TYPE_CHECKING:
    from collections.abc import Mapping


# A distinct 40-hex commit per test keeps snapshot dirs from colliding.
def _sha(char: str) -> str:
    return char * 40


def _skill_md(
    name: str | None = None,
    description: str = "A test skill",
    body: str = "# Body\n",
) -> str:
    lines = ["---"]
    if name is not None:
        lines.append(f"name: {name}")
    lines.append(f"description: {description}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body


def _pinned_ref(
    sha: str, *, host: str = "example.com", subdir: str | None = None
) -> GitSkillReference:
    text = f"git://{host}/org/repo@{sha}"
    if subdir is not None:
        text += f"#{subdir}"
    return GitSkillReference.from_string(text)


def _write_snapshot(
    repo: GitSkillRepository,
    ref: GitSkillReference,
    files: Mapping[str, str | bytes],
    *,
    sha: str | None = None,
    resolved_ref: str = "HEAD",
) -> Path:
    """Materialize a complete cache snapshot for a reference."""
    resolved_sha = sha or ref.pinned_sha
    assert resolved_sha is not None
    sha_dir = repo._sha_dir(ref, resolved_sha)
    sha_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        target = sha_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)
    (sha_dir / CACHE_COMPLETE_MARKER).write_text(f"{resolved_sha}\n{resolved_ref}\n")
    return sha_dir


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "gitcache"


def _repo(cache_dir: Path, ref: GitSkillReference, **kw: object) -> GitSkillRepository:
    config = GitRepositoryConfig(skills=[ref], cache_dir=cache_dir, **kw)  # type: ignore[arg-type]
    return GitSkillRepository(config)


class TestInit:
    def test_creates_cache_directory(self, tmp_path: Path) -> None:
        cache = tmp_path / "new_cache"
        GitSkillRepository(GitRepositoryConfig(cache_dir=cache))
        assert cache.exists()

    def test_uses_default_cache_dir(self) -> None:
        repo = GitSkillRepository(GitRepositoryConfig())
        assert repo._cache_dir == GitRepositoryConfig.default_cache_dir()

    def test_is_skill_repository(self, cache_dir: Path) -> None:
        """DONE #9: implements the SkillRepository protocol at runtime."""
        repo = _repo(cache_dir, _pinned_ref(_sha("a")))
        assert isinstance(repo, SkillRepository)


class TestDiscoveryLayouts:
    """Covers reference layouts P1-P4 from the plan (pinned, no network)."""

    async def test_p1_flat_skills_dir(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("a"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(
            repo,
            ref,
            {
                "skills/alpha/SKILL.md": _skill_md("alpha"),
                "skills/beta/SKILL.md": _skill_md("beta"),
            },
        )
        names = {s.name.value for s in await repo.list_all()}
        assert names == {"alpha", "beta"}

    async def test_p2_root_skill_md(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("b"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(repo, ref, {"SKILL.md": _skill_md("repo")})
        names = {s.name.value for s in await repo.list_all()}
        assert names == {"repo"}

    async def test_p3_plugins_nested(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("c"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(
            repo,
            ref,
            {
                "plugins/p1/skills/s1/SKILL.md": _skill_md("s1"),
                "plugins/p2/skills/s2/SKILL.md": _skill_md("s2"),
            },
        )
        names = {s.name.value for s in await repo.list_all()}
        assert names == {"s1", "s2"}

    async def test_p4_multi_root(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("d"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(
            repo,
            ref,
            {
                "a/SKILL.md": _skill_md("a"),
                "b/c/SKILL.md": _skill_md("c"),
                "SKILL.md": _skill_md("repo"),
            },
        )
        names = {s.name.value for s in await repo.list_all()}
        assert names == {"a", "c", "repo"}

    async def test_loads_resources(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("e"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(
            repo,
            ref,
            {
                "skills/x/SKILL.md": _skill_md("x"),
                "skills/x/scripts/run.py": "print('hi')\n",
                "skills/x/references/doc.md": "# Doc\n",
            },
        )
        skill = await repo.find_by_name(SkillName("x"))
        assert skill is not None
        assert {r.name for r in skill.scripts} == {"run.py"}
        assert {r.name for r in skill.references} == {"doc.md"}


class TestManifestCasing:
    @pytest.mark.parametrize("filename", ["SKILL.md", "skill.md", "Skill.md"])
    async def test_case_insensitive_manifest(
        self, cache_dir: Path, filename: str
    ) -> None:
        ref = _pinned_ref(_sha("a"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(repo, ref, {f"skills/c/{filename}": _skill_md("c")})
        skills = await repo.list_all()
        assert {s.name.value for s in skills} == {"c"}
        assert skills[0].sep_eligible is (filename == "SKILL.md")
        server = SkillsMCPServer(repo)
        legacy = await server._handle_list_resources()
        assert [resource.name for resource in legacy] == ["c"]
        legacy_get = json.loads((await server._tool_get_skill("c"))[0].text)
        assert legacy_get["name"] == "c"
        static = await server._static_skills()
        assert [skill.name.value for skill in static] == (
            ["c"] if filename == "SKILL.md" else []
        )


class TestPruning:
    async def test_prunes_template_readme_and_dot_dirs(
        self, cache_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        ref = _pinned_ref(_sha("a"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(
            repo,
            ref,
            {
                "skills/real/SKILL.md": _skill_md("real"),
                "template/SKILL.md": _skill_md("tmpl"),
                "TEMPLATE/SKILL.md": _skill_md("tmpl-upper"),
                "Template/SKILL.md": _skill_md("tmpl-mixed"),
                "README/SKILL.md": _skill_md("readme"),
                "readme/SKILL.md": _skill_md("readme-lower"),
                "ReadMe/SKILL.md": _skill_md("readme-mixed"),
                ".hidden/SKILL.md": _skill_md("hidden"),
                # A .gemini mirror of the real skill must be pruned (dot dir),
                # so it never even competes for the name.
                ".gemini/skills/real/SKILL.md": _skill_md("real"),
            },
        )
        with caplog.at_level(logging.WARNING):
            names = {s.name.value for s in await repo.list_all()}
        assert names == {"real"}
        # Pruned, not a duplicate-name collision.
        assert "Duplicate skill name" not in caplog.text


class TestSymlinks:
    async def test_symlinked_dir_not_followed(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("a"))
        repo = _repo(cache_dir, ref)
        sha_dir = _write_snapshot(
            repo, ref, {"skills/real/SKILL.md": _skill_md("real")}
        )
        external = cache_dir.parent / "external"
        (external / "sneaky").mkdir(parents=True)
        (external / "sneaky" / "SKILL.md").write_text(_skill_md("sneaky"))
        (sha_dir / "linked").symlink_to(external, target_is_directory=True)

        names = {s.name.value for s in await repo.list_all()}
        assert names == {"real"}
        assert "sneaky" not in names

    async def test_escaping_resource_symlink_rejected(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("b"))
        repo = _repo(cache_dir, ref)
        sha_dir = _write_snapshot(repo, ref, {"skills/s/SKILL.md": _skill_md("s")})
        secret = cache_dir.parent / "secret.txt"
        secret.write_text("classified")
        scripts = sha_dir / "skills" / "s" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "evil.py").symlink_to(secret)

        skill = await repo.find_by_name(SkillName("s"))
        assert skill is None


class TestIdentity:
    async def test_name_differs_from_dir_warns_frontmatter_wins(
        self, cache_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        ref = _pinned_ref(_sha("a"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(repo, ref, {"skills/dirname/SKILL.md": _skill_md("realname")})
        with caplog.at_level(logging.WARNING):
            skill = await repo.find_by_name(SkillName("realname"))
        assert skill is not None
        assert skill.name == SkillName("realname")
        assert skill.sep_eligible is False
        assert "frontmatter wins" in caplog.text

    async def test_mismatched_path_key_never_overrides_manifest_name_lookup(
        self, cache_dir: Path
    ) -> None:
        """Legacy Git surfaces resolve the requested frontmatter name only."""
        ref = _pinned_ref(_sha("9"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(
            repo,
            ref,
            {
                "requested/SKILL.md": _skill_md(
                    "different", description="path-key decoy", body="Decoy body\n"
                ),
                "z/SKILL.md": _skill_md(
                    "requested", description="manifest winner", body="Winner body\n"
                ),
                "z/scripts/value.txt": "winner resource\n",
            },
        )

        skill = await repo.find_by_name(SkillName("requested"))
        assert skill is not None
        assert skill.description == "manifest winner"
        server = SkillsMCPServer(repo)
        tool = json.loads((await server._tool_get_skill("requested"))[0].text)
        assert tool["body"] == "Winner body"
        resource = await server._handle_read_resource(
            "skills://requested/scripts/value.txt"
        )
        assert resource[0].content.endswith("winner resource\n")
        assert "decoy resource" not in resource[0].content
        prompt = await server._handle_get_prompt("requested")
        assert "Winner body" in prompt.messages[0].content.text  # type: ignore[union-attr]

    async def test_missing_name_falls_back_to_dir_name(
        self, cache_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        ref = _pinned_ref(_sha("b"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(repo, ref, {"skills/valid-name/SKILL.md": _skill_md(name=None)})
        with caplog.at_level(logging.WARNING):
            skill = await repo.find_by_name(SkillName("valid-name"))
        assert skill is not None
        assert skill.name == SkillName("valid-name")
        assert skill.sep_eligible is False
        assert "using directory name" in caplog.text.lower()

    async def test_missing_name_and_invalid_dir_is_skipped(
        self, cache_dir: Path
    ) -> None:
        ref = _pinned_ref(_sha("c"))
        repo = _repo(cache_dir, ref)
        # "Invalid_Name" is not a valid skill name (underscore, uppercase).
        _write_snapshot(
            repo, ref, {"skills/Invalid_Name/SKILL.md": _skill_md(name=None)}
        )
        assert await repo.list_all() == []

    async def test_missing_description_is_skipped(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("d"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(repo, ref, {"skills/x/SKILL.md": "---\nname: x\n---\n# Body\n"})
        assert await repo.list_all() == []

    async def test_duplicate_name_first_wins(
        self, cache_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        ref = _pinned_ref(_sha("e"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(
            repo,
            ref,
            {
                "skills/first/dup/SKILL.md": _skill_md("dup", description="first"),
                "skills/second/dup/SKILL.md": _skill_md("dup", description="second"),
            },
        )
        with caplog.at_level(logging.WARNING):
            skills = await repo.list_all()
        assert len(skills) == 2
        assert {skill.manifest.description for skill in skills} == {"first", "second"}
        assert "Duplicate skill" not in caplog.text

    async def test_duplicate_name_legacy_projection_is_authoritative(
        self, cache_dir: Path
    ) -> None:
        """Every legacy surface resolves the first listed Git aggregate."""
        ref = _pinned_ref(_sha("f"))
        repo = _repo(cache_dir, ref)
        _write_snapshot(
            repo,
            ref,
            {
                "a/dup/SKILL.md": _skill_md(
                    "dup", description="first aggregate", body="First body\n"
                ),
                "a/dup/scripts/value.txt": "first resource\n",
                "dup/SKILL.md": _skill_md(
                    "dup", description="second aggregate", body="Second body\n"
                ),
                "dup/scripts/value.txt": "second resource\n",
            },
        )
        server = SkillsMCPServer(repo)

        resources = await server._handle_list_resources()
        listed = next(resource for resource in resources if resource.name == "dup")
        assert listed.description == "first aggregate"
        catalog = json.loads((await server._tool_list_skills())[0].text)
        assert catalog == [
            {
                "name": "dup",
                "description": "first aggregate",
                "resources": {"scripts": 1, "references": 0, "assets": 0},
            }
        ]

        instructions = await server._handle_read_resource("skills://dup")
        assert "First body" in instructions[0].content
        tool_skill = json.loads((await server._tool_get_skill("dup"))[0].text)
        assert tool_skill["description"] == "first aggregate"
        assert tool_skill["body"] == "First body"
        resource = await server._handle_read_resource("skills://dup/scripts/value.txt")
        assert "first resource" in resource[0].content
        tool_resource = await server._tool_get_skill_resource(
            "dup", "scripts/value.txt"
        )
        assert tool_resource[0].text == "first resource\n"
        prompt = await server._handle_get_prompt("dup")
        assert prompt.description == "first aggregate"
        assert "First body" in prompt.messages[0].content.text  # type: ignore[union-attr]

        static = await server._static_skills()
        assert {server._canonical_skill_uri(skill) for skill in static} == {
            "skill://a/dup/SKILL.md",
            "skill://dup/SKILL.md",
        }
        for uri, body in {
            "skill://a/dup/SKILL.md": "First body",
            "skill://dup/SKILL.md": "Second body",
        }.items():
            skill = await server._find_skill_by_canonical_uri(uri)
            assert skill is not None
            assert body in skill.body
            canonical = await server._handle_read_resource(uri)
            assert body in canonical[0].content


class TestSubdirScoping:
    async def test_subdir_scopes_walk(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("a"), subdir="skills/pack")
        repo = _repo(cache_dir, ref)
        _write_snapshot(
            repo,
            ref,
            {
                "skills/pack/inside/SKILL.md": _skill_md("inside"),
                "skills/other/SKILL.md": _skill_md("outside"),
            },
        )
        names = {s.name.value for s in await repo.list_all()}
        assert names == {"inside"}

    async def test_missing_subdir_yields_nothing(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("b"), subdir="nope")
        repo = _repo(cache_dir, ref)
        _write_snapshot(repo, ref, {"skills/x/SKILL.md": _skill_md("x")})
        assert await repo.list_all() == []

    async def test_subdir_symlink_escape_rejected(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("c"), subdir="escape")
        repo = _repo(cache_dir, ref)
        sha_dir = _write_snapshot(repo, ref, {"SKILL.md": _skill_md("root")})
        external = cache_dir.parent / "ext"
        (external / "s").mkdir(parents=True)
        (external / "s" / "SKILL.md").write_text(_skill_md("leak"))
        (sha_dir / "escape").symlink_to(external, target_is_directory=True)

        assert await repo.list_all() == []


class TestCacheAndNetwork:
    async def test_cache_marker_hit_never_touches_network(
        self, cache_dir: Path
    ) -> None:
        """DONE: a complete pinned snapshot resolves with zero network."""
        ref = _pinned_ref(_sha("a"))
        repo = _repo(cache_dir, ref, allow_private_hosts=True)
        _write_snapshot(repo, ref, {"skills/x/SKILL.md": _skill_md("x")})

        with (
            patch(
                "skills_mcp.infrastructure.persistence.git_repository.porcelain.ls_remote"
            ) as mock_ls,
            patch(
                "skills_mcp.infrastructure.persistence.git_repository.porcelain.clone"
            ) as mock_clone,
        ):
            names = {s.name.value for s in await repo.list_all()}

        assert names == {"x"}
        mock_ls.assert_not_called()
        mock_clone.assert_not_called()

    async def test_refresh_reloads_moved_branch_from_new_dir(
        self, cache_dir: Path
    ) -> None:
        ref = GitSkillReference.from_string("git://example.com/org/repo@main")
        repo = _repo(cache_dir, ref, allow_private_hosts=True)
        sha1, sha2 = _sha("1"), _sha("2")
        _write_snapshot(
            repo, ref, {"skills/x/SKILL.md": _skill_md("x", description="v1")}, sha=sha1
        )
        _write_snapshot(
            repo, ref, {"skills/x/SKILL.md": _skill_md("x", description="v2")}, sha=sha2
        )

        def ls_remote(_url: str, **_kw: object) -> MagicMock:
            result = MagicMock()
            result.refs = {b"refs/heads/main": current[0].encode()}
            return result

        current = [sha1]
        with patch(
            "skills_mcp.infrastructure.persistence.git_repository.porcelain.ls_remote",
            side_effect=ls_remote,
        ):
            skill = await repo.find_by_name(SkillName("x"))
            assert skill is not None
            assert skill.manifest.description == "v1"

            current[0] = sha2
            await repo.refresh()
            skill = await repo.find_by_name(SkillName("x"))
            assert skill is not None
            assert skill.manifest.description == "v2"

    async def test_offline_branch_serves_stale_with_warning(
        self, cache_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        ref = GitSkillReference.from_string("git://example.com/org/repo@main")
        repo = _repo(cache_dir, ref, allow_private_hosts=True)
        sha = _sha("9")
        _write_snapshot(repo, ref, {"skills/x/SKILL.md": _skill_md("x")}, sha=sha)
        repo._write_pointer(ref, sha)  # a prior successful resolve

        with (
            patch(
                "skills_mcp.infrastructure.persistence.git_repository.porcelain.ls_remote",
                side_effect=OSError("network down"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            names = {s.name.value for s in await repo.list_all()}

        assert names == {"x"}
        assert "Serving stale" in caplog.text

    async def test_offline_branch_without_cache_is_skipped(
        self, cache_dir: Path
    ) -> None:
        ref = GitSkillReference.from_string("git://example.com/org/repo@main")
        repo = _repo(cache_dir, ref, allow_private_hosts=True)
        with patch(
            "skills_mcp.infrastructure.persistence.git_repository.porcelain.ls_remote",
            side_effect=OSError("network down"),
        ):
            assert await repo.list_all() == []

    async def test_one_bad_ref_does_not_sink_others(self, cache_dir: Path) -> None:
        good = _pinned_ref(_sha("a"))
        bad = GitSkillReference.from_string("git://example.com/org/other@main")
        config = GitRepositoryConfig(
            skills=[bad, good], cache_dir=cache_dir, allow_private_hosts=True
        )
        repo = GitSkillRepository(config)
        _write_snapshot(repo, good, {"skills/x/SKILL.md": _skill_md("x")})

        with patch(
            "skills_mcp.infrastructure.persistence.git_repository.porcelain.ls_remote",
            side_effect=OSError("boom"),
        ):
            names = {s.name.value for s in await repo.list_all()}
        assert names == {"x"}


class TestCredentialHygiene:
    async def test_clone_receives_creds_as_kwargs_never_in_url_or_logs(
        self, cache_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """DONE #10: token appears only as a kwarg, never in URL or logs."""
        token = "ghp_supersecrettoken"  # noqa: S105
        ref = GitSkillReference.from_string("git://github.com/org/repo@main")
        config = GitRepositoryConfig(
            skills=[ref],
            cache_dir=cache_dir,
            allow_private_hosts=True,
            auth={"github.com": GitAuthConfig(host="github.com", password=token)},
        )
        repo = GitSkillRepository(config)

        def ls_remote(_url: str, **_kw: object) -> MagicMock:
            result = MagicMock()
            result.refs = {b"refs/heads/main": _sha("a").encode()}
            return result

        clone_calls: list[dict[str, object]] = []

        def clone(url: str, **kwargs: object) -> MagicMock:
            clone_calls.append({"url": url, **kwargs})
            return MagicMock()

        with (
            patch(
                "skills_mcp.infrastructure.persistence.git_repository.porcelain.ls_remote",
                side_effect=ls_remote,
            ),
            patch(
                "skills_mcp.infrastructure.persistence.git_repository.porcelain.clone",
                side_effect=clone,
            ),
            caplog.at_level(logging.DEBUG),
        ):
            await repo.list_all()

        assert clone_calls, "clone should have been called"
        call = clone_calls[0]
        assert call["username"] == "x-access-token"
        assert call["password"] == token
        assert token not in str(call["url"])
        assert token not in caplog.text


class TestPrivateHostRejection:
    async def test_private_host_rejected(self, cache_dir: Path) -> None:
        ref = GitSkillReference.from_string("git://internal.example.com/org/repo@main")
        repo = _repo(cache_dir, ref, allow_private_hosts=False)

        def fake_getaddrinfo(*_a: object, **_k: object) -> list[object]:
            return [(2, 1, 6, "", ("10.0.0.5", 443))]

        with (
            patch(
                "skills_mcp.infrastructure.persistence.git_repository.socket.getaddrinfo",
                side_effect=fake_getaddrinfo,
            ),
            patch(
                "skills_mcp.infrastructure.persistence.git_repository.porcelain.ls_remote"
            ) as mock_ls,
        ):
            assert await repo.list_all() == []
            mock_ls.assert_not_called()

    async def test_allow_private_hosts_bypasses_check(self, cache_dir: Path) -> None:
        ref = _pinned_ref(_sha("a"), host="internal.example.com")
        repo = _repo(cache_dir, ref, allow_private_hosts=True)
        _write_snapshot(repo, ref, {"skills/x/SKILL.md": _skill_md("x")})

        with patch(
            "skills_mcp.infrastructure.persistence.git_repository.socket.getaddrinfo",
            side_effect=AssertionError("getaddrinfo must not be called"),
        ):
            names = {s.name.value for s in await repo.list_all()}
        assert names == {"x"}


class TestGetResourceContent:
    async def test_raises_skill_not_found(self, cache_dir: Path) -> None:
        repo = _repo(cache_dir, _pinned_ref(_sha("a")))
        repo._skills_cache = {}
        with pytest.raises(SkillNotFoundError):
            await repo.get_resource_content(SkillName("missing"), "scripts", "x.py")

    async def test_raises_for_invalid_resource_type(
        self, cache_dir: Path, tmp_path: Path
    ) -> None:
        repo = _repo(cache_dir, _pinned_ref(_sha("a")))
        skill = MagicMock()
        skill.name = SkillName("s")
        skill.path = tmp_path
        repo._skills_cache = {"s": skill}
        with pytest.raises(ResourceNotFoundError):
            await repo.get_resource_content(SkillName("s"), "bogus", "x.py")

    async def test_raises_for_missing_resource(
        self, cache_dir: Path, tmp_path: Path
    ) -> None:
        repo = _repo(cache_dir, _pinned_ref(_sha("a")))
        skill = MagicMock()
        skill.name = SkillName("s")
        skill.path = tmp_path
        skill.get_resource.return_value = None
        repo._skills_cache = {"s": skill}
        with pytest.raises(ResourceNotFoundError):
            await repo.get_resource_content(SkillName("s"), "scripts", "missing.py")

    async def test_raises_for_traversal(self, cache_dir: Path, tmp_path: Path) -> None:
        repo = _repo(cache_dir, _pinned_ref(_sha("a")))
        resource = MagicMock()
        resource.path = Path("/etc/passwd")
        skill = MagicMock()
        skill.name = SkillName("s")
        skill.path = tmp_path
        skill.get_resource.return_value = resource
        repo._skills_cache = {"s": skill}
        with pytest.raises(ResourceNotFoundError):
            await repo.get_resource_content(SkillName("s"), "scripts", "passwd")

    async def test_raises_for_oversized(self, cache_dir: Path, tmp_path: Path) -> None:
        big = tmp_path / "scripts" / "big.py"
        big.parent.mkdir(parents=True)
        big.write_bytes(b"x" * (MAX_RESOURCE_SIZE_BYTES + 1))
        repo = _repo(cache_dir, _pinned_ref(_sha("a")))
        resource = MagicMock()
        resource.path = big
        skill = MagicMock()
        skill.name = SkillName("s")
        skill.path = tmp_path
        skill.get_resource.return_value = resource
        repo._skills_cache = {"s": skill}
        with pytest.raises(ResourceNotFoundError, match="too large"):
            await repo.get_resource_content(SkillName("s"), "scripts", "big.py")

    async def test_returns_content(self, cache_dir: Path, tmp_path: Path) -> None:
        f = tmp_path / "scripts" / "run.py"
        f.parent.mkdir(parents=True)
        f.write_bytes(b"print('hi')")
        repo = _repo(cache_dir, _pinned_ref(_sha("a")))
        resource = MagicMock()
        resource.path = f
        skill = MagicMock()
        skill.name = SkillName("s")
        skill.path = tmp_path
        skill.get_resource.return_value = resource
        repo._skills_cache = {"s": skill}
        content = await repo.get_resource_content(SkillName("s"), "scripts", "run.py")
        assert content == b"print('hi')"


class TestRefresh:
    async def test_clears_cache(self, cache_dir: Path) -> None:
        repo = _repo(cache_dir, _pinned_ref(_sha("a")))
        repo._skills_cache = {"x": MagicMock()}
        await repo.refresh()
        assert repo._skills_cache is None


class TestCloneTimeout:
    async def test_timeout_skips_reference_without_poisoning_cache(
        self, cache_dir: Path
    ) -> None:
        """A clone exceeding clone_timeout is skipped; no partial sha_dir.

        The orphaned clone thread (which outlives asyncio.wait_for) is held
        blocked while we assert, proving the timed-out attempt neither
        produces a reference nor leaves a completed/partial snapshot behind.
        """
        ref = GitSkillReference.from_string("git://example.com/org/repo@main")
        repo = _repo(cache_dir, ref, allow_private_hosts=True)
        repo._config.clone_timeout = 0.2  # tighten the wait_for bound (float ok)
        sha = _sha("a")

        def ls_remote(_url: str, **_kw: object) -> MagicMock:
            result = MagicMock()
            result.refs = {b"refs/heads/main": sha.encode()}
            return result

        release = threading.Event()

        def slow_clone(_url: str, **kwargs: object) -> MagicMock:
            # Block past the timeout; released only after our assertions.
            release.wait(timeout=5)
            target = Path(str(kwargs["target"]))
            demo = target / "skills" / "x"
            demo.mkdir(parents=True, exist_ok=True)
            (demo / "SKILL.md").write_text(_skill_md("x"))
            return MagicMock()

        try:
            with (
                patch(
                    "skills_mcp.infrastructure.persistence.git_repository.porcelain.ls_remote",
                    side_effect=ls_remote,
                ),
                patch(
                    "skills_mcp.infrastructure.persistence.git_repository.porcelain.clone",
                    side_effect=slow_clone,
                ),
            ):
                skills = await repo.list_all()

            assert skills == []
            sha_dir = repo._sha_dir(ref, sha)
            # Atomic replace happens only after a full clone, so the snapshot
            # is never complete (nor partial) at this point.
            assert not repo._is_complete(sha_dir)
            assert repo._read_pointer(ref) is None
        finally:
            release.set()  # let the orphaned worker thread unwind cleanly


class TestConcurrentLoad:
    async def test_two_concurrent_list_all_fetch_once(self, cache_dir: Path) -> None:
        """QA: racing list_all() calls trigger exactly one fetch (asyncio.Lock)."""
        ref = GitSkillReference.from_string("git://example.com/org/repo@main")
        repo = _repo(cache_dir, ref, allow_private_hosts=True)
        sha = _sha("b")

        ls_calls = 0
        clone_calls = 0

        def ls_remote(_url: str, **_kw: object) -> MagicMock:
            nonlocal ls_calls
            ls_calls += 1
            result = MagicMock()
            result.refs = {b"refs/heads/main": sha.encode()}
            return result

        def clone(_url: str, **kwargs: object) -> MagicMock:
            nonlocal clone_calls
            clone_calls += 1
            target = Path(str(kwargs["target"]))
            demo = target / "skills" / "x"
            demo.mkdir(parents=True, exist_ok=True)
            (demo / "SKILL.md").write_text(_skill_md("x"))
            return MagicMock()

        with (
            patch(
                "skills_mcp.infrastructure.persistence.git_repository.porcelain.ls_remote",
                side_effect=ls_remote,
            ),
            patch(
                "skills_mcp.infrastructure.persistence.git_repository.porcelain.clone",
                side_effect=clone,
            ),
        ):
            first, second = await asyncio.gather(repo.list_all(), repo.list_all())

        assert ls_calls == 1
        assert clone_calls == 1
        assert {s.name.value for s in first} == {"x"}
        assert {s.name.value for s in second} == {"x"}
