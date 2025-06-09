"""
Asynchronous operations package for WinDbg MCP Extension.

This package provides async and non-blocking operations for performance
in network debugging scenarios, including background command execution,
concurrent task management, and async health monitoring.

The package is organized into focused modules:
- task_manager.py: AsyncOperationManager and task management
- batch_executor.py: BatchCommandExecutor for specialized batch operations
- monitoring.py: Background monitoring and health checking
- utilities.py: Task utilities and helper functions
"""

# Import core classes and functions
from .task_manager import AsyncOperationManager, AsyncTask, TaskStatus, TaskPriority
from .batch_executor import BatchCommandExecutor
from .monitoring import AsyncMonitor
from .utilities import TaskUtilities

# Global instances for use across the application
async_manager = AsyncOperationManager()
batch_executor = BatchCommandExecutor(async_manager)
async_monitor = AsyncMonitor(async_manager)

# Convenience functions that delegate to the global instances
def submit_async_command(command: str, priority: TaskPriority = TaskPriority.NORMAL) -> str:
    """Submit a command for async execution."""
    return async_manager.submit_command(command, priority)

def get_async_result(task_id: str, timeout: float = None):
    """Get result of an async command."""
    return async_manager.get_task_result(task_id, timeout)

def execute_parallel_commands(commands: list):
    """Execute multiple commands in parallel."""
    return async_manager.execute_parallel_commands(commands)

def start_async_monitoring():
    """Start background async monitoring."""
    async_monitor.start_monitoring()

def stop_async_monitoring():
    """Stop background async monitoring."""
    async_monitor.stop_monitoring()

def get_async_stats():
    """Get async operation statistics."""
    return async_manager.get_statistics()

__all__ = [
    # Core classes
    "AsyncOperationManager",
    "AsyncTask", 
    "TaskStatus",
    "TaskPriority",
    "BatchCommandExecutor",
    "AsyncMonitor",
    "TaskUtilities",
    
    # Global instances
    "async_manager",
    "batch_executor",
    "async_monitor",
    
    # Convenience functions
    "submit_async_command",
    "get_async_result",
    "execute_parallel_commands",
    "start_async_monitoring",
    "stop_async_monitoring",
    "get_async_stats"
] 