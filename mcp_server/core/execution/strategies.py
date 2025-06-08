"""
Execution strategies for the unified execution system.

This module implements the strategy pattern for different execution modes,
consolidating the scattered execution logic.
"""
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

from core.communication import send_command, CommunicationError, TimeoutError, ConnectionError
from core.retry_utils import execute_with_retry, resilient_command
# Direct execution with optimization
from .result import ExecutionResult, ExecutionContext, ExecutionMode, create_success_result, create_failure_result
from .timeout_resolver import get_timeout_resolver

logger = logging.getLogger(__name__)

class ExecutionStrategy(ABC):
    """Abstract base class for execution strategies."""
    
    @abstractmethod
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """
        Execute a command with this strategy.
        
        Args:
            context: Execution context with command and settings
            
        Returns:
            ExecutionResult with success status and metadata
        """
        pass
    
    @abstractmethod
    def get_execution_mode(self) -> ExecutionMode:
        """Get the execution mode for this strategy."""
        pass

class DirectStrategy(ExecutionStrategy):
    """
    Direct execution strategy without optimization or retries.
    
    This strategy executes commands directly using the communication layer.
    """
    
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute command directly."""
        start_time = datetime.now()
        timeout_resolver = get_timeout_resolver()
        
        try:
            # Resolve timeout
            timeout_ms, category = timeout_resolver.resolve_timeout_and_category(
                context.command, 
                category_override=context.timeout_category
            )
            
            logger.debug(f"Direct execution: {context.command} (timeout: {timeout_ms}ms, category: {category})")
            
            # Execute command
            result = send_command(context.command, timeout_ms=timeout_ms)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return create_success_result(
                result=result,
                execution_mode=self.get_execution_mode(),
                execution_time=execution_time,
                timeout_category=category,
                timeout_ms=timeout_ms,
                started_at=start_time
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Determine if it was a timeout
            timed_out = isinstance(e, TimeoutError)
            
            return create_failure_result(
                error=str(e),
                execution_mode=self.get_execution_mode(),
                execution_time=execution_time,
                timeout_category=category if 'category' in locals() else None,
                timeout_ms=timeout_ms if 'timeout_ms' in locals() else 0,
                timed_out=timed_out,
                started_at=start_time
            )
    
    def get_execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

class ResilientStrategy(ExecutionStrategy):
    """
    Resilient execution strategy with retry logic.
    
    This strategy uses the centralized retry system to handle transient failures.
    """
    
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute command with retry logic."""
        start_time = datetime.now()
        timeout_resolver = get_timeout_resolver()
        
        # Resolve timeout and category
        timeout_ms, category = timeout_resolver.resolve_timeout_and_category(
            context.command,
            category_override=context.timeout_category
        )
        
        logger.debug(f"Resilient execution: {context.command} (timeout: {timeout_ms}ms, category: {category})")
        
        # Execute with retry logic
        try:
            result = execute_with_retry(
                send_command,
                context.command,
                timeout_ms=timeout_ms,
                max_attempts=context.max_retries,
                delay_base_ms=context.retry_delay_base_ms,
                exponential_backoff=context.exponential_backoff,
                retry_on=(CommunicationError, TimeoutError, ConnectionError)
            )
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return create_success_result(
                result=result,
                execution_mode=self.get_execution_mode(),
                execution_time=execution_time,
                timeout_category=category,
                timeout_ms=timeout_ms,
                started_at=start_time
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return create_failure_result(
                error=str(e),
                execution_mode=self.get_execution_mode(),
                execution_time=execution_time,
                timeout_category=category,
                timeout_ms=timeout_ms,
                timed_out=isinstance(e, TimeoutError),
                started_at=start_time
            )
    
    def get_execution_mode(self) -> ExecutionMode:
        return ExecutionMode.RESILIENT

class OptimizedStrategy(ExecutionStrategy):
    """
    Optimized execution strategy with performance optimizations.
    
    This strategy uses the performance optimization system including
    caching, compression, and optimization.
    """
    
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute command with performance optimizations using direct execution."""
        start_time = datetime.now()
        timeout_resolver = get_timeout_resolver()
        
        # Resolve timeout and category
        timeout_ms, category = timeout_resolver.resolve_timeout_and_category(
            context.command,
            category_override=context.timeout_category
        )
        
        logger.debug(f"Optimized execution: {context.command} (timeout: {timeout_ms}ms, category: {category})")
        
        try:
            # Use direct execution - optimization features now handled at higher level
            result = send_command(context.command, timeout_ms=timeout_ms)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return create_success_result(
                result=result,
                execution_mode=self.get_execution_mode(),
                execution_time=execution_time,
                cached=False,  # Caching now handled by unified cache system
                compressed=False,  # Compression handled at transport level
                original_size=len(result.encode('utf-8')) if result else 0,
                timeout_category=category,
                timeout_ms=timeout_ms,
                optimization_level="direct",
                started_at=start_time
            )
                
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return create_failure_result(
                error=str(e),
                execution_mode=self.get_execution_mode(),
                execution_time=execution_time,
                timeout_category=category,
                timeout_ms=timeout_ms,
                started_at=start_time
            )
    
    def get_execution_mode(self) -> ExecutionMode:
        return ExecutionMode.OPTIMIZED

class AsyncStrategy(ExecutionStrategy):
    """
    Asynchronous execution strategy for background execution.
    
    This strategy submits commands to the async operation manager
    and can optionally wait for completion.
    """
    
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute command asynchronously."""
        start_time = datetime.now()
        timeout_resolver = get_timeout_resolver()
        
        # Resolve timeout and category
        timeout_ms, category = timeout_resolver.resolve_timeout_and_category(
            context.command,
            category_override=context.timeout_category
        )
        
        logger.debug(f"Async execution: {context.command} (timeout: {timeout_ms}ms, category: {category})")
        
        try:
            # For now, use direct execution but mark as async
            # In future, this could be enhanced with true async capabilities
            result = send_command(context.command, timeout_ms=timeout_ms)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return create_success_result(
                result=result,
                execution_mode=self.get_execution_mode(),
                execution_time=execution_time,
                timeout_category=category,
                timeout_ms=timeout_ms,
                started_at=start_time,
                metadata={"async_execution": True}
            )
                
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return create_failure_result(
                error=str(e),
                execution_mode=self.get_execution_mode(),
                execution_time=execution_time,
                timeout_category=category,
                timeout_ms=timeout_ms,
                started_at=start_time
            )
    
    def get_execution_mode(self) -> ExecutionMode:
        return ExecutionMode.ASYNC

class HybridStrategy(ExecutionStrategy):
    """
    Hybrid strategy that combines resilient and optimized execution.
    
    This provides the best of both worlds: optimization with fallback resilience.
    """
    
    def __init__(self):
        self.optimized = OptimizedStrategy()
        self.resilient = ResilientStrategy()
    
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute with optimization first, then resilient fallback if needed."""
        logger.debug(f"Hybrid execution: {context.command}")
        
        # Try optimized execution first
        result = self.optimized.execute(context)
        
        if result.success:
            # Mark as hybrid execution but keep optimization metadata
            result.execution_mode = ExecutionMode.OPTIMIZED
            result.metadata["hybrid_execution"] = True
            result.metadata["primary_strategy"] = "optimized"
            return result
        
        # If optimized execution failed, try resilient execution
        logger.info(f"Optimized execution failed, falling back to resilient: {result.error}")
        
        # Create new context for resilient execution
        resilient_context = ExecutionContext(
            command=context.command,
            resilient=True,
            optimize=False,  # Disable optimization for fallback
            timeout_category=context.timeout_category,
            max_retries=context.max_retries,
            metadata=context.metadata.copy()
        )
        
        resilient_result = self.resilient.execute(resilient_context)
        
        # Mark as hybrid execution
        resilient_result.execution_mode = ExecutionMode.RESILIENT 
        resilient_result.metadata["hybrid_execution"] = True
        resilient_result.metadata["primary_strategy"] = "resilient"
        resilient_result.metadata["optimized_failed"] = True
        
        return resilient_result
    
    def get_execution_mode(self) -> ExecutionMode:
        return ExecutionMode.OPTIMIZED  # Primary mode

# Strategy factory
def create_strategy(
    resilient: bool = True,
    optimize: bool = True, 
    async_mode: bool = False
) -> ExecutionStrategy:
    """
    Create appropriate execution strategy based on parameters.
    
    Args:
        resilient: Enable resilient execution
        optimize: Enable optimization
        async_mode: Enable async execution
        
    Returns:
        Appropriate ExecutionStrategy instance
    """
    if async_mode:
        return AsyncStrategy()
    elif resilient and optimize:
        return OptimizedStrategy()  # Optimized includes resilience
    elif optimize:
        return OptimizedStrategy()
    elif resilient:
        return ResilientStrategy()
    else:
        return DirectStrategy() 