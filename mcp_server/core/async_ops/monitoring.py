"""
Background monitoring for async operations.

This module provides the AsyncMonitor class that handles background
monitoring of task queues, performance metrics, and health checking.
"""
import logging
import time
import threading
from typing import Dict, Any, List
from datetime import datetime, timedelta

from .task_manager import AsyncOperationManager, TaskStatus

logger = logging.getLogger(__name__)

class AsyncMonitor:
    """Handles background monitoring of async operations."""
    
    def __init__(self, async_manager: AsyncOperationManager):
        self.async_manager = async_manager
        self._monitoring_enabled = False
        self._monitor_thread = None
        self._stats_history = []
        self._max_history_size = 100
    
    def start_monitoring(self):
        """Start background monitoring of task queue and performance."""
        if self._monitoring_enabled:
            return
        
        self._monitoring_enabled = True
        self._monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="AsyncMonitor"
        )
        self._monitor_thread.start()
        logger.info("Started async operations monitoring")
    
    def stop_monitoring(self):
        """Stop background monitoring."""
        self._monitoring_enabled = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        # Don't log during shutdown to avoid I/O errors with closed streams
        try:
            logger.info("Stopped async operations monitoring")
        except:
            pass  # Silently ignore if streams are closed
    
    def get_monitoring_report(self) -> Dict[str, Any]:
        """Get comprehensive monitoring report."""
        current_stats = self.async_manager.get_statistics()
        
        # Calculate trends if we have history
        trends = self._calculate_trends()
        
        # Health assessment
        health = self._assess_health(current_stats)
        
        return {
            "current_statistics": current_stats,
            "trends": trends,
            "health_assessment": health,
            "monitoring_status": "active" if self._monitoring_enabled else "inactive",
            "history_size": len(self._stats_history),
            "recommendations": self._get_monitoring_recommendations(current_stats, health)
        }
    
    def cleanup_completed_tasks(self, max_age_hours: int = 1):
        """Clean up old completed tasks."""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        with self.async_manager._lock:
            completed_tasks = [
                task_id for task_id, task in self.async_manager.tasks.items()
                if task.completed_at and task.completed_at < cutoff_time
                and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
            ]
            
            for task_id in completed_tasks:
                del self.async_manager.tasks[task_id]
        
        logger.debug(f"Cleaned up {len(completed_tasks)} old tasks")
        return len(completed_tasks)
    
    def _monitoring_loop(self):
        """Background monitoring loop."""
        while self._monitoring_enabled:
            try:
                # Collect current statistics
                stats = self.async_manager.get_statistics()
                stats["timestamp"] = datetime.now().isoformat()
                
                # Add to history
                self._stats_history.append(stats)
                if len(self._stats_history) > self._max_history_size:
                    self._stats_history.pop(0)
                
                # Clean up old tasks periodically
                if len(self._stats_history) % 10 == 0:  # Every 10th cycle
                    self.cleanup_completed_tasks()
                
                # Log statistics periodically
                if stats["total_tasks"] > 0:
                    logger.debug(f"Async stats: {stats['running_tasks']} running, "
                               f"{stats['pending_tasks']} pending, "
                               f"{stats['success_rate']:.2f} success rate")
                
                # Check for potential issues
                self._check_for_issues(stats)
                
                time.sleep(30.0)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(30.0)
    
    def _calculate_trends(self) -> Dict[str, Any]:
        """Calculate trends from historical data."""
        if len(self._stats_history) < 2:
            return {"available": False, "reason": "insufficient_data"}
        
        recent = self._stats_history[-5:]  # Last 5 data points
        older = self._stats_history[-10:-5] if len(self._stats_history) >= 10 else self._stats_history[:-5]
        
        if not older:
            return {"available": False, "reason": "insufficient_history"}
        
        # Calculate averages
        recent_avg = {
            "success_rate": sum(s["success_rate"] for s in recent) / len(recent),
            "avg_execution_time": sum(s["average_execution_time"] for s in recent) / len(recent),
            "running_tasks": sum(s["running_tasks"] for s in recent) / len(recent)
        }
        
        older_avg = {
            "success_rate": sum(s["success_rate"] for s in older) / len(older),
            "avg_execution_time": sum(s["average_execution_time"] for s in older) / len(older),
            "running_tasks": sum(s["running_tasks"] for s in older) / len(older)
        }
        
        return {
            "available": True,
            "success_rate_trend": recent_avg["success_rate"] - older_avg["success_rate"],
            "execution_time_trend": recent_avg["avg_execution_time"] - older_avg["avg_execution_time"],
            "load_trend": recent_avg["running_tasks"] - older_avg["running_tasks"],
            "interpretation": self._interpret_trends(recent_avg, older_avg)
        }
    
    def _assess_health(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Assess the health of async operations."""
        health = {
            "overall": "healthy",
            "issues": [],
            "warnings": []
        }
        
        # Check success rate
        if stats["success_rate"] < 0.5:
            health["issues"].append("Low success rate (< 50%)")
            health["overall"] = "unhealthy"
        elif stats["success_rate"] < 0.8:
            health["warnings"].append("Moderate success rate (< 80%)")
            if health["overall"] == "healthy":
                health["overall"] = "warning"
        
        # Check execution time
        if stats["average_execution_time"] > 10.0:
            health["warnings"].append("High average execution time (> 10s)")
            if health["overall"] == "healthy":
                health["overall"] = "warning"
        
        # Check queue buildup
        if stats["pending_tasks"] > 10:
            health["warnings"].append("High pending task count (> 10)")
            if health["overall"] == "healthy":
                health["overall"] = "warning"
        
        # Check for stuck tasks
        if stats["running_tasks"] == stats["concurrent_peak"] and stats["pending_tasks"] > 0:
            health["issues"].append("Possible task queue bottleneck")
            health["overall"] = "unhealthy"
        
        return health
    
    def _interpret_trends(self, recent: Dict[str, float], older: Dict[str, float]) -> List[str]:
        """Interpret trend data."""
        interpretations = []
        
        success_diff = recent["success_rate"] - older["success_rate"]
        if success_diff > 0.1:
            interpretations.append("📈 Success rate improving")
        elif success_diff < -0.1:
            interpretations.append("📉 Success rate declining")
        
        time_diff = recent["avg_execution_time"] - older["avg_execution_time"]
        if time_diff > 2.0:
            interpretations.append("⏳ Execution times increasing")
        elif time_diff < -2.0:
            interpretations.append("⚡ Execution times improving")
        
        load_diff = recent["running_tasks"] - older["running_tasks"]
        if load_diff > 1.0:
            interpretations.append("📊 Task load increasing")
        elif load_diff < -1.0:
            interpretations.append("📊 Task load decreasing")
        
        if not interpretations:
            interpretations.append("📊 Performance stable")
        
        return interpretations
    
    def _check_for_issues(self, stats: Dict[str, Any]):
        """Check for potential issues and log warnings."""
        # Check for high failure rate
        if stats["failure_rate"] > 0.3:
            logger.warning(f"High task failure rate: {stats['failure_rate']:.1%}")
        
        # Check for queue buildup
        if stats["pending_tasks"] > 20:
            logger.warning(f"High pending task count: {stats['pending_tasks']}")
        
        # Check for slow execution
        if stats["average_execution_time"] > 15.0:
            logger.warning(f"Slow average execution time: {stats['average_execution_time']:.1f}s")
    
    def _get_monitoring_recommendations(self, stats: Dict[str, Any], health: Dict[str, Any]) -> List[str]:
        """Get monitoring-based recommendations."""
        recommendations = []
        
        if health["overall"] == "unhealthy":
            recommendations.append("🚨 Review system health - multiple issues detected")
        
        if stats["failure_rate"] > 0.2:
            recommendations.append("🔧 Investigate command failures - check WinDbg connection")
        
        if stats["pending_tasks"] > 5:
            recommendations.append("⚡ Consider increasing max_concurrent for better throughput")
        
        if stats["average_execution_time"] > 8.0:
            recommendations.append("🌐 Check network latency to target VM")
        
        if stats["total_tasks"] > 100 and stats["success_rate"] > 0.9:
            recommendations.append("✅ Async operations performing well")
        
        if not recommendations:
            recommendations.append("📊 No specific recommendations at this time")
        
        return recommendations 