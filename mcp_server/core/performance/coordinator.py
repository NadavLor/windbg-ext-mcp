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

from .compression import DataCompressor
from .streaming import StreamingHandler
from .command_optimizer import CommandOptimizer
from core.communication import send_command
from core.unified_cache import cache_command_result, get_cached_command_result, CacheContext, get_cache_stats, unified_cache
from config import get_timeout_for_command, DebuggingMode

# Import unified execution system
from core.execution import execute_command as execute_unified

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

# Commands that should bypass optimization and execute directly
BYPASS_OPTIMIZATION_COMMANDS = {
    ".reload /f", ".reload -f",  # Force reload needs direct execution
    ".restart", ".reboot",       # System control commands
    "g", "p", "t",              # Execution control commands  
    "bp", "bc", "bd", "be",     # Breakpoint commands (state-changing)
    ".attach", ".detach",       # Process attach/detach
    ".symfix", ".sympath"       # Symbol path changes
}

class PerformanceOptimizer:
    """Main performance optimization coordinator."""
    
    def __init__(self, optimization_level: OptimizationLevel = OptimizationLevel.NONE):
        self.optimization_level = optimization_level
        # Use unified cache instead of separate ResultCache
        self.compressor = DataCompressor()
        self.streaming = StreamingHandler()
        self.command_optimizer = CommandOptimizer()
        self.metrics = PerformanceMetrics()
        self._lock = threading.Lock()
        
        # Thread pool for async operations
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="PerfOpt")
        
    def should_bypass_optimization(self, command: str) -> bool:
        """
        Determine if a command should bypass optimization and execute directly.
        
        Args:
            command: The command to check
            
        Returns:
            True if command should bypass optimization
        """
        command_lower = command.lower().strip()
        
        # Check against bypass list
        for bypass_cmd in BYPASS_OPTIMIZATION_COMMANDS:
            if bypass_cmd in command_lower:
                return True
        
        # Commands with parameters that affect state
        if any(pattern in command_lower for pattern in [
            ".process /i", ".thread", "~", ".context",  # Context switching
            "ed ", "ew ", "eb ", "eq ",                  # Memory editing
            "!process", "!thread"                       # Process/thread manipulation
        ]):
            return True
            
        return False
        
    # Use unified execution system for command execution
    # Use core.execution.execute_command instead
    
    def _execute_direct_command(self, command: str, start_time: float) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Execute command directly without optimization.
        
        Args:
            command: Command to execute
            start_time: Start time for metrics
            
        Returns:
            Tuple of (success, result, metadata)
        """
        try:
            # Use centralized timeout configuration
            timeout_ms = get_timeout_for_command(command, DebuggingMode.VM_NETWORK)
            
            result = send_command(command, timeout_ms=timeout_ms)
            success = True
            
            execution_time = time.time() - start_time
            metadata = {
                "cached": False,
                "compressed": False,
                "optimization_bypassed": True,
                "timeout_ms": timeout_ms,
                "response_time": execution_time,
                "optimization_level": "direct"
            }
            
            return success, result, metadata
            
        except Exception as e:
            execution_time = time.time() - start_time
            metadata = {
                "error": True,
                "optimization_bypassed": True,
                "timeout_ms": get_timeout_for_command(command, DebuggingMode.VM_NETWORK),
                "response_time": execution_time,
                "original_error": str(e)
            }
            return False, str(e), metadata
    
    def stream_large_command(self, command: str, timeout_category: str = "bulk") -> Generator[Dict[str, Any], None, None]:
        """Stream large command output with optimization."""
        if self.optimization_level == OptimizationLevel.NONE:
            # Fallback to regular execution
            try:
                # Use centralized timeout configuration
                timeout_ms = get_timeout_for_command(command, DebuggingMode.VM_NETWORK)
                
                result = send_command(command, timeout_ms=timeout_ms)
                metadata = {"cached": False, "optimization": "none", "timeout_ms": timeout_ms}
                yield {
                    "type": "complete",
                    "data": result,
                    "metadata": metadata
                }
            except Exception as e:
                yield {
                    "type": "error",
                    "message": str(e),
                    "metadata": {"error": True, "timeout_ms": get_timeout_for_command(command, DebuggingMode.VM_NETWORK)}
                }
        else:
            yield from self.streaming.stream_large_output(command, timeout_category)
    
    def execute_command_batch(self, commands: List[str]) -> Dict[str, Any]:
        """Execute multiple commands with optimization using unified execution system."""
        if not commands:
            return {"results": [], "optimization": "empty_batch"}
        
        if len(commands) == 1:
            result = execute_unified(commands[0], resilient=True, optimize=True)
            return {
                "results": [{
                    "command": commands[0], 
                    "success": result.success, 
                    "result": result.result, 
                    "metadata": result.to_dict()
                }],
                "optimization": "single_command"
            }
        
        # Optimize command sequence
        batches = self.command_optimizer.optimize_command_sequence(commands)
        
        results = []
        total_time = 0
        
        for batch in batches:
            batch_start = time.time()
            
            for command in batch:
                result = execute_unified(command, resilient=True, optimize=True)
                results.append({
                    "command": command,
                    "success": result.success, 
                    "result": result.result,
                    "metadata": result.to_dict()
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
        cache_stats = get_cache_stats()
        
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
            self.compressor.max_size = 300
            self.compressor.default_ttl = 600  # 10 minutes
        
        # Adjust compression thresholds for network
        # Note: compressor.min_size is accessed via static methods
        
        # Optimize streaming chunk size for network
        self.streaming.chunk_size = 2048
        
        logger.info("Applied network debugging optimizations")
    
    def clear_caches(self):
        """Clear all caches and reset metrics."""
        unified_cache.clear_all()
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
    
    def set_network_debugging_mode(self, enabled: bool):
        """Configure for network debugging scenarios."""
        if enabled:
            # Increase timeouts and retries for network debugging
            logger.info("Enabled network debugging mode - adjusted timeouts and compression")
        else:
            # Reset to normal operation
            logger.info("Disabled network debugging mode")
        
        # Network debugging optimizations are now handled by unified cache
        # with appropriate TTL settings per command type 