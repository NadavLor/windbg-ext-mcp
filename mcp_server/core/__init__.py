"""
Core functionality for WinDbg MCP Extension.

This module provides the core components for communication, validation,
context management, enhanced error handling, parameter hints, connection
resilience, session recovery, performance optimization, and async operations.
"""

from .communication import (
    send_command,
    test_connection,
    CommunicationError,
    TimeoutError,
    ConnectionError
)

from .validation import (
    validate_command,
    is_safe_for_automation
)

from .context import (
    get_context_manager,
    save_context,
    restore_context,
    ContextManager
)

from .error_handler import (
    enhance_error,
    error_enhancer,
    EnhancedError,
    ErrorEnhancer,
    DebugContext,
    ErrorCategory
)

from .hints import (
    get_parameter_help,
    validate_tool_parameters,
    parameter_hints,
    ParameterHints,
    ParameterInfo,
    ActionInfo,
    ToolInfo
)

# Phase 2B: Connection Resilience and Session Recovery
from .connection_resilience import (
    execute_resilient_command,
    get_connection_health,
    set_network_debugging_mode,
    start_connection_monitoring,
    stop_connection_monitoring,
    connection_resilience,
    ConnectionResilience,
    ConnectionState,
    VMState,
    ConnectionMetrics,
    RetryConfig
)

from .session_recovery import (
    capture_current_session,
    check_session_health,
    recover_session,
    get_recovery_recommendations,
    save_current_session,
    load_previous_session,
    session_recovery,
    SessionRecovery,
    SessionState,
    RecoveryStrategy,
    SessionSnapshot,
    RecoveryContext
)

# Phase 2C: Performance Optimization and Async Operations
from .performance import (
    execute_optimized_command,
    stream_large_command,
    get_performance_report,
    set_optimization_level,
    clear_performance_caches,
    performance_optimizer,
    PerformanceOptimizer,
    OptimizationLevel,
    ResultCache,
    DataCompressor,
    StreamingHandler,
    CommandOptimizer,
    PerformanceMetrics,
    DataSize
)

from .async_ops import (
    submit_async_command,
    get_async_result,
    execute_parallel_commands,
    start_async_monitoring,
    stop_async_monitoring,
    get_async_stats,
    async_manager,
    batch_executor,
    AsyncOperationManager,
    BatchCommandExecutor,
    TaskStatus,
    TaskPriority,
    AsyncTask
)

__all__ = [
    # Communication
    "send_command",
    "test_connection", 
    "CommunicationError",
    "TimeoutError",
    "ConnectionError",
    
    # Validation
    "validate_command",
    "is_safe_for_automation",
    
    # Context management
    "get_context_manager",
    "save_context",
    "restore_context",
    "ContextManager",
    
    # Enhanced error handling
    "enhance_error",
    "error_enhancer",
    "EnhancedError",
    "ErrorEnhancer",
    "DebugContext",
    "ErrorCategory",
    
    # Parameter hints and validation
    "get_parameter_help",
    "validate_tool_parameters",
    "parameter_hints",
    "ParameterHints",
    "ParameterInfo",
    "ActionInfo",
    "ToolInfo",
    
    # Connection resilience (Phase 2B)
    "execute_resilient_command",
    "get_connection_health", 
    "set_network_debugging_mode",
    "start_connection_monitoring",
    "stop_connection_monitoring",
    "connection_resilience",
    "ConnectionResilience",
    "ConnectionState",
    "VMState",
    "ConnectionMetrics",
    "RetryConfig",
    
    # Session recovery (Phase 2B)
    "capture_current_session",
    "check_session_health",
    "recover_session",
    "get_recovery_recommendations",
    "save_current_session",
    "load_previous_session",
    "session_recovery",
    "SessionRecovery",
    "SessionState",
    "RecoveryStrategy",
    "SessionSnapshot",
    "RecoveryContext",
    
    # Performance optimization (Phase 2C)
    "execute_optimized_command",
    "stream_large_command", 
    "get_performance_report",
    "set_optimization_level",
    "clear_performance_caches",
    "performance_optimizer",
    "PerformanceOptimizer",
    "OptimizationLevel",
    "ResultCache",
    "DataCompressor",
    "StreamingHandler",
    "CommandOptimizer",
    "PerformanceMetrics",
    "DataSize",
    
    # Async operations (Phase 2C)
    "submit_async_command",
    "get_async_result",
    "execute_parallel_commands",
    "start_async_monitoring",
    "stop_async_monitoring",
    "get_async_stats",
    "async_manager",
    "batch_executor",
    "AsyncOperationManager",
    "BatchCommandExecutor",
    "TaskStatus",
    "TaskPriority",
    "AsyncTask"
] 