"""Tests for OCI skill repository."""

import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from skills_mcp.domain.exceptions import ResourceNotFoundError, SkillNotFoundError
from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.infrastructure.mcp.server import SkillsMCPServer
from skills_mcp.infrastructure.persistence.oci_models import (
    OCIAuthConfig,
    OCIRepositoryConfig,
    OCISkillReference,
)
from skills_mcp.infrastructure.persistence.oci_repository import (
    MAX_RESOURCE_SIZE_BYTES,
    MAX_TARBALL_FILES,
    MAX_TARBALL_TOTAL_SIZE,
    OCISkillRepository,
)


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def basic_config(tmp_cache_dir: Path) -> OCIRepositoryConfig:
    """Create a basic repository configuration."""
    return OCIRepositoryConfig(
        skills=[
            OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0"),
        ],
        cache_dir=tmp_cache_dir,
    )


@pytest.fixture
def repo(basic_config: OCIRepositoryConfig) -> OCISkillRepository:
    """Create a repository instance for testing."""
    return OCISkillRepository(basic_config)


class TestOCISkillRepositoryInit:
    """Tests for OCISkillRepository initialization."""

    def test_creates_cache_directory(self, tmp_path: Path) -> None:
        """Should create cache directory if it doesn't exist."""
        cache_dir = tmp_path / "new_cache"
        config = OCIRepositoryConfig(cache_dir=cache_dir)

        OCISkillRepository(config)

        assert cache_dir.exists()

    def test_uses_default_cache_dir_when_not_specified(self) -> None:
        """Should use default cache directory when not specified."""
        config = OCIRepositoryConfig()
        repo = OCISkillRepository(config)

        # Should use default path
        assert repo._cache_dir == OCIRepositoryConfig.default_cache_dir()


class TestListAll:
    """Tests for list_all method."""

    async def test_returns_empty_when_no_skills_configured(
        self, tmp_cache_dir: Path
    ) -> None:
        """Should return empty list when no skills are configured."""
        config = OCIRepositoryConfig(skills=[], cache_dir=tmp_cache_dir)
        repo = OCISkillRepository(config)

        skills = await repo.list_all()

        assert skills == []

    async def test_caches_skills_after_first_load(
        self, repo: OCISkillRepository
    ) -> None:
        """Should cache skills after first load."""
        # Mock the internal load
        repo._skills_cache = {}

        await repo.list_all()
        skills1 = await repo.list_all()

        # Should use cached value
        assert skills1 == []


