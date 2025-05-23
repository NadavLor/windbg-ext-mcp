"""
Task utilities and helper functions for async operations.

This module provides utility functions for task management, 
insights generation, and async operation helpers.
"""
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

from .task_manager import AsyncTask, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)

class TaskUtilities:
    """Utility functions for async task management."""
    
    @staticmethod
    def filter_tasks_by_status(tasks: Dict[str, AsyncTask], status: TaskStatus) -> List[AsyncTask]:
        """Filter tasks by their status."""
        return [task for task in tasks.values() if task.status == status]
    
    @staticmethod
    def filter_tasks_by_timeframe(tasks: Dict[str, AsyncTask], hours: int) -> List[AsyncTask]:
        """Filter tasks created within the specified timeframe."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [task for task in tasks.values() if task.created_at >= cutoff_time]
    
    @staticmethod
    def get_task_execution_time(task: AsyncTask) -> float:
        """Get the execution time of a task in seconds."""
        if not task.started_at or not task.completed_at:
            return 0.0
        return (task.completed_at - task.started_at).total_seconds()
    
    @staticmethod
    def get_tasks_by_command_pattern(tasks: Dict[str, AsyncTask], pattern: str) -> List[AsyncTask]:
        """Get tasks that match a command pattern."""
        pattern_lower = pattern.lower()
        return [task for task in tasks.values() if pattern_lower in task.command.lower()]
    
    @staticmethod
    def calculate_task_metrics(tasks: List[AsyncTask]) -> Dict[str, Any]:
        """Calculate metrics for a list of tasks."""
        if not tasks:
            return {
                "count": 0,
                "success_rate": 0.0,
                "average_execution_time": 0.0,
                "total_execution_time": 0.0
            }
        
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        failed_tasks = [t for t in tasks if t.status == TaskStatus.FAILED]
        
        execution_times = [
            TaskUtilities.get_task_execution_time(task) 
            for task in tasks 
            if task.started_at and task.completed_at
        ]
        
        return {
            "count": len(tasks),
            "completed": len(completed_tasks),
            "failed": len(failed_tasks),
            "success_rate": len(completed_tasks) / len(tasks),
            "failure_rate": len(failed_tasks) / len(tasks),
            "average_execution_time": sum(execution_times) / len(execution_times) if execution_times else 0.0,
            "total_execution_time": sum(execution_times),
            "min_execution_time": min(execution_times) if execution_times else 0.0,
            "max_execution_time": max(execution_times) if execution_times else 0.0
        }
    
    @staticmethod
    def get_async_insights(tasks: Dict[str, AsyncTask], stats: Dict[str, Any]) -> Dict[str, Any]:
        """Generate insights about async operations."""
        insights = {
            "performance_insights": [],
            "command_insights": [],
            "timing_insights": [],
            "recommendations": []
        }
        
        # Performance insights
        if stats["success_rate"] > 0.95:
            insights["performance_insights"].append("🎯 Excellent success rate (>95%)")
        elif stats["success_rate"] < 0.8:
            insights["performance_insights"].append("⚠️ Success rate below optimal (<80%)")
        
        if stats["average_execution_time"] < 2.0:
            insights["performance_insights"].append("⚡ Fast average execution time (<2s)")
        elif stats["average_execution_time"] > 10.0:
            insights["performance_insights"].append("🐌 Slow average execution time (>10s)")
        
        # Command insights
        command_patterns = {}
        for task in tasks.values():
            cmd_type = TaskUtilities._categorize_command(task.command)
            if cmd_type not in command_patterns:
                command_patterns[cmd_type] = {"count": 0, "success": 0}
            command_patterns[cmd_type]["count"] += 1
            if task.status == TaskStatus.COMPLETED:
                command_patterns[cmd_type]["success"] += 1
        
        for cmd_type, data in command_patterns.items():
            success_rate = data["success"] / data["count"] if data["count"] > 0 else 0
            if data["count"] >= 5:  # Only report on patterns with enough data
                insights["command_insights"].append(
                    f"📊 {cmd_type}: {data['count']} executions, {success_rate:.1%} success rate"
                )
        
        # Timing insights
        recent_tasks = TaskUtilities.filter_tasks_by_timeframe(tasks, 1)  # Last hour
        if recent_tasks:
            recent_metrics = TaskUtilities.calculate_task_metrics(recent_tasks)
            insights["timing_insights"].append(
                f"📈 Last hour: {recent_metrics['count']} tasks, "
                f"{recent_metrics['average_execution_time']:.1f}s avg time"
            )
        
        # Recommendations
        if stats["pending_tasks"] > stats["running_tasks"] * 2:
            insights["recommendations"].append("Consider increasing max_concurrent workers")
        
        if stats["failure_rate"] > 0.2:
            insights["recommendations"].append("Investigate frequent command failures")
        
        if stats["average_execution_time"] > 8.0:
            insights["recommendations"].append("Check network connectivity to target system")
        
        return insights
    
    @staticmethod
    def _categorize_command(command: str) -> str:
        """Categorize a command by type."""
        command_lower = command.lower().strip()
        
        if any(cmd in command_lower for cmd in ["!analyze", "!crash", ".bugcheck"]):
            return "crash_analysis"
        elif any(cmd in command_lower for cmd in ["!process", "!thread", "!handle"]):
            return "process_analysis"
        elif any(cmd in command_lower for cmd in ["!vm", "!pool", "!heap", "!pte"]):
            return "memory_analysis"
        elif any(cmd in command_lower for cmd in ["k", "kb", "kv", "kp"]):
            return "stack_trace"
        elif any(cmd in command_lower for cmd in ["r", "rm", "rF"]):
            return "registers"
        elif any(cmd in command_lower for cmd in ["lm", "version", ".effmach"]):
            return "system_info"
        elif any(cmd in command_lower for cmd in ["g", "p", "t", "bp", "bc"]):
            return "execution_control"
        else:
            return "general"
    
    @staticmethod
    def format_task_summary(task: AsyncTask) -> str:
        """Format a concise summary of a task."""
        duration = ""
        if task.started_at and task.completed_at:
            duration = f" ({TaskUtilities.get_task_execution_time(task):.1f}s)"
        elif task.started_at:
            running_time = (datetime.now() - task.started_at).total_seconds()
            duration = f" (running {running_time:.1f}s)"
        
        status_icon = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "🔄",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.CANCELLED: "🚫"
        }.get(task.status, "❓")
        
        return f"{status_icon} {task.command[:50]}{'...' if len(task.command) > 50 else ''}{duration}"
    
    @staticmethod
    def get_performance_recommendations(stats: Dict[str, Any]) -> List[str]:
        """Get performance recommendations based on async statistics."""
        recommendations = []
        
        # Success rate recommendations
        if stats["success_rate"] < 0.7:
            recommendations.append("🔧 Poor success rate - check WinDbg connection stability")
        elif stats["success_rate"] < 0.9:
            recommendations.append("⚡ Moderate success rate - consider command validation")
        
        # Execution time recommendations
        if stats["average_execution_time"] > 15.0:
            recommendations.append("🌐 Very slow execution - verify network connectivity")
        elif stats["average_execution_time"] > 8.0:
            recommendations.append("🐌 Slow execution - check target VM performance")
        
        # Queue management recommendations
        if stats["pending_tasks"] > 15:
            recommendations.append("📊 High queue depth - consider increasing worker count")
        elif stats["running_tasks"] == 0 and stats["pending_tasks"] > 0:
            recommendations.append("🚨 Tasks pending but none running - check async manager")
        
        # Load balancing recommendations
        concurrent_utilization = stats["running_tasks"] / max(stats.get("concurrent_peak", 1), 1)
        if concurrent_utilization > 0.9 and stats["pending_tasks"] > 5:
            recommendations.append("⚡ High utilization - consider increasing max_concurrent")
        
        # Success recommendations
        if stats["success_rate"] > 0.95 and stats["average_execution_time"] < 3.0:
            recommendations.append("🚀 Excellent async performance!")
        
        return recommendations or ["📊 No specific recommendations"] 