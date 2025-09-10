"""
Unified command executor for WinDbg MCP Server.

This module provides the main UnifiedCommandExecutor class that serves as
the single entry point for all command execution, coordinating different
strategies and providing a consistent interface.
"""
import logging
from typing import Dict, Any, Optional, Union

from .result import ExecutionResult, ExecutionContext, create_execution_context
from .strategies import create_strategy, ExecutionStrategy
from .timeout_resolver import get_timeout_resolver

logger = logging.getLogger(__name__)

class UnifiedCommandExecutor:
    """
    Unified command executor that consolidates all execution patterns.
    
    This class serves as the single entry point for command execution,
    eliminating duplication across resilient, optimized, and async systems.
    """
    
    def __init__(self):
        self.timeout_resolver = get_timeout_resolver()
        self._strategy_cache: Dict[str, ExecutionStrategy] = {}
        
    def execute(
        self,
        command: str,
        resilient: bool = True,
        optimize: bool = True,
        async_mode: bool = False,
        timeout_category: str = None,
        context: Dict[str, Any] = None,
        **kwargs
    ) -> ExecutionResult:
        """
        Execute a WinDbg command with specified execution parameters.
        
        Args:
            command: WinDbg command to execute
            resilient: Enable resilient execution with retries
            optimize: Enable performance optimization (caching, compression)
            async_mode: Enable asynchronous execution
            timeout_category: Override timeout category
            context: Additional execution context
            **kwargs: Additional context parameters
            
        Returns:
            ExecutionResult with success status, result, and comprehensive metadata
        """
        # Validate command
        if not command or not command.strip():
            return self._create_parameter_error("Command cannot be empty")
        
        logger.debug(f"Unified execution: {command} (resilient={resilient}, optimize={optimize}, async={async_mode})")
        
        try:
            # Create execution context
            exec_context = self._create_context(
                command=command,
                resilient=resilient,
                optimize=optimize,
                async_mode=async_mode,
                timeout_category=timeout_category,
                context=context or {},
                **kwargs
            )
            
            # Get appropriate strategy
            strategy = self._get_strategy(resilient, optimize, async_mode)
            
            # Execute with strategy
            result = strategy.execute(exec_context)
            
            # Add execution metadata
            result.metadata.update({
                "unified_execution": True,
                "strategy_type": strategy.__class__.__name__,
                "parameters": {
                    "resilient": resilient,
                    "optimize": optimize,
                    "async_mode": async_mode
                }
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Unified execution failed for '{command}': {e}")
            return self._create_execution_error(command, str(e))
    
    def execute_batch(
        self,
        commands: list[str],
        resilient: bool = True,
        optimize: bool = True,
        stop_on_error: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute multiple commands with unified execution system.
        
        Args:
            commands: List of commands to execute
            resilient: Enable resilient execution
            optimize: Enable optimization
            stop_on_error: Stop on first error
            **kwargs: Additional execution parameters
            
        Returns:
            Dictionary with batch execution results and summary
        """
        if not commands:
            return {
                "success": False,
                "error": "No commands provided",
                "results": []
            }
        
        logger.debug(f"Batch execution: {len(commands)} commands")
        
        results = []
        successful_commands = 0
        failed_commands = 0
        total_execution_time = 0.0
        
        for i, command in enumerate(commands):
            if not command.strip():
                # Skip empty commands
                results.append({
                    "command": command,
                    "index": i,
                    "success": False,
                    "error": "Empty command",
                    "skipped": True
                })
                continue
            
            # Execute command
            result = self.execute(
                command=command,
                resilient=resilient,
                optimize=optimize,
                **kwargs
            )
            
            # Convert to batch result format
            batch_result = {
                "command": command,
                "index": i,
                "success": result.success,
                "execution_time": result.execution_time,
                "execution_mode": result.execution_mode.value,
                "timeout_category": result.timeout_category
            }
            
            if result.success:
                batch_result.update({
                    "result": result.result,
                    "cached": result.cached,
                    "compressed": result.compressed,
                    "retries_used": result.retries_attempted
                })
                successful_commands += 1
            else:
                batch_result.update({
                    "error": result.error,
                    "timed_out": result.timed_out,
                    "retries_used": result.retries_attempted
                })
                failed_commands += 1
                
                if stop_on_error:
                    # Include the failing result, then stop
                    results.append(batch_result)
                    logger.warning(f"Stopping batch execution at command {i+1} due to error")
                    total_execution_time += result.execution_time
                    break

            results.append(batch_result)
            total_execution_time += result.execution_time
        
        # Calculate summary
        summary = {
            "total_commands": len(commands),
            "successful_commands": successful_commands,
            "failed_commands": failed_commands,
            "execution_stopped": stop_on_error and failed_commands > 0,
            "total_execution_time": total_execution_time,
            "average_execution_time": total_execution_time / len(commands) if commands else 0,
            "success_rate": successful_commands / len(commands) if commands else 0
        }
        
        return {
            "success": failed_commands == 0,
            "results": results,
            "summary": summary,
            "unified_batch_execution": True
        }
    
    def get_execution_statistics(self) -> Dict[str, Any]:
        """
        Get execution statistics and performance metrics.
        
        Returns:
            Dictionary with execution statistics
        """
        # This could be enhanced with actual statistics tracking
        return {
            "unified_executor": True,
            "cached_strategies": len(self._strategy_cache),
            "timeout_resolver": {
                "cache_size": len(self.timeout_resolver._category_cache)
            }
        }
    
    def _create_context(
        self,
        command: str,
        resilient: bool,
        optimize: bool,
        async_mode: bool,
        timeout_category: str,
        context: Dict[str, Any],
        **kwargs
    ) -> ExecutionContext:
        """Create execution context from parameters."""
        return create_execution_context(
            command=command,
            resilient=resilient,
            optimize=optimize,
            async_mode=async_mode,
            timeout_category=timeout_category,
            metadata=context,
            **kwargs
        )
    
    def _get_strategy(
        self,
        resilient: bool,
        optimize: bool,
        async_mode: bool
    ) -> ExecutionStrategy:
        """Get or create execution strategy based on parameters."""
        # Create cache key
        cache_key = f"r{resilient}_o{optimize}_a{async_mode}"
        
        # Check cache first
        if cache_key in self._strategy_cache:
            return self._strategy_cache[cache_key]
        
        # Create new strategy
        strategy = create_strategy(
            resilient=resilient,
            optimize=optimize,
            async_mode=async_mode
        )
        
        # Cache it
        self._strategy_cache[cache_key] = strategy
        
        return strategy
    
    def _create_parameter_error(self, message: str) -> ExecutionResult:
        """Create a parameter validation error result."""
        from .result import create_failure_result, ExecutionMode
        
        return create_failure_result(
            error=f"Parameter error: {message}",
            execution_mode=ExecutionMode.DIRECT,
            metadata={"error_type": "parameter_validation"}
        )
    
    def _create_execution_error(self, command: str, error: str) -> ExecutionResult:
        """Create an execution error result."""
        from .result import create_failure_result, ExecutionMode
        
        return create_failure_result(
            error=f"Execution error: {error}",
            execution_mode=ExecutionMode.DIRECT,
            metadata={
                "error_type": "execution_error",
                "original_command": command
            }
        )
    
    def clear_caches(self):
        """Clear all caches in the execution system."""
        self._strategy_cache.clear()
        self.timeout_resolver.clear_cache()
        logger.info("Unified executor caches cleared")

# Convenience functions for backward compatibility
def execute_command_unified(
    command: str,
    resilient: bool = True,
    optimize: bool = True,
    async_mode: bool = False,
    **kwargs
) -> ExecutionResult:
    """
    Convenience function for unified command execution.
    
    This provides backward compatibility for existing code.
    """
    from . import get_executor
    executor = get_executor()
    return executor.execute(
        command=command,
        resilient=resilient,
        optimize=optimize,
        async_mode=async_mode,
        **kwargs
    )

# Use execute_command for all execution needs
# Use core.execution.execute_command instead 
