"""
Main performance optimization coordinator.

This module coordinates all performance optimization features including
caching, compression, streaming, and command optimization.
"""
import logging
import time
import threading
from typing import Dict, Any, List, Tuple, Generator
from dataclasses import dataclass, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

from .caching import ResultCache
from .compression import DataCompressor
from .streaming import StreamingHandler
from .command_optimizer import CommandOptimizer
from ..connection_resilience import execute_resilient_command

logger = logging.getLogger(__name__)

class OptimizationLevel(Enum):
    """Performance optimization levels."""
    NONE = "none"
    BASIC = "basic"
    AGGRESSIVE = "aggressive"
    MAXIMUM = "maximum"

@dataclass
class PerformanceMetrics:
    """Performance metrics tracking."""
    total_commands: int = 0
    cached_hits: int = 0
    cache_miss: int = 0
    compression_saves: int = 0
    total_bytes_transferred: int = 0
    total_bytes_saved: int = 0
    average_command_time: float = 0.0
    network_latency: float = 0.0

class PerformanceOptimizer:
    """Main performance optimization coordinator."""
    
    def __init__(self, optimization_level: OptimizationLevel = OptimizationLevel.AGGRESSIVE):
        self.optimization_level = optimization_level
        self.cache = ResultCache(max_size=200 if optimization_level != OptimizationLevel.NONE else 0)
        self.compressor = DataCompressor()
        self.streaming = StreamingHandler()
        self.command_optimizer = CommandOptimizer()
        self.metrics = PerformanceMetrics()
        self._lock = threading.Lock()
        
        # Thread pool for async operations
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="PerfOpt")
        
    def execute_optimized_command(
        self,
        command: str,
        timeout_category: str = "normal",
        context: Dict[str, Any] = None,
        force_fresh: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Execute command with all optimizations applied."""
        start_time = time.time()
        
        # Update metrics
        with self._lock:
            self.metrics.total_commands += 1
        
        # Check cache first (unless forced fresh)
        if not force_fresh and self.optimization_level != OptimizationLevel.NONE:
            should_cache, ttl = self.command_optimizer.should_cache_command(command)
            
            if should_cache:
                cached_result = self.cache.get(command, context)
                if cached_result:
                    with self._lock:
                        self.metrics.cached_hits += 1
                    
                    # Decompress if needed
                    if isinstance(cached_result, bytes) or (isinstance(cached_result, str) and len(cached_result) > 0 and ord(cached_result[0]) == 31):
                        try:
                            cached_result = self.compressor.decompress_text(cached_result, True)
                        except:
                            pass
                    
                    execution_time = time.time() - start_time
                    metadata = {
                        "cached": True,
                        "response_time": execution_time,
                        "cache_hit": True,
                        "optimization_level": self.optimization_level.value
                    }
                    return True, cached_result, metadata
        
        # Cache miss - execute command
        with self._lock:
            self.metrics.cache_miss += 1
        
        # Execute with resilience
        success, result, metadata = execute_resilient_command(command, timeout_category)
        
        if success:
            # Measure network transfer size
            data_size = len(result.encode('utf-8'))
            with self._lock:
                self.metrics.total_bytes_transferred += data_size
            
            # Apply compression if beneficial
            if self.optimization_level in [OptimizationLevel.AGGRESSIVE, OptimizationLevel.MAXIMUM]:
                compressed_result, was_compressed = self.compressor.compress_text(result)
                if was_compressed:
                    compressed_size = len(compressed_result) if isinstance(compressed_result, bytes) else len(compressed_result.encode('utf-8'))
                    with self._lock:
                        self.metrics.compression_saves += 1
                        self.metrics.total_bytes_saved += (data_size - compressed_size)
            else:
                compressed_result, was_compressed = result, False
            
            # Cache result if appropriate
            if self.optimization_level != OptimizationLevel.NONE:
                should_cache, ttl = self.command_optimizer.should_cache_command(command)
                if should_cache:
                    self.cache.put(command, compressed_result if was_compressed else result, context, ttl)
            
            # Update performance metrics
            execution_time = time.time() - start_time
            with self._lock:
                if self.metrics.average_command_time == 0:
                    self.metrics.average_command_time = execution_time
                else:
                    # Exponential moving average
                    alpha = 0.1
                    self.metrics.average_command_time = (
                        alpha * execution_time + (1 - alpha) * self.metrics.average_command_time
                    )
            
            # Add optimization metadata
            metadata.update({
                "cached": False,
                "compressed": was_compressed,
                "original_size": data_size,
                "optimization_level": self.optimization_level.value,
                "cache_ttl": ttl if should_cache else 0
            })
            
            if was_compressed:
                metadata["compressed_size"] = len(compressed_result) if isinstance(compressed_result, bytes) else len(compressed_result.encode('utf-8'))
                metadata["compression_ratio"] = metadata["compressed_size"] / data_size
        
        return success, result, metadata
    
    def stream_large_command(self, command: str, timeout_category: str = "bulk") -> Generator[Dict[str, Any], None, None]:
        """Stream large command output with optimization."""
        if self.optimization_level == OptimizationLevel.NONE:
            # Fallback to regular execution
            success, result, metadata = execute_resilient_command(command, timeout_category)
            yield {
                "type": "complete",
                "data": result,
                "metadata": metadata
            }
        else:
            yield from self.streaming.stream_large_output(command, timeout_category)
    
    def execute_command_batch(self, commands: List[str]) -> Dict[str, Any]:
        """Execute multiple commands with optimization."""
        if not commands:
            return {"results": [], "optimization": "empty_batch"}
        
        if len(commands) == 1:
            success, result, metadata = self.execute_optimized_command(commands[0])
            return {
                "results": [{"command": commands[0], "success": success, "result": result, "metadata": metadata}],
                "optimization": "single_command"
            }
        
        # Optimize command sequence
        batches = self.command_optimizer.optimize_command_sequence(commands)
        
        results = []
        total_time = 0
        
        for batch in batches:
            batch_start = time.time()
            
            for command in batch:
                success, result, metadata = self.execute_optimized_command(command)
                results.append({
                    "command": command,
                    "success": success, 
                    "result": result,
                    "metadata": metadata
                })
            
            batch_time = time.time() - batch_start
            total_time += batch_time
        
        return {
            "results": results,
            "optimization": "batched",
            "batch_count": len(batches),
            "total_time": total_time,
            "commands_per_second": len(commands) / max(total_time, 0.001)
        }
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report."""
        cache_stats = self.cache.get_stats()
        
        with self._lock:
            metrics = asdict(self.metrics)
        
        # Calculate performance indicators
        cache_hit_rate = metrics["cached_hits"] / max(metrics["total_commands"], 1)
        compression_rate = metrics["compression_saves"] / max(metrics["total_commands"], 1)
        bytes_saved_percent = metrics["total_bytes_saved"] / max(metrics["total_bytes_transferred"], 1) * 100
        
        return {
            "optimization_level": self.optimization_level.value,
            "performance_metrics": metrics,
            "cache_statistics": cache_stats,
            "performance_indicators": {
                "cache_hit_rate": cache_hit_rate,
                "compression_rate": compression_rate,
                "bytes_saved_percent": bytes_saved_percent,
                "average_command_time": metrics["average_command_time"]
            },
            "recommendations": self._get_performance_recommendations(cache_hit_rate, compression_rate, metrics)
        }
    
    def optimize_for_network_debugging(self):
        """Apply specific optimizations for network debugging scenarios."""
        # Increase cache sizes for network debugging
        if self.optimization_level != OptimizationLevel.NONE:
            self.cache.max_size = 300
            self.cache.default_ttl = 600  # 10 minutes
        
        # Adjust compression thresholds for network
        # Note: compressor.min_size is accessed via static methods
        
        # Optimize streaming chunk size for network
        self.streaming.chunk_size = 2048
        
        logger.info("Applied network debugging optimizations")
    
    def clear_caches(self):
        """Clear all caches and reset metrics."""
        self.cache.clear()
        with self._lock:
            self.metrics = PerformanceMetrics()
        logger.info("Cleared performance caches and metrics")
    
    def _get_performance_recommendations(self, cache_hit_rate: float, compression_rate: float, metrics: Dict[str, Any]) -> List[str]:
        """Get performance optimization recommendations."""
        recommendations = []
        
        if cache_hit_rate < 0.3:
            recommendations.append("🔄 Low cache hit rate - consider increasing cache TTL for stable commands")
        elif cache_hit_rate > 0.8:
            recommendations.append("✅ Excellent cache performance")
        
        if compression_rate < 0.1 and metrics["total_bytes_transferred"] > 1000000:
            recommendations.append("📦 Consider enabling compression for large data transfers")
        
        if metrics["average_command_time"] > 5.0:
            recommendations.append("⏱️ Slow command execution - check network connectivity and VM performance")
        
        if metrics["total_bytes_transferred"] > 10000000:  # 10MB
            recommendations.append("📊 High data transfer volume - streaming optimization recommended")
        
        if not recommendations:
            recommendations.append("🚀 Performance optimization is working well")
        
        return recommendations 