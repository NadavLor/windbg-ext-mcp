"""
Unified execution system for WinDbg MCP Server.

This module provides a centralized execution layer that combines:
- Resilient retry logic
- Performance optimization (caching, compression)
- Timeout management
- Error handling
- Metadata collection
"""

from .executor import UnifiedCommandExecutor, ExecutionContext, ExecutionResult
from .result import ExecutionMode
from .strategies import (
    ExecutionStrategy, DirectStrategy, ResilientStrategy, 
    OptimizedStrategy, AsyncStrategy
)
from .timeout_resolver import TimeoutResolver

# Main execution instance - singleton for consistency
_global_executor = None

def get_executor() -> UnifiedCommandExecutor:
    """Get the global command executor instance."""
    global _global_executor
    if _global_executor is None:
        _global_executor = UnifiedCommandExecutor()
    return _global_executor

def execute_command(
    command: str,
    resilient: bool = True,
    optimize: bool = True,
    async_mode: bool = False,
    timeout_category: str = None,
    context: dict = None
) -> ExecutionResult:
    """
    Convenience function for executing commands with unified execution system.
    
    Args:
        command: WinDbg command to execute
        resilient: Whether to use resilient execution with retries
        optimize: Whether to use performance optimization
        async_mode: Whether to execute asynchronously  
        timeout_category: Optional timeout category override
        context: Optional execution context
        
    Returns:
        ExecutionResult with success status, result, and metadata
    """
    executor = get_executor()
    return executor.execute(
        command=command,
        resilient=resilient,
        optimize=optimize,
        async_mode=async_mode,
        timeout_category=timeout_category,
        context=context
    )

__all__ = [
    'UnifiedCommandExecutor',
    'ExecutionContext',
    'ExecutionResult',
    'ExecutionMode',
    'ExecutionStrategy',
    'DirectStrategy',
    'ResilientStrategy',
    'OptimizedStrategy',
    'AsyncStrategy',
    'TimeoutResolver',
    'get_executor',
    'execute_command',
]
