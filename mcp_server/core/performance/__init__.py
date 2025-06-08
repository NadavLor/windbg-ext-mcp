"""
Performance optimization package for WinDbg MCP Extension.

This package provides performance optimization features specifically designed for
kernel debugging over network connections, including data compression, result
caching, streaming for large outputs, and network optimization.

The package is organized into focused modules:
- caching.py: Result caching with TTL (Time-To-Live)
- compression.py: Data compression for large outputs
- streaming.py: Streaming handler for huge results
- command_optimizer.py: Command batching and optimization
- coordinator.py: Main performance optimizer coordinator
"""

# Import core classes and functions
from .compression import DataCompressor, DataSize
from .streaming import StreamingHandler
from .command_optimizer import CommandOptimizer
from .coordinator import (
    PerformanceOptimizer, 
    PerformanceMetrics,
    OptimizationLevel
)

# Global instance for use across the application
performance_optimizer = PerformanceOptimizer(optimization_level=OptimizationLevel.NONE)

# Convenience functions that delegate to the global instance
# Execution functions are in the unified execution system
# Use core.execution.execute_command instead

def stream_large_command(command: str):
    """Stream large command output."""
    yield from performance_optimizer.stream_large_command(command)

def get_performance_report():
    """Get performance optimization report."""
    return performance_optimizer.get_performance_report()

def set_optimization_level(level: OptimizationLevel):
    """Set performance optimization level."""
    performance_optimizer.optimization_level = level
    if level != OptimizationLevel.NONE:
        performance_optimizer.optimize_for_network_debugging()

def clear_performance_caches():
    """Clear all performance caches."""
    performance_optimizer.clear_caches()

__all__ = [
    # Core classes
    "DataCompressor",
    "StreamingHandler",
    "CommandOptimizer",
    "PerformanceOptimizer",
    "PerformanceMetrics",
    "OptimizationLevel",
    "DataSize",
    
    # Global instance
    "performance_optimizer",
    
    # Convenience functions
    "stream_large_command",
    "get_performance_report", 
    "set_optimization_level",
    "clear_performance_caches"
] 