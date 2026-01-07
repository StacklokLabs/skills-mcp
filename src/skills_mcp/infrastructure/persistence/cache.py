"""Caching repository decorator.

Provides an LRU caching layer that can wrap any SkillRepository implementation.
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


# Default cache sizes
DEFAULT_SKILL_CACHE_SIZE = 100
DEFAULT_RESOURCE_CACHE_SIZE = 500


class CachingRepositoryDecorator:
    """Decorator that adds LRU caching to any SkillRepository.

    This decorator wraps a SkillRepository and caches:
    - Individual skill lookups (find_by_name)
    - Resource content (get_resource_content)

    The list_all method is NOT cached by this decorator since repositories
    typically cache their own skill list.

    Example:
        inner_repo = LocalSkillRepository([Path("/skills")])
        cached_repo = CachingRepositoryDecorator(inner_repo)
        skill = await cached_repo.find_by_name(SkillName("data-analysis"))
    """

    def __init__(
        self,
        inner: SkillRepository,
        *,
        skill_cache_size: int = DEFAULT_SKILL_CACHE_SIZE,
        resource_cache_size: int = DEFAULT_RESOURCE_CACHE_SIZE,
    ) -> None:
        """Initialize the caching decorator.

        Args:
            inner: The repository to wrap with caching.
            skill_cache_size: Maximum number of skills to cache.
            resource_cache_size: Maximum number of resources to cache.
        """
        self._inner = inner
        self._skill_cache_size = skill_cache_size
        self._resource_cache_size = resource_cache_size

        # LRU caches implemented with OrderedDict
        self._skill_cache: OrderedDict[str, Skill | None] = OrderedDict()
        self._resource_cache: OrderedDict[str, bytes] = OrderedDict()

        # Locks for thread-safe cache access
        self._skill_lock = asyncio.Lock()
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
        """Find a skill by name, with caching.

        Args:
            name: The skill name to search for.

        Returns:
            The matching skill, or None if not found.
        """
        cache_key = name.value

        # Check cache first (under lock)
        async with self._skill_lock:
            if cache_key in self._skill_cache:
                # Move to end (most recently used)
                self._skill_cache.move_to_end(cache_key)
                logger.debug("Cache hit for skill: %s", cache_key)
                return self._skill_cache[cache_key]

        # Cache miss - fetch from inner repository (outside lock)
        logger.debug("Cache miss for skill: %s", cache_key)
        skill = await self._inner.find_by_name(name)

        # Add to cache (under lock, with double-check)
        async with self._skill_lock:
            if cache_key not in self._skill_cache:
                self._skill_cache[cache_key] = skill
                self._evict_skill_cache_if_needed()

        return skill

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
        """Refresh the repository and clear caches.

        Clears all caches and delegates to the inner repository's refresh.
        """
        async with self._skill_lock:
            self._skill_cache.clear()
        async with self._resource_lock:
            self._resource_cache.clear()
        logger.info("Cleared skill and resource caches")
        await self._inner.refresh()

    def _evict_skill_cache_if_needed(self) -> None:
        """Evict oldest entries if skill cache is over capacity."""
        while len(self._skill_cache) > self._skill_cache_size:
            oldest_key, _ = self._skill_cache.popitem(last=False)
            logger.debug("Evicted skill from cache: %s", oldest_key)

    def _evict_resource_cache_if_needed(self) -> None:
        """Evict oldest entries if resource cache is over capacity."""
        while len(self._resource_cache) > self._resource_cache_size:
            oldest_key, _ = self._resource_cache.popitem(last=False)
            logger.debug("Evicted resource from cache: %s", oldest_key)

    @property
    def skill_cache_size(self) -> int:
        """Return current number of cached skills."""
        return len(self._skill_cache)

    @property
    def resource_cache_size(self) -> int:
        """Return current number of cached resources."""
        return len(self._resource_cache)
