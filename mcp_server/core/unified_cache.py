"""
Unified caching system for WinDbg MCP Extension.

This module consolidates all caching functionality into a single, coherent system
that handles command-level caching, composite results (like session snapshots),
and context-aware cache management with different TTL strategies.

Replaces the separate startup cache, session cache, and performance cache
with a unified approach that eliminates redundancy and improves performance.
"""
import logging
import time
import threading
import hashlib
import json
import gzip
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import OrderedDict
from enum import Enum

logger = logging.getLogger(__name__)

class CacheContext(Enum):
    """Different cache contexts with different behaviors."""
    STARTUP = "startup"           # Startup-only cache, cleared after init
    COMMAND = "command"           # Individual command results
    SESSION = "session"           # Session snapshots and composite data
    PERFORMANCE = "performance"   # Performance-optimized command caching

class CachePriority(Enum):
    """Cache priority levels for eviction."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class UnifiedCacheEntry:
    """Unified cache entry with full metadata."""
    key: str
    data: Any
    context: CacheContext
    timestamp: datetime
    ttl_seconds: int
    access_count: int = 0
    last_access: Optional[datetime] = None
    priority: CachePriority = CachePriority.NORMAL
    compressed: bool = False
    data_size: int = 0
    command: Optional[str] = None  # Original command for command-level entries
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > self.ttl_seconds
    
    def touch(self):
        """Update access information."""
        self.access_count += 1
        self.last_access = datetime.now()

class UnifiedCache:
    """
    Unified caching system that handles all caching needs.
    
    Features:
    - Context-aware caching (startup, command, session, performance)
    - TTL with different strategies per context
    - LRU eviction with priority support
    - Automatic compression for large data
    - Thread-safe operations
    - Smart invalidation based on context relationships
    """
    
    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._cache: OrderedDict[str, UnifiedCacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._startup_active = False
        
        # Context-specific TTL defaults (in seconds)
        self._default_ttls = {
            CacheContext.STARTUP: 0,       # No TTL - cleared manually
            CacheContext.COMMAND: 300,     # 5 minutes
            CacheContext.SESSION: 30,      # 30 seconds for session snapshots
            CacheContext.PERFORMANCE: 600  # 10 minutes for performance data
        }
        
        # Command-specific TTL overrides
        self._command_ttls = {
            "version": 1800,        # 30 minutes - version rarely changes
            "lm": 900,             # 15 minutes - modules change infrequently
            ".effmach": 1800,      # 30 minutes - machine type is static
            "!pcr": 600,           # 10 minutes - PCR changes rarely
            "vertarget": 300,      # 5 minutes - target connection can change
            "r": 5,                # 5 seconds - registers change frequently
            "k": 30,               # 30 seconds - call stack changes
            "!thread": 60,         # 1 minute - thread state changes
            "bl": 120,             # 2 minutes - breakpoints change occasionally
        }
        
    def _generate_key(self, command_or_id: str, context: CacheContext, extra_context: Dict[str, Any] = None) -> str:
        """Generate cache key with context and optional extra context."""
        key_data = {
            "base": command_or_id.strip().lower() if isinstance(command_or_id, str) else str(command_or_id),
            "context": context.value
        }
        if extra_context:
            key_data["extra"] = extra_context
        
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_ttl(self, context: CacheContext, command: str = None) -> int:
        """Get TTL for context and command."""
        if context == CacheContext.STARTUP:
            return 0  # No TTL for startup cache
        
        if context == CacheContext.COMMAND and command:
            # Check command-specific TTL
            command_lower = command.lower().strip()
            for cmd_pattern, ttl in self._command_ttls.items():
                if cmd_pattern in command_lower:
                    return ttl
        
        return self._default_ttls.get(context, 300)
    
    def _should_compress(self, data: Any) -> bool:
        """Determine if data should be compressed."""
        if isinstance(data, str):
            return len(data.encode('utf-8')) > 10000  # Compress if > 10KB
        elif isinstance(data, dict):
            return len(json.dumps(data).encode('utf-8')) > 10000
        return False
    
    def _compress_data(self, data: Any) -> tuple[Any, bool]:
        """Compress data if beneficial."""
        if not self._should_compress(data):
            return data, False
        
        try:
            if isinstance(data, str):
                compressed = gzip.compress(data.encode('utf-8'))
                if len(compressed) < len(data.encode('utf-8')) * 0.8:  # 20% savings
                    return compressed.decode('latin-1'), True
            elif isinstance(data, dict):
                json_str = json.dumps(data)
                compressed = gzip.compress(json_str.encode('utf-8'))
                if len(compressed) < len(json_str.encode('utf-8')) * 0.8:
                    return compressed.decode('latin-1'), True
        except Exception:
            pass  # Fall back to uncompressed
        
        return data, False
    
    def _decompress_data(self, data: Any, was_compressed: bool) -> Any:
        """Decompress data if it was compressed."""
        if not was_compressed:
            return data
        
        try:
            if isinstance(data, str):
                # Try to decompress
                compressed_bytes = data.encode('latin-1')
                decompressed_bytes = gzip.decompress(compressed_bytes)
                return decompressed_bytes.decode('utf-8')
        except Exception:
            logger.warning("Failed to decompress cached data")
        
        return data
    
    def _evict_if_needed(self):
        """Evict entries if cache is at capacity."""
        while len(self._cache) >= self.max_size:
            # Find entry with lowest priority and oldest access
            oldest_entry = None
            oldest_key = None
            
            for key, entry in self._cache.items():
                if oldest_entry is None or (
                    entry.priority.value < oldest_entry.priority.value or
                    (entry.priority == oldest_entry.priority and 
                     (entry.last_access or entry.timestamp) < (oldest_entry.last_access or oldest_entry.timestamp))
                ):
                    oldest_entry = entry
                    oldest_key = key
            
            if oldest_key:
                del self._cache[oldest_key]
                logger.debug(f"Evicted cache entry: {oldest_key}")
    
    def get(self, command_or_id: str, context: CacheContext, extra_context: Dict[str, Any] = None) -> Optional[Any]:
        """Get cached data."""
        key = self._generate_key(command_or_id, context, extra_context)
        
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            
            # Check if entry is expired (except for startup context)
            if context != CacheContext.STARTUP and entry.is_expired():
                del self._cache[key]
                logger.debug(f"Cache entry expired: {command_or_id}")
                return None
            
            # Update access info and move to end (most recent)
            entry.touch()
            self._cache.move_to_end(key)
            
            # Decompress if needed
            data = self._decompress_data(entry.data, entry.compressed)
            
            logger.debug(f"Cache hit: {command_or_id} (context: {context.value}, age: {(datetime.now() - entry.timestamp).total_seconds():.1f}s)")
            return data
    
    def put(self, command_or_id: str, data: Any, context: CacheContext, 
            extra_context: Dict[str, Any] = None, ttl: int = None, 
            priority: CachePriority = CachePriority.NORMAL) -> bool:
        """Store data in cache."""
        key = self._generate_key(command_or_id, context, extra_context)
        
        # Skip caching for startup context if not active
        if context == CacheContext.STARTUP and not self._startup_active:
            return False
        
        ttl = ttl or self._get_ttl(context, command_or_id if isinstance(command_or_id, str) else None)
        
        with self._lock:
            # Evict if needed
            self._evict_if_needed()
            
            # Compress data if beneficial
            compressed_data, was_compressed = self._compress_data(data)
            
            # Calculate data size
            if isinstance(data, str):
                data_size = len(data.encode('utf-8'))
            elif isinstance(data, dict):
                data_size = len(json.dumps(data).encode('utf-8'))
            else:
                data_size = len(str(data).encode('utf-8'))
            
            entry = UnifiedCacheEntry(
                key=key,
                data=compressed_data,
                context=context,
                timestamp=datetime.now(),
                ttl_seconds=ttl,
                priority=priority,
                compressed=was_compressed,
                data_size=data_size,
                command=command_or_id if isinstance(command_or_id, str) else None
            )
            
            self._cache[key] = entry
            logger.debug(f"Cached: {command_or_id} (context: {context.value}, TTL: {ttl}s, compressed: {was_compressed})")
            return True
    
    def invalidate(self, command_or_id: str = None, context: CacheContext = None, pattern: str = None) -> int:
        """Invalidate cache entries by command, context, or pattern."""
        removed_count = 0
        
        with self._lock:
            keys_to_remove = []
            
            for key, entry in self._cache.items():
                should_remove = False
                
                if command_or_id and entry.command == command_or_id:
                    should_remove = True
                elif context and entry.context == context:
                    should_remove = True
                elif pattern and pattern.lower() in (entry.command or "").lower():
                    should_remove = True
                
                if should_remove:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._cache[key]
                removed_count += 1
        
        if removed_count > 0:
            logger.debug(f"Invalidated {removed_count} cache entries")
        
        return removed_count
    
    def clear_context(self, context: CacheContext) -> int:
        """Clear all entries for a specific context."""
        return self.invalidate(context=context)
    
    def clear_all(self):
        """Clear all cache entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.debug(f"Cleared all cache entries ({count} total)")
    
    def start_startup_caching(self):
        """Enable startup caching context."""
        self._startup_active = True
        logger.debug("Startup caching enabled")
    
    def stop_startup_caching(self):
        """Disable startup caching and clear startup entries."""
        removed = self.clear_context(CacheContext.STARTUP)
        self._startup_active = False
        logger.info(f"Startup caching disabled - cleared {removed} startup cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        with self._lock:
            stats_by_context = {}
            total_size = 0
            compressed_count = 0
            
            for entry in self._cache.values():
                context_name = entry.context.value
                if context_name not in stats_by_context:
                    stats_by_context[context_name] = {
                        "count": 0,
                        "size": 0,
                        "compressed": 0
                    }
                
                stats_by_context[context_name]["count"] += 1
                stats_by_context[context_name]["size"] += entry.data_size
                
                if entry.compressed:
                    stats_by_context[context_name]["compressed"] += 1
                    compressed_count += 1
                
                total_size += entry.data_size
            
            return {
                "total_entries": len(self._cache),
                "max_size": self.max_size,
                "total_data_size": total_size,
                "total_compressed": compressed_count,
                "contexts": stats_by_context,
                "startup_active": self._startup_active
            }

# Global unified cache instance
unified_cache = UnifiedCache(max_size=500)

# Convenience functions for different contexts
def cache_command_result(command: str, result: str, ttl: int = None) -> bool:
    """Cache a command result."""
    return unified_cache.put(command, result, CacheContext.COMMAND, ttl=ttl)

def get_cached_command_result(command: str) -> Optional[str]:
    """Get cached command result."""
    return unified_cache.get(command, CacheContext.COMMAND)

def cache_session_snapshot(session_id: str, snapshot: Any) -> bool:
    """Cache a session snapshot."""
    return unified_cache.put(session_id, snapshot, CacheContext.SESSION, priority=CachePriority.HIGH)

def get_cached_session_snapshot(session_id: str = "current") -> Optional[Any]:
    """Get cached session snapshot."""
    return unified_cache.get(session_id, CacheContext.SESSION)

def clear_session_cache():
    """Clear session cache entries."""
    unified_cache.clear_context(CacheContext.SESSION)

def start_startup_cache():
    """Enable startup caching."""
    unified_cache.start_startup_caching()

def stop_startup_cache():
    """Disable startup caching.""" 
    unified_cache.stop_startup_caching()

def cache_startup_command(command: str, result: str) -> bool:
    """Cache a startup command result."""
    return unified_cache.put(command, result, CacheContext.STARTUP, priority=CachePriority.CRITICAL)

def get_startup_cached_result(command: str) -> Optional[str]:
    """Get startup cached command result."""
    return unified_cache.get(command, CacheContext.STARTUP)

def invalidate_command_cache(command: str = None, pattern: str = None) -> int:
    """Invalidate command cache entries."""
    if command:
        return unified_cache.invalidate(command_or_id=command, context=CacheContext.COMMAND)
    elif pattern:
        return unified_cache.invalidate(context=CacheContext.COMMAND, pattern=pattern)
    else:
        return unified_cache.clear_context(CacheContext.COMMAND)

def get_cache_stats() -> Dict[str, Any]:
    """Get unified cache statistics."""
    return unified_cache.get_stats() 