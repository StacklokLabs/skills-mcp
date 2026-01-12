"""Tests for CachingRepositoryDecorator."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from skills_mcp.domain.models.skill import Skill
from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.infrastructure.persistence.cache import CachingRepositoryDecorator


def create_mock_skill(name: str) -> Skill:
    """Create a mock Skill object for testing."""
    manifest = MagicMock()
    manifest.name = SkillName(name)
    manifest.description = f"Test skill {name}"
    return Skill(
        manifest=manifest,
        body=f"# {name}\n\nTest body",
        path=Path(f"/skills/{name}"),
        scripts=[],
        references=[],
        assets=[],
        token_count=100,
    )


class TestCachingRepositoryDecoratorFindByName:
    """Tests for find_by_name (delegates to inner repo)."""

    async def test_delegates_to_inner_repo(self) -> None:
        """Should delegate find_by_name to inner repository."""
        inner = AsyncMock()
        skill = create_mock_skill("test-skill")
        inner.find_by_name.return_value = skill

        cached = CachingRepositoryDecorator(inner)
        name = SkillName("test-skill")

        # First call should hit inner
        result1 = await cached.find_by_name(name)
        assert result1 is skill
        assert inner.find_by_name.call_count == 1

        # Second call should also hit inner (no caching)
        result2 = await cached.find_by_name(name)
        assert result2 is skill
        assert inner.find_by_name.call_count == 2

    async def test_returns_none_from_inner(self) -> None:
        """Should return None when inner repo returns None."""
        inner = AsyncMock()
        inner.find_by_name.return_value = None

        cached = CachingRepositoryDecorator(inner)
        name = SkillName("nonexistent")

        result = await cached.find_by_name(name)
        assert result is None
        assert inner.find_by_name.call_count == 1


class TestCachingRepositoryDecoratorGetResourceContent:
    """Tests for get_resource_content caching."""

    async def test_caches_resource_content(self) -> None:
        """Should cache resource content."""
        inner = AsyncMock()
        content = b"test content"
        inner.get_resource_content.return_value = content

        cached = CachingRepositoryDecorator(inner)
        name = SkillName("test-skill")

        # First call should hit inner
        result1 = await cached.get_resource_content(name, "scripts", "test.py")
        assert result1 == content
        assert inner.get_resource_content.call_count == 1

        # Second call should use cache
        result2 = await cached.get_resource_content(name, "scripts", "test.py")
        assert result2 == content
        assert inner.get_resource_content.call_count == 1

    async def test_different_resources_cached_separately(self) -> None:
        """Should cache different resources separately."""
        inner = AsyncMock()
        inner.get_resource_content.side_effect = [b"content1", b"content2"]

        cached = CachingRepositoryDecorator(inner)
        name = SkillName("test-skill")

        result1 = await cached.get_resource_content(name, "scripts", "file1.py")
        result2 = await cached.get_resource_content(name, "scripts", "file2.py")

        assert result1 == b"content1"
        assert result2 == b"content2"
        assert inner.get_resource_content.call_count == 2

    async def test_resource_lru_eviction(self) -> None:
        """Should evict least recently used resources."""
        inner = AsyncMock()
        inner.get_resource_content.side_effect = lambda _n, _t, r: f"{r}".encode()

        cached = CachingRepositoryDecorator(inner, resource_cache_size=2)
        name = SkillName("skill")

        # Fill cache
        await cached.get_resource_content(name, "scripts", "a.py")
        await cached.get_resource_content(name, "scripts", "b.py")
        assert cached.resource_cache_size == 2

        # Add third - should evict a.py
        await cached.get_resource_content(name, "scripts", "c.py")
        assert cached.resource_cache_size == 2


class TestCachingRepositoryDecoratorRefresh:
    """Tests for refresh method."""

    async def test_refresh_clears_resource_cache(self) -> None:
        """Should clear resource cache on refresh."""
        inner = AsyncMock()
        inner.get_resource_content.return_value = b"content"

        cached = CachingRepositoryDecorator(inner)
        name = SkillName("test-skill")

        # Populate cache
        await cached.get_resource_content(name, "scripts", "test.py")
        assert cached.resource_cache_size == 1

        # Refresh should clear cache
        await cached.refresh()
        assert cached.resource_cache_size == 0
        inner.refresh.assert_called_once()


class TestCachingRepositoryDecoratorListAll:
    """Tests for list_all method (not cached)."""

    async def test_list_all_delegates_to_inner(self) -> None:
        """list_all should always delegate to inner repository."""
        inner = AsyncMock()
        skills = [create_mock_skill("skill1"), create_mock_skill("skill2")]
        inner.list_all.return_value = skills

        cached = CachingRepositoryDecorator(inner)

        # Multiple calls should all hit inner
        result1 = await cached.list_all()
        result2 = await cached.list_all()

        assert result1 == skills
        assert result2 == skills
        assert inner.list_all.call_count == 2