class TestFindByName:
    """Tests for find_by_name method."""

    async def test_returns_none_for_missing_skill(
        self, repo: OCISkillRepository
    ) -> None:
        """Should return None when skill is not found."""
        # Set empty cache
        repo._skills_cache = {}

        result = await repo.find_by_name(SkillName("nonexistent"))

        assert result is None

    async def test_finds_cached_skill(self, repo: OCISkillRepository) -> None:
        """Should find skill from cache."""
        mock_skill = MagicMock()
        mock_skill.name = SkillName("test-skill")
        repo._skills_cache = {"test-skill": mock_skill}

        result = await repo.find_by_name(SkillName("test-skill"))

        assert result is mock_skill

    async def test_mismatched_path_key_never_overrides_manifest_name_lookup(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Legacy OCI surfaces resolve the requested frontmatter name only."""
        decoy_dir = tmp_path / "requested"
        winner_dir = tmp_path / "z"
        for skill_dir, name, description, body in (
            (decoy_dir, "different", "path-key decoy", "Decoy body"),
            (winner_dir, "requested", "manifest winner", "Winner body"),
        ):
            (skill_dir / "scripts").mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {description}\n---\n{body}\n"
            )
            (skill_dir / "scripts/value.txt").write_text(
                "decoy resource\n" if name == "different" else "winner resource\n"
            )
        decoy = await repo._load_skill_from_dir(
            decoy_dir, decoy_dir / "SKILL.md", "requested"
        )
        winner = await repo._load_skill_from_dir(
            winner_dir, winner_dir / "SKILL.md", "z"
        )
        assert decoy is not None
        assert winner is not None
        repo._skills_cache = {"requested": decoy, "z": winner}

        skill = await repo.find_by_name(SkillName("requested"))
        assert skill is winner
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


class TestGetResourceContent:
    """Tests for get_resource_content method."""

    async def test_raises_skill_not_found(self, repo: OCISkillRepository) -> None:
        """Should raise SkillNotFoundError when skill doesn't exist."""
        repo._skills_cache = {}

        with pytest.raises(SkillNotFoundError):
            await repo.get_resource_content(SkillName("missing"), "scripts", "test.py")

    async def test_raises_for_invalid_resource_type(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should raise ResourceNotFoundError for invalid resource type."""
        mock_skill = MagicMock()
        mock_skill.name = SkillName("test-skill")
        mock_skill.path = tmp_path
        repo._skills_cache = {"test-skill": mock_skill}

        with pytest.raises(ResourceNotFoundError):
            await repo.get_resource_content(
                SkillName("test-skill"), "invalid_type", "test.py"
            )

    async def test_raises_for_missing_resource(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should raise ResourceNotFoundError when resource doesn't exist."""
        mock_skill = MagicMock()
        mock_skill.name = SkillName("test-skill")
        mock_skill.path = tmp_path
        mock_skill.get_resource.return_value = None
        repo._skills_cache = {"test-skill": mock_skill}

        with pytest.raises(ResourceNotFoundError):
            await repo.get_resource_content(
                SkillName("test-skill"), "scripts", "missing.py"
            )

    async def test_raises_for_resource_outside_skill_dir(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should raise ResourceNotFoundError for path traversal attempt."""
        mock_resource = MagicMock()
        # Try to access file outside skill directory
        mock_resource.path = Path("/etc/passwd")

        mock_skill = MagicMock()
        mock_skill.name = SkillName("test-skill")
        mock_skill.path = tmp_path
        mock_skill.get_resource.return_value = mock_resource
        repo._skills_cache = {"test-skill": mock_skill}

        with pytest.raises(ResourceNotFoundError):
            await repo.get_resource_content(
                SkillName("test-skill"), "scripts", "passwd"
            )

    async def test_raises_for_oversized_resource(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should raise ResourceNotFoundError for oversized resources."""
        # Create a mock resource file
        resource_file = tmp_path / "scripts" / "large.py"
        resource_file.parent.mkdir(parents=True)
        resource_file.write_bytes(b"x" * (MAX_RESOURCE_SIZE_BYTES + 1))

        mock_resource = MagicMock()
        mock_resource.path = resource_file

        mock_skill = MagicMock()
        mock_skill.name = SkillName("test-skill")
        mock_skill.path = tmp_path
        mock_skill.get_resource.return_value = mock_resource
        repo._skills_cache = {"test-skill": mock_skill}

        with pytest.raises(ResourceNotFoundError, match="too large"):
            await repo.get_resource_content(
                SkillName("test-skill"), "scripts", "large.py"
            )

    async def test_returns_resource_content(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should return resource content when valid."""
        # Create a resource file
        resource_file = tmp_path / "scripts" / "test.py"
        resource_file.parent.mkdir(parents=True)
        resource_file.write_bytes(b"print('hello')")

        mock_resource = MagicMock()
        mock_resource.path = resource_file

        mock_skill = MagicMock()
        mock_skill.name = SkillName("test-skill")
        mock_skill.path = tmp_path
        mock_skill.get_resource.return_value = mock_resource
        repo._skills_cache = {"test-skill": mock_skill}

        content = await repo.get_resource_content(
            SkillName("test-skill"), "scripts", "test.py"
        )

        assert content == b"print('hello')"


class TestRefresh:
    """Tests for refresh method."""

    async def test_clears_cache(self, repo: OCISkillRepository) -> None:
        """Should clear the skills cache."""
        repo._skills_cache = {"skill": MagicMock()}

        await repo.refresh()

        assert repo._skills_cache is None


class TestExtractTarball:
    """Tests for tarball extraction security."""

    def create_tarball(
        self, tmp_path: Path, members: list[tuple[str, bytes | None, str | None]]
    ) -> Path:
        """Create a test tarball with specified members.

        Args:
            tmp_path: Temporary directory.
            members: List of (name, content, type) tuples.
                     type can be: 'file', 'symlink', 'dir', 'device', 'fifo'

        Returns:
            Path to the created tarball.
        """
        tarball_path = tmp_path / "test.tar.gz"

        with tarfile.open(tarball_path, "w:gz") as tar:
            for name, content, member_type in members:
                if member_type == "file":
                    data = content or b""
                    info = tarfile.TarInfo(name=name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
                elif member_type == "symlink":
                    info = tarfile.TarInfo(name=name)
                    info.type = tarfile.SYMTYPE
                    info.linkname = cast("str", content)  # linkname for symlinks
                    tar.addfile(info)
                elif member_type == "hardlink":
                    info = tarfile.TarInfo(name=name)
                    info.type = tarfile.LNKTYPE
                    info.linkname = cast("str", content)
                    tar.addfile(info)
                elif member_type == "dir":
                    info = tarfile.TarInfo(name=name)
                    info.type = tarfile.DIRTYPE
                    tar.addfile(info)
                elif member_type == "device":
                    info = tarfile.TarInfo(name=name)
                    info.type = tarfile.CHRTYPE
                    tar.addfile(info)
                elif member_type == "fifo":
                    info = tarfile.TarInfo(name=name)
                    info.type = tarfile.FIFOTYPE
                    tar.addfile(info)

        return tarball_path

    def test_extracts_valid_tarball(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should extract valid tarball successfully."""
        tarball = self.create_tarball(
            tmp_path,
            [
                ("SKILL.md", b"# Test Skill", "file"),
                ("scripts/test.py", b"print('hello')", "file"),
            ],
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        repo._extract_tarball(tarball, output_dir)

        assert (output_dir / "SKILL.md").exists()
        assert (output_dir / "scripts" / "test.py").exists()

    def test_rejects_path_traversal_dotdot(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should reject tarball with .. in path."""
        tarball = self.create_tarball(
            tmp_path,
            [("../etc/passwd", b"malicious", "file")],
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="Unsafe path"):
            repo._extract_tarball(tarball, output_dir)

    def test_rejects_absolute_path(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should reject tarball with absolute paths."""
        tarball = self.create_tarball(
            tmp_path,
            [("/etc/passwd", b"malicious", "file")],
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="Unsafe path"):
            repo._extract_tarball(tarball, output_dir)

    def test_rejects_symlinks(self, repo: OCISkillRepository, tmp_path: Path) -> None:
        """Should reject tarball containing symlinks."""
        tarball = self.create_tarball(
            tmp_path,
            [("link", "/etc/passwd", "symlink")],
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="Symlink not allowed"):
            repo._extract_tarball(tarball, output_dir)

    def test_rejects_hardlinks(self, repo: OCISkillRepository, tmp_path: Path) -> None:
        """Should reject tarball containing hardlinks."""
        tarball = self.create_tarball(
            tmp_path,
            [("link", "/etc/passwd", "hardlink")],
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="Symlink not allowed"):
            repo._extract_tarball(tarball, output_dir)

    def test_rejects_device_files(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should reject tarball containing device files."""
        tarball = self.create_tarball(
            tmp_path,
            [("dev", None, "device")],
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="Device file not allowed"):
            repo._extract_tarball(tarball, output_dir)

    def test_rejects_fifo(self, repo: OCISkillRepository, tmp_path: Path) -> None:
        """Should reject tarball containing FIFOs."""
        tarball = self.create_tarball(
            tmp_path,
            [("fifo", None, "fifo")],
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="FIFO not allowed"):
            repo._extract_tarball(tarball, output_dir)

    def test_rejects_too_many_files(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should reject tarball with too many files."""
        members = [
            (f"file_{i}.txt", b"content", "file") for i in range(MAX_TARBALL_FILES + 1)
        ]
        tarball = self.create_tarball(tmp_path, members)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="Too many files"):
            repo._extract_tarball(tarball, output_dir)

    def test_rejects_oversized_tarball(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should reject tarball exceeding size limit."""
        # Create a few large files that together exceed the limit
        large_content = b"x" * (MAX_TARBALL_TOTAL_SIZE // 2 + 1)
        members = [
            ("file1.bin", large_content, "file"),
            ("file2.bin", large_content, "file"),
        ]
        tarball = self.create_tarball(tmp_path, members)
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="Tarball too large"):
            repo._extract_tarball(tarball, output_dir)


class TestIsPathSafe:
    """Tests for path safety validation."""

    def test_safe_path_within_base(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should return True for path within base directory."""
        base = tmp_path / "skill"
        base.mkdir()
        file_path = base / "scripts" / "test.py"
        file_path.parent.mkdir(parents=True)
        file_path.touch()

        assert repo._is_path_safe(file_path, base) is True

    def test_unsafe_path_outside_base(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should return False for path outside base directory."""
        base = tmp_path / "skill"
        base.mkdir()
        file_path = tmp_path / "other" / "file.txt"
        file_path.parent.mkdir(parents=True)
        file_path.touch()

        assert repo._is_path_safe(file_path, base) is False

    def test_handles_symlink_escape(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should catch symlink that escapes base directory."""
        base = tmp_path / "skill"
        base.mkdir()
        external_file = tmp_path / "external.txt"
        external_file.write_text("secret")
        symlink = base / "link"
        symlink.symlink_to(external_file)

        # The resolved path is outside base
        assert repo._is_path_safe(symlink.resolve(), base) is False


class TestGetSkillCacheDir:
    """Tests for cache directory path generation."""

    def test_generates_correct_path(
        self, repo: OCISkillRepository, tmp_cache_dir: Path
    ) -> None:
        """Should generate correct cache directory path."""
        ref = OCISkillReference.from_string("ghcr.io/org/skill:v1.0.0")

        cache_dir = repo._get_skill_cache_dir(ref)

        # Should be cache_dir/registry/namespace/name/tag
        assert cache_dir == tmp_cache_dir / "ghcr.io" / "org" / "skill" / "v1.0.0"

    def test_handles_port_in_registry(
        self, repo: OCISkillRepository, tmp_cache_dir: Path
    ) -> None:
        """Should handle registry with port."""
        ref = OCISkillReference.from_string("localhost:5000/test/skill:dev")

        cache_dir = repo._get_skill_cache_dir(ref)

        # Port colon should be replaced with underscore
        assert cache_dir == tmp_cache_dir / "localhost_5000" / "test" / "skill" / "dev"

    def test_handles_nested_namespace(
        self, repo: OCISkillRepository, tmp_cache_dir: Path
    ) -> None:
        """Should handle nested namespace with slashes."""
        ref = OCISkillReference.from_string("ghcr.io/org/group/skill:latest")

        cache_dir = repo._get_skill_cache_dir(ref)

        # Namespace slashes should be replaced with underscores
        assert cache_dir == tmp_cache_dir / "ghcr.io" / "org_group" / "skill" / "latest"


class TestPullWithOras:
    """Tests for oras pull integration."""

    @patch(
        "skills_mcp.infrastructure.persistence.oci_repository.oras.client.OrasClient"
    )
    def test_pulls_artifact(
        self,
        mock_client_class: MagicMock,
        repo: OCISkillRepository,
        tmp_path: Path,
    ) -> None:
        """Should pull artifact using oras client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.pull.return_value = []

        ref = OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        repo._pull_with_oras(ref, output_dir)

        mock_client_class.assert_called_once_with(hostname="ghcr.io", insecure=False)
        mock_client.pull.assert_called_once()

    @patch(
        "skills_mcp.infrastructure.persistence.oci_repository.oras.client.OrasClient"
    )
    def test_authenticates_when_configured(
        self,
        mock_client_class: MagicMock,
        tmp_cache_dir: Path,
    ) -> None:
        """Should authenticate when credentials are configured."""
        config = OCIRepositoryConfig(
            skills=[OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")],
            cache_dir=tmp_cache_dir,
            auth={
                "ghcr.io": OCIAuthConfig(
                    registry="ghcr.io",
                    username="user",
                    password="token",  # noqa: S106
                )
            },
        )
        repo = OCISkillRepository(config)

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.pull.return_value = []

        ref = OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")
        output_dir = tmp_cache_dir / "output"
        output_dir.mkdir()

        repo._pull_with_oras(ref, output_dir)

        mock_client.login.assert_called_once_with(
            hostname="ghcr.io",
            username="user",
            password="token",  # noqa: S106
        )

    @patch(
        "skills_mcp.infrastructure.persistence.oci_repository.oras.client.OrasClient"
    )
    def test_raises_on_oras_error(
        self,
        mock_client_class: MagicMock,
        repo: OCISkillRepository,
        tmp_path: Path,
    ) -> None:
        """Should raise exception when oras pull fails."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.pull.side_effect = RuntimeError("Registry error")

        ref = OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(RuntimeError, match="Registry error"):
            repo._pull_with_oras(ref, output_dir)


class TestAsyncErrorHandling:
    """Tests for async error handling in pull operations."""

    async def test_try_pull_skill_handles_oserror(
        self, repo: OCISkillRepository
    ) -> None:
        """Should handle OSError gracefully and return None."""
        ref = OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")

        with patch.object(repo, "_pull_skill", side_effect=OSError("Disk full")):
            result = await repo._try_pull_skill(ref)

        assert result is None

    async def test_try_pull_skill_handles_valueerror(
        self, repo: OCISkillRepository
    ) -> None:
        """Should handle ValueError gracefully and return None."""
        ref = OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")

        with patch.object(repo, "_pull_skill", side_effect=ValueError("Invalid data")):
            result = await repo._try_pull_skill(ref)

        assert result is None

    async def test_try_pull_skill_handles_unexpected_exception(
        self, repo: OCISkillRepository
    ) -> None:
        """Should handle unexpected exceptions gracefully."""
        ref = OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")

        with patch.object(repo, "_pull_skill", side_effect=RuntimeError("Unexpected")):
            result = await repo._try_pull_skill(ref)

        assert result is None

    async def test_pull_skill_handles_executor_oserror(
        self, repo: OCISkillRepository
    ) -> None:
        """Should handle OSError from thread executor."""
        ref = OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")
        err = OSError("Permission denied")

        with patch.object(repo, "_pull_with_oras", side_effect=err):
            result = await repo._pull_skill(ref)

        assert result is None

    async def test_pull_skill_handles_executor_valueerror(
        self, repo: OCISkillRepository
    ) -> None:
        """Should handle ValueError from thread executor."""
        ref = OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")
        err = ValueError("Bad tarball")

        with patch.object(repo, "_pull_with_oras", side_effect=err):
            result = await repo._pull_skill(ref)

        assert result is None

    async def test_pull_skill_handles_executor_runtime_error(
        self, repo: OCISkillRepository
    ) -> None:
        """Should handle RuntimeError from thread executor."""
        ref = OCISkillReference.from_string("ghcr.io/test/skill:v1.0.0")

        with patch.object(repo, "_pull_with_oras", side_effect=RuntimeError("Network")):
            result = await repo._pull_skill(ref)

        assert result is None

    async def test_load_skills_continues_on_individual_failure(
        self, tmp_cache_dir: Path
    ) -> None:
        """Should continue loading other skills when one fails."""
        config = OCIRepositoryConfig(
            skills=[
                OCISkillReference.from_string("ghcr.io/test/skill1:v1"),
                OCISkillReference.from_string("ghcr.io/test/skill2:v1"),
            ],
            cache_dir=tmp_cache_dir,
        )
        repo = OCISkillRepository(config)

        # First skill fails, second succeeds
        call_count = 0

        async def mock_try_pull(ref: OCISkillReference) -> MagicMock | None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # First fails
            mock_skill = MagicMock()
            mock_skill.name = SkillName("skill2")
            return mock_skill

        with patch.object(repo, "_try_pull_skill", side_effect=mock_try_pull):
            await repo._load_skills()

        assert len(repo._skills_cache) == 1
        assert "skill2" in repo._skills_cache


class TestLoadSkillFromDir:
    """Tests for loading skills from extracted directories."""

    async def test_loads_skill_from_valid_directory(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should load skill from directory with SKILL.md."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()

        # Create SKILL.md
        manifest = skill_dir / "SKILL.md"
        manifest.write_text(
            "---\nname: test-skill\ndescription: A test skill\n---\n# Test Skill\n"
        )

        # Create some resources
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.py").write_text("print('hello')")

        skill = await repo._load_skill_from_dir(skill_dir, manifest)

        assert skill.name.value == "test-skill"
        assert skill.manifest.description == "A test skill"


class TestDiscoverResources:
    """Tests for resource discovery."""

    async def test_discovers_files_in_directory(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should discover files in resource directory."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        # Create some files
        (scripts_dir / "run.py").write_text("print('run')")
        (scripts_dir / "helper.py").write_text("print('helper')")

        resources = await repo._discover_resources(scripts_dir, skill_dir)

        assert len(resources) == 2

    async def test_skips_hidden_files(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should skip files starting with dot."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        (scripts_dir / ".hidden").write_text("hidden")
        (scripts_dir / "visible.py").write_text("visible")

        resources = await repo._discover_resources(scripts_dir, skill_dir)

        assert len(resources) == 1
        assert resources[0].name == "visible.py"

    async def test_returns_empty_for_nonexistent_directory(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """Should return empty list for non-existent directory."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        resources = await repo._discover_resources(skill_dir / "nonexistent", skill_dir)

        assert resources == []


class TestOCISkillRepositoryLastModified:
    """Tests for the SEP-2640 last_modified population from extracted mtime."""

    async def test_load_skill_from_dir_populates_last_modified(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """A skill loaded from an extracted dir carries file mtimes.

        OCI artifacts are extracted with tar.extractall / copytree, which
        preserve archived mtimes, so the extracted mtime is meaningful.
        """
        skill_dir = tmp_path / "oci-skill"
        (skill_dir / "scripts").mkdir(parents=True)
        manifest_path = skill_dir / "SKILL.md"
        manifest_path.write_text(
            "---\nname: oci-skill\ndescription: An OCI test skill\n---\n\n# OCI\n"
        )
        (skill_dir / "scripts" / "run.py").write_text("print('hi')\n")

        skill = await repo._load_skill_from_dir(skill_dir, manifest_path)

        assert skill.last_modified is not None
        assert skill.last_modified.tzinfo is not None
        assert skill.scripts
        assert skill.scripts[0].last_modified is not None

    async def test_load_skill_from_dir_last_modified_matches_manifest_mtime(
        self, repo: OCISkillRepository, tmp_path: Path
    ) -> None:
        """The skill last_modified must equal the SKILL.md mtime in UTC."""
        skill_dir = tmp_path / "oci-skill"
        skill_dir.mkdir()
        manifest_path = skill_dir / "SKILL.md"
        manifest_path.write_text(
            "---\nname: oci-skill\ndescription: An OCI test skill\n---\n\n# OCI\n"
        )

        skill = await repo._load_skill_from_dir(skill_dir, manifest_path)

        expected = datetime.fromtimestamp(manifest_path.stat().st_mtime, tz=UTC)
        assert skill.last_modified == expected
