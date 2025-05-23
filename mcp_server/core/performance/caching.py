"""
Result caching with TTL (Time-To-Live) for WinDbg commands.

This module provides intelligent caching of command results with LRU eviction,
TTL expiration, and compression for large results.
"""
import logging
import gzip
import json
import hashlib
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from collections import OrderedDict

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    command: str
    result: str
    timestamp: datetime
    access_count: int = 0
    data_size: int = 0
    compressed: bool = False
    ttl_seconds: int = 300  # 5 minutes default

class ResultCache:
    """LRU cache with TTL for command results."""
    
    def __init__(self, max_size: int = 100, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
    
    def _generate_key(self, command: str, context: Dict[str, Any] = None) -> str:
        """Generate cache key for command and context."""
        key_data = {"command": command.strip().lower()}
        if context:
            key_data["context"] = context
        
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, command: str, context: Dict[str, Any] = None) -> Optional[str]:
        """Get cached result if available and not expired."""
        key = self._generate_key(command, context)
        
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            
            # Check TTL
            age = (datetime.now() - entry.timestamp).total_seconds()
            if age > entry.ttl_seconds:
                del self._cache[key]
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.access_count += 1
            
            return entry.result
    
    def put(self, command: str, result: str, context: Dict[str, Any] = None, ttl: int = None) -> bool:
        """Store result in cache."""
        key = self._generate_key(command, context)
        ttl = ttl or self.default_ttl
        
        with self._lock:
            # Remove oldest entries if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            # Determine if we should compress large results
            data_size = len(result.encode('utf-8'))
            compressed = False
            
            if data_size > 10000:  # Compress results > 10KB
                try:
                    compressed_data = gzip.compress(result.encode('utf-8'))
                    if len(compressed_data) < data_size * 0.8:  # Only if 20%+ savings
                        result = compressed_data.decode('latin-1')  # Store as string
                        compressed = True
                except Exception:
                    pass  # Fall back to uncompressed
            
            entry = CacheEntry(
                command=command,
                result=result,
                timestamp=datetime.now(),
                data_size=data_size,
                compressed=compressed,
                ttl_seconds=ttl
            )
            
            self._cache[key] = entry
            return True
    
    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_size = sum(entry.data_size for entry in self._cache.values())
            compressed_count = sum(1 for entry in self._cache.values() if entry.compressed)
            
            return {
                "entries": len(self._cache),
                "max_size": self.max_size,
                "total_data_size": total_size,
                "compressed_entries": compressed_count,
                "compression_ratio": compressed_count / max(len(self._cache), 1)
            } 