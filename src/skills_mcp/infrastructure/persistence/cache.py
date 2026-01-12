"""Caching repository decorator.

Provides an LRU caching layer for resource content that can wrap any
SkillRepository implementation.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from skills_mcp.domain.models.skill import Skill
    from skills_mcp.domain.models.skill_name import SkillName
    from skills_mcp.domain.repositories import SkillRepository


logger = logging.getLogger(__name__)


# Default cache size
DEFAULT_RESOURCE_CACHE_SIZE = 500


class CachingRepositoryDecorator:
    """Decorator that adds LRU caching for resources to any SkillRepository.

    This decorator wraps a SkillRepository and caches resource content
    (get_resource_content). Skill lookups are NOT cached here because
    LocalSkillRepository and OCISkillRepository already maintain internal
    skill caches.

    The list_all method is NOT cached by this decorator since repositories
    typically cache their own skill list.

    Example:
        inner_repo = LocalSkillRepository([Path("/skills")])
        cached_repo = CachingRepositoryDecorator(inner_repo)
        content = await cached_repo.get_resource_content(name, "scripts", "test.py")
    """

    def __init__(
        self,
        inner: SkillRepository,
        *,
        resource_cache_size: int = DEFAULT_RESOURCE_CACHE_SIZE,
    ) -> None:
        """Initialize the caching decorator.

        Args:
            inner: The repository to wrap with caching.
            resource_cache_size: Maximum number of resources to cache.
        """
        self._inner = inner
        self._resource_cache_size = resource_cache_size

        # LRU cache implemented with OrderedDict
        self._resource_cache: OrderedDict[str, bytes] = OrderedDict()

        # Lock for thread-safe cache access
        self._resource_lock = asyncio.Lock()

    async def list_all(self) -> list[Skill]:
        """List all available skills.

        This method is NOT cached - it delegates directly to the inner repository.
        Most repository implementations already cache their skill list internally.

        Returns:
            List of all available skills.
        """
        return await self._inner.list_all()

    async def find_by_name(self, name: SkillName) -> Skill | None:
        """Find a skill by name.

        This method delegates directly to the inner repository without caching.
        Repository implementations (LocalSkillRepository, OCISkillRepository)
        already maintain internal skill caches.

        Args:
            name: The skill name to search for.

        Returns:
            The matching skill, or None if not found.
        """
        return await self._inner.find_by_name(name)

    async def get_resource_content(
        self, skill_name: SkillName, resource_type: str, resource_name: str
    ) -> bytes:
        """Get resource content, with caching.

        Args:
            skill_name: The name of the skill.
            resource_type: The resource type (scripts, references, or assets).
            resource_name: The filename of the resource.

        Returns:
            The resource content as bytes.

        Raises:
            SkillNotFoundError: If the skill doesn't exist.
            ResourceNotFoundError: If the resource doesn't exist.
        """
        cache_key = f"{skill_name.value}:{resource_type}:{resource_name}"

        # Check cache first (under lock)
        async with self._resource_lock:
            if cache_key in self._resource_cache:
                # Move to end (most recently used)
                self._resource_cache.move_to_end(cache_key)
                logger.debug("Cache hit for resource: %s", cache_key)
                return self._resource_cache[cache_key]

        # Cache miss - fetch from inner repository (outside lock)
        logger.debug("Cache miss for resource: %s", cache_key)
        content = await self._inner.get_resource_content(
            skill_name, resource_type, resource_name
        )

        # Add to cache (under lock, with double-check)
        async with self._resource_lock:
            if cache_key not in self._resource_cache:
                self._resource_cache[cache_key] = content
                self._evict_resource_cache_if_needed()

        return content

    async def refresh(self) -> None:
        """Refresh the repository and clear resource cache.

        Clears the resource cache and delegates to the inner repository's refresh.
        """
        async with self._resource_lock:
            self._resource_cache.clear()
        logger.info("Cleared resource cache")
        await self._inner.refresh()

    def _evict_resource_cache_if_needed(self) -> None:
        """Evict oldest entries if resource cache is over capacity."""
        while len(self._resource_cache) > self._resource_cache_size:
            oldest_key, _ = self._resource_cache.popitem(last=False)
            logger.debug("Evicted resource from cache: %s", oldest_key)

    @property
    def resource_cache_size(self) -> int:
        """Return current number of cached resources."""
        return len(self._resource_cache)
