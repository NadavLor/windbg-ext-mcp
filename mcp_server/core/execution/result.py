"""
Execution result and context classes for unified execution system.
"""
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class ExecutionMode(Enum):
    """Execution mode enumeration."""
    DIRECT = "direct"
    RESILIENT = "resilient" 
    OPTIMIZED = "optimized"
    ASYNC = "async"

@dataclass
class ExecutionContext:
    """
    Context for command execution with settings and state.
    """
    # Core settings
    command: str
    resilient: bool = True
    optimize: bool = True
    async_mode: bool = False
    
    # Timeout settings
    timeout_category: Optional[str] = None
    timeout_ms: Optional[int] = None
    
    # Retry settings
    max_retries: int = 3
    retry_delay_base_ms: int = 1000
    exponential_backoff: bool = True
    
    # Optimization settings  
    force_fresh: bool = False
    enable_compression: bool = True
    enable_streaming: bool = True
    
    # Additional context
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary."""
        return {
            "command": self.command,
            "resilient": self.resilient,
            "optimize": self.optimize,
            "async_mode": self.async_mode,
            "timeout_category": self.timeout_category,
            "timeout_ms": self.timeout_ms,
            "max_retries": self.max_retries,
            "retry_delay_base_ms": self.retry_delay_base_ms,
            "exponential_backoff": self.exponential_backoff,
            "force_fresh": self.force_fresh,
            "enable_compression": self.enable_compression,
            "enable_streaming": self.enable_streaming,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }

@dataclass
class ExecutionResult:
    """
    Standardized execution result with comprehensive metadata.
    """
    # Core result
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    
    # Execution metadata
    execution_mode: ExecutionMode = ExecutionMode.DIRECT
    execution_time: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Resilience metadata
    retries_attempted: int = 0
    retry_delay_total: float = 0.0
    
    # Performance metadata
    cached: bool = False
    compressed: bool = False
    original_size: int = 0
    compressed_size: int = 0
    cache_hit: bool = False
    cache_ttl: int = 0
    
    # Timeout metadata
    timeout_category: Optional[str] = None
    timeout_ms: int = 0
    timed_out: bool = False
    
    # Optimization metadata
    optimization_level: str = "none"
    optimization_bypassed: bool = False
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization to set timestamps if not provided."""
        if self.completed_at and self.started_at:
            self.execution_time = (self.completed_at - self.started_at).total_seconds()
        elif self.execution_time == 0.0:
            # Set a default execution time if not provided
            self.execution_time = 0.0
    
    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio if compressed."""
        if self.compressed and self.original_size > 0:
            return self.compressed_size / self.original_size
        return 1.0
    
    @property 
    def bytes_saved(self) -> int:
        """Calculate bytes saved through compression."""
        if self.compressed:
            return max(0, self.original_size - self.compressed_size)
        return 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary format."""
        result_dict = {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "execution_mode": self.execution_mode.value,
            "execution_time": self.execution_time,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "retries_attempted": self.retries_attempted,
            "retry_delay_total": self.retry_delay_total,
            "cached": self.cached,
            "compressed": self.compressed,
            "original_size": self.original_size,
            "timeout_category": self.timeout_category,
            "timeout_ms": self.timeout_ms,
            "timed_out": self.timed_out,
            "optimization_level": self.optimization_level,
            "optimization_bypassed": self.optimization_bypassed,
            "metadata": self.metadata
        }
        
        # Add compression metrics if applicable
        if self.compressed:
            result_dict.update({
                "compressed_size": self.compressed_size,
                "compression_ratio": self.compression_ratio,
                "bytes_saved": self.bytes_saved
            })
            
        return result_dict
    
    def to_legacy_format(self) -> Dict[str, Any]:
        """
        Convert to legacy format for compatibility with existing tools.
        """
        if self.success:
            return {
                "success": True,
                "result": self.result,
                "execution_method": self.execution_mode.value,
                "performance_info": {
                    "cached": self.cached,
                    "response_time": self.execution_time,
                    "retries_used": self.retries_attempted,
                    "timeout_category": self.timeout_category,
                    "optimization_level": self.optimization_level
                },
                "resilience_info": {
                    "response_time": self.execution_time,
                    "retries_used": self.retries_attempted,
                    "timeout_category": self.timeout_category
                } if self.execution_mode == ExecutionMode.RESILIENT else None
            }
        else:
            return {
                "success": False,
                "error": self.error,
                "execution_method": self.execution_mode.value,
                "metadata": self.metadata
            }

def create_execution_context(
    command: str,
    resilient: bool = True,
    optimize: bool = True,
    async_mode: bool = False,
    timeout_category: str = None,
    **kwargs
) -> ExecutionContext:
    """
    Create an execution context with validated parameters.
    
    Args:
        command: WinDbg command to execute
        resilient: Enable resilient execution
        optimize: Enable performance optimization
        async_mode: Enable asynchronous execution
        timeout_category: Timeout category override
        **kwargs: Additional context parameters
        
    Returns:
        ExecutionContext instance
    """
    return ExecutionContext(
        command=command,
        resilient=resilient,
        optimize=optimize,
        async_mode=async_mode,
        timeout_category=timeout_category,
        **kwargs
    )

def create_success_result(
    result: str,
    execution_mode: ExecutionMode,
    execution_time: float = 0.0,
    **kwargs
) -> ExecutionResult:
    """
    Create a successful execution result.
    
    Args:
        result: Command output
        execution_mode: How the command was executed
        execution_time: Time taken for execution
        **kwargs: Additional result metadata
        
    Returns:
        ExecutionResult instance
    """
    return ExecutionResult(
        success=True,
        result=result,
        execution_mode=execution_mode,
        execution_time=execution_time,
        completed_at=datetime.now(),
        **kwargs
    )

def create_failure_result(
    error: str,
    execution_mode: ExecutionMode,
    execution_time: float = 0.0,
    **kwargs
) -> ExecutionResult:
    """
    Create a failed execution result.
    
    Args:
        error: Error message
        execution_mode: How the command was executed
        execution_time: Time taken before failure
        **kwargs: Additional result metadata
        
    Returns:
        ExecutionResult instance
    """
    return ExecutionResult(
        success=False,
        error=error,
        execution_mode=execution_mode,
        execution_time=execution_time,
        completed_at=datetime.now(),
        **kwargs
    ) 