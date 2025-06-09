"""
Core functionality for WinDbg MCP Extension.

This module provides the core components for communication, validation,
context management, error handling, parameter hints, connection
resilience, session recovery, performance optimization, and async operations.
"""

from .communication import (
    send_command,
    send_handler_command,
    test_connection,
    test_target_connection,
    diagnose_connection_issues,
    CommunicationError,
    TimeoutError,
    ConnectionError,
    NetworkDebuggingError
)

from .unified_cache import (
    start_startup_cache,
    stop_startup_cache,
    cache_command_result,
    get_cached_command_result,
    cache_session_snapshot,
    get_cached_session_snapshot,
    clear_session_cache,
    get_cache_stats,
    unified_cache
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

from .performance import (
    stream_large_command,
    get_performance_report,
    set_optimization_level,
    clear_performance_caches,
    performance_optimizer,
    PerformanceOptimizer,
    OptimizationLevel,
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
    "send_handler_command",
    "test_connection",
    "test_target_connection", 
    "diagnose_connection_issues",
    "CommunicationError",
    "TimeoutError",
    "ConnectionError",
    "NetworkDebuggingError",
    
    # Unified Cache
    "start_startup_cache",
    "stop_startup_cache",
    "cache_command_result",
    "get_cached_command_result", 
    "cache_session_snapshot",
    "get_cached_session_snapshot",
    "clear_session_cache",
    "get_cache_stats",
    "unified_cache",
    
    # Validation
    "validate_command",
    "is_safe_for_automation",
    
    # Context management
    "get_context_manager",
    "save_context",
    "restore_context",
    "ContextManager",
    
    # Error handling
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
    
    # Session recovery
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
    
    # Performance optimization
    "stream_large_command", 
    "get_performance_report",
    "set_optimization_level",
    "clear_performance_caches",
    "performance_optimizer",
    "PerformanceOptimizer",
    "OptimizationLevel",
    "DataCompressor",
    "StreamingHandler",
    "CommandOptimizer",
    "PerformanceMetrics",
    "DataSize",
    
    # Async operations
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