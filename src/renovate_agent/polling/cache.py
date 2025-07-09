"""
Caching layer for the polling system.

This module provides caching capabilities to reduce GitHub API calls
and improve polling performance.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CacheEntry:
    """Represents a single cache entry with expiration."""

    def __init__(self, value: Any, ttl_seconds: int = 300) -> None:
        self.value = value
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return datetime.now() > self.expires_at

    def is_valid(self) -> bool:
        """Check if this cache entry is still valid."""
        return not self.is_expired()


class PollingCache:
    """
    In-memory cache for polling operations.

    This cache reduces API calls by storing frequently accessed data
    with configurable TTL (time-to-live) values.
    """

    def __init__(self) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_requests": 0,
        }
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            self._stats["total_requests"] += 1

            if key in self._cache:
                entry = self._cache[key]
                if entry.is_valid():
                    self._stats["hits"] += 1
                    return entry.value
                else:
                    # Entry expired, remove it
                    del self._cache[key]
                    self._stats["evictions"] += 1

            self._stats["misses"] += 1
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds (default: 5 minutes)
        """
        async with self._lock:
            self._cache[key] = CacheEntry(value, ttl_seconds)

    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()

    async def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired()
            ]

            for key in expired_keys:
                del self._cache[key]

            self._stats["evictions"] += len(expired_keys)
            return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._stats["total_requests"]
        hit_rate = (
            (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        )

        return {
            "cache_size": len(self._cache),
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total_requests,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
        }


class RepositoryCache:
    """
    Cache for repository-specific data.

    This cache stores repository metadata, PR lists, and other
    repository-specific information with intelligent invalidation.
    """

    def __init__(self, base_cache: PollingCache):
        self.cache = base_cache
        self.default_ttl = 300  # 5 minutes
        self.pr_list_ttl = 120  # 2 minutes for PR lists (more dynamic)
        self.repo_metadata_ttl = 600  # 10 minutes for repository metadata

    def _make_key(self, repo_name: str, data_type: str, extra: str = "") -> str:
        """Create a cache key for repository data."""
        key_parts = [repo_name, data_type]
        if extra:
            key_parts.append(extra)
        return ":".join(key_parts)

    async def get_repository_metadata(self, repo_name: str) -> dict[str, Any] | None:
        """Get cached repository metadata."""
        key = self._make_key(repo_name, "metadata")
        return await self.cache.get(key)

    async def set_repository_metadata(
        self, repo_name: str, metadata: dict[str, Any]
    ) -> None:
        """Cache repository metadata."""
        key = self._make_key(repo_name, "metadata")
        await self.cache.set(key, metadata, self.repo_metadata_ttl)

    async def get_pr_list(
        self, repo_name: str, state: str = "open"
    ) -> list[dict[str, Any]] | None:
        """Get cached PR list for a repository."""
        key = self._make_key(repo_name, "prs", state)
        return await self.cache.get(key)

    async def set_pr_list(
        self, repo_name: str, prs: list[dict[str, Any]], state: str = "open"
    ) -> None:
        """Cache PR list for a repository."""
        key = self._make_key(repo_name, "prs", state)
        await self.cache.set(key, prs, self.pr_list_ttl)

    async def get_pr_details(
        self, repo_name: str, pr_number: str
    ) -> dict[str, Any] | None:
        """Get cached PR details."""
        key = self._make_key(repo_name, "pr_details", pr_number)
        return await self.cache.get(key)

    async def set_pr_details(
        self, repo_name: str, pr_number: str, pr_data: dict[str, Any]
    ) -> None:
        """Cache PR details."""
        key = self._make_key(repo_name, "pr_details", pr_number)
        await self.cache.set(key, pr_data, self.default_ttl)

    async def get_renovate_detection(
        self, repo_name: str, pr_number: str
    ) -> bool | None:
        """Get cached Renovate detection result."""
        key = self._make_key(repo_name, "renovate_detection", pr_number)
        return await self.cache.get(key)

    async def set_renovate_detection(
        self, repo_name: str, pr_number: str, is_renovate: bool
    ) -> None:
        """Cache Renovate detection result."""
        key = self._make_key(repo_name, "renovate_detection", pr_number)
        # Cache Renovate detection for longer since it rarely changes
        await self.cache.set(key, is_renovate, 1800)  # 30 minutes

    async def invalidate_repository(self, repo_name: str) -> None:
        """Invalidate all cache entries for a repository."""
        # This is a simple implementation - in production you might want
        # to track keys by prefix for more efficient invalidation
        pass

    async def get_check_runs_status(
        self, repo_name: str, pr_number: str, head_sha: str
    ) -> str | None:
        """Get cached check runs status."""
        key = self._make_key(repo_name, "check_runs", f"{pr_number}:{head_sha}")
        return await self.cache.get(key)

    async def set_check_runs_status(
        self, repo_name: str, pr_number: str, head_sha: str, status: str
    ) -> None:
        """Cache check runs status."""
        key = self._make_key(repo_name, "check_runs", f"{pr_number}:{head_sha}")
        # Check runs status can change quickly, so shorter TTL
        await self.cache.set(key, status, 60)  # 1 minute


class CacheManager:
    """
    Central cache manager for the polling system.

    This class coordinates all caching operations and provides
    a unified interface for cache management.
    """

    def __init__(self) -> None:
        self.base_cache = PollingCache()
        self.repository_cache = RepositoryCache(self.base_cache)
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the cache manager and background cleanup."""
        logger.info("Starting cache manager")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop the cache manager and cleanup tasks."""
        logger.info("Stopping cache manager")
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired cache entries."""
        while True:
            try:
                await asyncio.sleep(300)  # Run cleanup every 5 minutes
                expired_count = await self.base_cache.cleanup_expired()
                if expired_count > 0:
                    logger.debug(
                        "Cache cleanup completed", expired_entries=expired_count
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Cache cleanup failed", error=str(e))

    def get_repository_cache(self) -> RepositoryCache:
        """Get the repository cache instance."""
        return self.repository_cache

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        base_stats = self.base_cache.get_stats()

        return {
            "base_cache": base_stats,
            "cache_manager": {
                "cleanup_task_running": self._cleanup_task is not None
                and not self._cleanup_task.done(),
            },
        }

    async def clear_all(self) -> None:
        """Clear all caches."""
        await self.base_cache.clear()
        logger.info("All caches cleared")


# Global cache manager instance
_cache_manager: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


async def initialize_cache() -> None:
    """Initialize the global cache manager."""
    cache_manager = get_cache_manager()
    await cache_manager.start()


async def shutdown_cache() -> None:
    """Shutdown the global cache manager."""
    global _cache_manager
    if _cache_manager:
        await _cache_manager.stop()
        _cache_manager = None
