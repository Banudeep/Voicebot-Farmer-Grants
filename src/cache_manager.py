"""
Cache Manager for USDA Voicebot

Provides TTL-based in-memory caching for:
- NASS API responses (crop data)
- Service center lookups
- Program searches

Uses cachetools for TTL caching with configurable expiration.
"""

import hashlib
import json
from functools import wraps
from typing import Any, Callable, Optional
import time
from pathlib import Path

# Try to import cachetools, fallback to simple dict cache
try:
    from cachetools import TTLCache
    HAS_CACHETOOLS = True
except ImportError:
    HAS_CACHETOOLS = False

from logging_config import get_logger

logger = get_logger("voicebot.cache")

# Path: src/cache_manager.py -> src -> root
BASE_DIR = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "cache"
# Cache configuration (in seconds)
CACHE_TTL = {
    "nass_api": 3600,       # 1 hour - NASS data changes daily at most
    "service_center": 86400, # 24 hours - service center data is static
    "programs": 86400,       # 24 hours - program data is static
    "news": 1800,            # 30 minutes - news updates more frequently
    "default": 300,          # 5 minutes - default TTL
}

CACHE_MAX_SIZE = 1000  # Maximum items per cache


class SimpleCache:
    """Simple TTL cache fallback if cachetools is not installed"""
    
    def __init__(self, maxsize: int = 100, ttl: int = 300):
        self._cache: dict = {}
        self._timestamps: dict = {}
        self._maxsize = maxsize
        self._ttl = ttl
    
    def get(self, key: str, default=None):
        if key in self._cache:
            if time.time() - self._timestamps[key] < self._ttl:
                return self._cache[key]
            else:
                # Expired
                del self._cache[key]
                del self._timestamps[key]
        return default
    
    def __setitem__(self, key: str, value: Any):
        # Evict oldest if full
        if len(self._cache) >= self._maxsize:
            oldest_key = min(self._timestamps, key=self._timestamps.get)
            del self._cache[oldest_key]
            del self._timestamps[oldest_key]
        
        self._cache[key] = value
        self._timestamps[key] = time.time()
    
    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
    
    def clear(self):
        self._cache.clear()
        self._timestamps.clear()


# Create cache instances
_caches: dict = {}


def get_cache(name: str, ttl: Optional[int] = None) -> Any:
    """Get or create a cache instance by name"""
    if name not in _caches:
        cache_ttl = ttl or CACHE_TTL.get(name, CACHE_TTL["default"])
        if HAS_CACHETOOLS:
            _caches[name] = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=cache_ttl)
        else:
            _caches[name] = SimpleCache(maxsize=CACHE_MAX_SIZE, ttl=cache_ttl)
        logger.debug(f"Created cache '{name}' with TTL={cache_ttl}s")
    return _caches[name]


def generate_cache_key(*args, **kwargs) -> str:
    """Generate a cache key from function arguments"""
    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return hashlib.md5(key_data.encode()).hexdigest()


def cached(cache_name: str, ttl: Optional[int] = None):
    """
    Decorator for caching function results with TTL.
    
    Usage:
        @cached("nass_api")
        async def fetch_nass_data(filters: dict):
            ...
    
    Args:
        cache_name: Name of the cache to use (determines TTL)
        ttl: Optional TTL override in seconds
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache = get_cache(cache_name, ttl)
            key = generate_cache_key(func.__name__, *args, **kwargs)
            
            # Check cache
            if key in cache:
                logger.debug(f"Cache HIT for {func.__name__}")
                return cache.get(key)
            
            # Execute function
            logger.debug(f"Cache MISS for {func.__name__}")
            result = await func(*args, **kwargs)
            
            # Store in cache (only cache successful results)
            if isinstance(result, dict) and result.get("success", True):
                cache[key] = result
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache = get_cache(cache_name, ttl)
            key = generate_cache_key(func.__name__, *args, **kwargs)
            
            if key in cache:
                logger.debug(f"Cache HIT for {func.__name__}")
                return cache.get(key)
            
            logger.debug(f"Cache MISS for {func.__name__}")
            result = func(*args, **kwargs)
            
            if isinstance(result, dict) and result.get("success", True):
                cache[key] = result
            
            return result
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def clear_cache(cache_name: Optional[str] = None):
    """Clear a specific cache or all caches"""
    if cache_name:
        if cache_name in _caches:
            _caches[cache_name].clear()
            logger.info(f"Cleared cache: {cache_name}")
    else:
        for name, cache in _caches.items():
            cache.clear()
        logger.info("Cleared all caches")


def get_cache_stats() -> dict:
    """Get statistics for all caches"""
    stats = {}
    for name, cache in _caches.items():
        if HAS_CACHETOOLS:
            stats[name] = {
                "size": len(cache),
                "maxsize": cache.maxsize,
                "ttl": cache.ttl
            }
        else:
            stats[name] = {
                "size": len(cache._cache),
                "maxsize": cache._maxsize,
                "ttl": cache._ttl
            }
    return stats


if __name__ == "__main__":
    # Test caching
    import asyncio
    
    @cached("default")
    async def expensive_operation(x: int) -> dict:
        print(f"Computing for {x}...")
        await asyncio.sleep(0.1)
        return {"success": True, "result": x * 2}
    
    async def test():
        # First call - cache miss
        result1 = await expensive_operation(5)
        print(f"Result 1: {result1}")
        
        # Second call - cache hit
        result2 = await expensive_operation(5)
        print(f"Result 2: {result2}")
        
        print(f"Cache stats: {get_cache_stats()}")
        print("✓ Cache manager test complete")
    
    asyncio.run(test())
