"""
Asynchronous task management for WinDbg commands.

This module provides the core AsyncOperationManager class that handles
task submission, execution, tracking, and result management.
"""
import logging
import time
import threading
import queue
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future

from core.execution import execute_command

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """Status of async tasks."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    """Priority levels for async tasks."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class AsyncTask:
    """Represents an async task."""
    task_id: str
    command: str
    status: TaskStatus
    priority: TaskPriority
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    timeout_category: str = "normal"
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class AsyncOperationManager:
    """Manages asynchronous operations for WinDbg commands."""
    
    def __init__(self, max_workers: int = 5, max_concurrent: int = 3):
        self.max_workers = max_workers
        self.max_concurrent = max_concurrent
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="AsyncWinDbg"
        )
        
        # Task management
        self.tasks: Dict[str, AsyncTask] = {}
        self.task_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.running_tasks: Dict[str, Future] = {}
        self._task_counter = 0
        self._lock = threading.Lock()
        
        # Performance tracking
        self.stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "average_execution_time": 0.0,
            "concurrent_peak": 0
        }
        
        # Task processor
        self._processor_running = False
    
    def submit_command(
        self,
        command: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout_category: str = "normal",
        callback: Optional[Callable[[AsyncTask], None]] = None
    ) -> str:
        """
        Submit a command for asynchronous execution.
        
        Args:
            command: WinDbg command to execute
            priority: Task priority
            timeout_category: Timeout category for the command
            callback: Optional callback function when task completes
            
        Returns:
            Task ID for tracking
        """
        with self._lock:
            self._task_counter += 1
            task_id = f"task_{self._task_counter}_{int(time.time())}"
        
        task = AsyncTask(
            task_id=task_id,
            command=command,
            status=TaskStatus.PENDING,
            priority=priority,
            created_at=datetime.now(),
            timeout_category=timeout_category,
            metadata={"callback": callback} if callback else {}
        )
        
        with self._lock:
            self.tasks[task_id] = task
            self.stats["total_tasks"] += 1
        
        # Add to priority queue (lower number = higher priority)
        priority_value = 5 - priority.value  # Invert so higher enum value = higher priority
        self.task_queue.put((priority_value, time.time(), task_id))
        
        logger.debug(f"Submitted async task {task_id}: {command}")
        
        # Start processing if not already running
        self._start_task_processor()
        
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[AsyncTask]:
        """Get the status of a specific task."""
        with self._lock:
            return self.tasks.get(task_id)
    
    def get_task_result(self, task_id: str, timeout: float = None) -> Optional[str]:
        """
        Get the result of a task, optionally waiting for completion.
        
        Args:
            task_id: Task identifier
            timeout: Maximum time to wait in seconds
            
        Returns:
            Task result or None if not completed/failed
        """
        start_time = time.time()
        
        while True:
            with self._lock:
                task = self.tasks.get(task_id)
            
            if not task:
                return None
            
            if task.status == TaskStatus.COMPLETED:
                return task.result
            elif task.status in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
                return None
            
            if timeout and (time.time() - start_time) > timeout:
                return None
            
            time.sleep(0.1)  # Small delay before checking again
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or running task."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                return True
            elif task.status == TaskStatus.RUNNING:
                # Try to cancel the running future
                future = self.running_tasks.get(task_id)
                if future and future.cancel():
                    task.status = TaskStatus.CANCELLED
                    task.completed_at = datetime.now()
                    return True
        
        return False
    
    def execute_parallel_commands(
        self,
        commands: List[str],
        max_parallel: int = None
    ) -> Dict[str, AsyncTask]:
        """
        Execute multiple commands in parallel.
        
        Args:
            commands: List of commands to execute
            max_parallel: Maximum parallel executions (default: max_concurrent)
            
        Returns:
            Dictionary mapping commands to their task results
        """
        max_parallel = max_parallel or self.max_concurrent
        
        # Submit all commands
        task_ids = []
        for command in commands:
            task_id = self.submit_command(command, TaskPriority.HIGH)
            task_ids.append(task_id)
        
        # Wait for all to complete
        results = {}
        timeout = 120.0  # 2 minutes max wait
        start_time = time.time()
        
        while task_ids and (time.time() - start_time) < timeout:
            completed_ids = []
            
            for task_id in task_ids:
                task = self.get_task_status(task_id)
                if task and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    results[task.command] = task
                    completed_ids.append(task_id)
            
            for task_id in completed_ids:
                task_ids.remove(task_id)
            
            if task_ids:
                time.sleep(0.2)
        
        # Cancel any remaining tasks
        for task_id in task_ids:
            self.cancel_task(task_id)
            task = self.get_task_status(task_id)
            if task:
                results[task.command] = task
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get async operation statistics."""
        with self._lock:
            running_count = len(self.running_tasks)
            pending_count = sum(1 for task in self.tasks.values() if task.status == TaskStatus.PENDING)
            
            stats = self.stats.copy()
            stats.update({
                "running_tasks": running_count,
                "pending_tasks": pending_count,
                "total_managed_tasks": len(self.tasks),
                "success_rate": stats["completed_tasks"] / max(stats["total_tasks"], 1),
                "failure_rate": stats["failed_tasks"] / max(stats["total_tasks"], 1)
            })
        
        return stats
    
    def _start_task_processor(self):
        """Start the task processor if not already running."""
        if not self._processor_running:
            self._processor_running = True
            threading.Thread(
                target=self._task_processor_loop,
                daemon=True,
                name="TaskProcessor"
            ).start()
    
    def _task_processor_loop(self):
        """Main task processing loop."""
        while True:
            try:
                # Check if we can start more tasks
                with self._lock:
                    current_running = len(self.running_tasks)
                
                if current_running >= self.max_concurrent:
                    time.sleep(0.1)
                    continue
                
                # Get next task from queue
                try:
                    priority, submit_time, task_id = self.task_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Check if task still exists and is pending
                with self._lock:
                    task = self.tasks.get(task_id)
                    if not task or task.status != TaskStatus.PENDING:
                        continue
                
                # Start the task
                self._execute_task(task)
                
            except Exception as e:
                logger.error(f"Error in task processor loop: {e}")
                time.sleep(1.0)
    
    def _execute_task(self, task: AsyncTask):
        """Execute a single task."""
        with self._lock:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            
            # Update peak concurrent tasks
            running_count = len(self.running_tasks) + 1
            if running_count > self.stats["concurrent_peak"]:
                self.stats["concurrent_peak"] = running_count
        
        # Submit to thread pool
        future = self.executor.submit(self._run_command, task)
        
        with self._lock:
            self.running_tasks[task.task_id] = future
        
        # Add completion callback
        future.add_done_callback(lambda f: self._task_completed(task.task_id, f))
    
    def _run_command(self, task: AsyncTask) -> Tuple[bool, str, Dict[str, Any]]:
        """Run the actual command for a task."""
        try:
            # Use unified execution system
            result = execute_command(
                command=task.command,
                resilient=True,
                optimize=True,
                timeout_category=task.timeout_category
            )
            
            if result.success:
                metadata = {
                    "cached": result.cached,
                    "response_time": result.execution_time,
                    "retries_attempted": result.retries_attempted,
                    "timeout_ms": result.timeout_ms,
                    "execution_mode": result.execution_mode.value
                }
                return True, result.result, metadata
            else:
                metadata = {
                    "error": True,
                    "response_time": result.execution_time,
                    "retries_attempted": result.retries_attempted,
                    "timeout_ms": result.timeout_ms,
                    "timed_out": result.timed_out
                }
                return False, result.error, metadata
        except Exception as e:
            logger.error(f"Error executing task {task.task_id}: {e}")
            return False, str(e), {"error": "execution_failed"}
    
    def _task_completed(self, task_id: str, future: Future):
        """Handle task completion."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            
            # Remove from running tasks
            self.running_tasks.pop(task_id, None)
            
            # Update task with results
            task.completed_at = datetime.now()
            
            try:
                success, result, metadata = future.result()
                if success:
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.metadata.update(metadata)
                    self.stats["completed_tasks"] += 1
                else:
                    task.status = TaskStatus.FAILED
                    task.error = result
                    task.metadata.update(metadata)
                    self.stats["failed_tasks"] += 1
                    
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                self.stats["failed_tasks"] += 1
            
            # Update average execution time
            execution_time = (task.completed_at - task.started_at).total_seconds()
            if self.stats["average_execution_time"] == 0:
                self.stats["average_execution_time"] = execution_time
            else:
                # Exponential moving average
                alpha = 0.1
                self.stats["average_execution_time"] = (
                    alpha * execution_time + 
                    (1 - alpha) * self.stats["average_execution_time"]
                )
            
            # Call callback if provided
            callback = task.metadata.get("callback")
            if callback and callable(callback):
                try:
                    callback(task)
                except Exception as e:
                    logger.error(f"Error in task callback: {e}") 