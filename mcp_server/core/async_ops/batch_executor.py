"""
Specialized batch command execution for WinDbg.

This module provides the BatchCommandExecutor class that handles
specialized batch operations like diagnostic sequences and performance analysis.
"""
import logging
from typing import Dict, Any, List
from datetime import datetime

from .task_manager import AsyncOperationManager, TaskStatus

logger = logging.getLogger(__name__)

class BatchCommandExecutor:
    """Specialized executor for batch command operations."""
    
    def __init__(self, async_manager: AsyncOperationManager):
        self.async_manager = async_manager
    
    def execute_diagnostic_sequence(self) -> Dict[str, Any]:
        """Execute a comprehensive diagnostic command sequence."""
        diagnostic_commands = [
            "version",
            ".effmach", 
            "!pcr",
            "lm",
            "!process -1 0",
            "k",
            "r"
        ]
        
        logger.info("Starting diagnostic sequence")
        results = self.async_manager.execute_parallel_commands(
            diagnostic_commands,
            max_parallel=3
        )
        
        # Process results into a structured report
        report = {
            "diagnostic_time": datetime.now().isoformat(),
            "commands_executed": len(diagnostic_commands),
            "successful_commands": sum(1 for task in results.values() if task.status == TaskStatus.COMPLETED),
            "results": {}
        }
        
        for command, task in results.items():
            report["results"][command] = {
                "status": task.status.value,
                "execution_time": (task.completed_at - task.started_at).total_seconds() if task.started_at and task.completed_at else 0,
                "result_preview": task.result[:200] + "..." if task.result and len(task.result) > 200 else task.result,
                "error": task.error
            }
        
        return report
    
    def execute_performance_analysis(self) -> Dict[str, Any]:
        """Execute commands for performance analysis."""
        performance_commands = [
            "!analyze -v",
            "!process 0 0",
            "!handle 0 f", 
            "!vm",
            "!poolused"
        ]
        
        logger.info("Starting performance analysis")
        results = self.async_manager.execute_parallel_commands(
            performance_commands,
            max_parallel=2  # These commands can be resource intensive
        )
        
        return self._format_analysis_results(results, "performance")
    
    def execute_crash_analysis(self) -> Dict[str, Any]:
        """Execute commands for crash analysis."""
        crash_commands = [
            "!analyze -v",
            ".bugcheck",
            "k",
            "!thread",
            "!process",
            "lm"
        ]
        
        logger.info("Starting crash analysis")
        results = self.async_manager.execute_parallel_commands(
            crash_commands,
            max_parallel=2
        )
        
        return self._format_analysis_results(results, "crash")
    
    def execute_memory_analysis(self) -> Dict[str, Any]:
        """Execute commands for memory analysis."""
        memory_commands = [
            "!vm",
            "!poolused",
            "!heap -s",
            "!address",
            "!pte",
            "!pfn"
        ]
        
        logger.info("Starting memory analysis")
        results = self.async_manager.execute_parallel_commands(
            memory_commands,
            max_parallel=2
        )
        
        return self._format_analysis_results(results, "memory")
    
    def execute_system_info_batch(self) -> Dict[str, Any]:
        """Execute system information gathering commands."""
        system_commands = [
            "version",
            ".effmach",
            "!cpuinfo",
            "!sysinfo",
            "lm",
            "!drivers",
            "!object"
        ]
        
        logger.info("Starting system information gathering")
        results = self.async_manager.execute_parallel_commands(
            system_commands,
            max_parallel=3
        )
        
        return self._format_analysis_results(results, "system_info")
    
    def _format_analysis_results(self, results: Dict[str, any], analysis_type: str) -> Dict[str, Any]:
        """Format analysis results into a structured report."""
        return {
            "analysis_type": analysis_type,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_commands": len(results),
                "successful": sum(1 for task in results.values() if task.status == TaskStatus.COMPLETED),
                "failed": sum(1 for task in results.values() if task.status == TaskStatus.FAILED),
                "total_execution_time": sum(
                    (task.completed_at - task.started_at).total_seconds()
                    for task in results.values() 
                    if task.started_at and task.completed_at
                )
            },
            "results": {
                command: {
                    "status": task.status.value,
                    "success": task.status == TaskStatus.COMPLETED,
                    "execution_time": (task.completed_at - task.started_at).total_seconds() if task.started_at and task.completed_at else 0,
                    "data_size": len(task.result) if task.result else 0,
                    "error": task.error,
                    "result_preview": task.result[:500] + "..." if task.result and len(task.result) > 500 else task.result
                }
                for command, task in results.items()
            },
            "recommendations": self._get_analysis_recommendations(results, analysis_type)
        }
    
    def _get_analysis_recommendations(self, results: Dict[str, any], analysis_type: str) -> List[str]:
        """Get recommendations based on analysis results."""
        recommendations = []
        
        failed_count = sum(1 for task in results.values() if task.status == TaskStatus.FAILED)
        success_rate = (len(results) - failed_count) / len(results) if results else 0
        
        if success_rate < 0.5:
            recommendations.append("⚠️ High failure rate - check WinDbg connection and VM state")
        
        if analysis_type == "crash":
            if any("!analyze" in cmd for cmd in results.keys()):
                recommendations.append("🔍 Review !analyze output for crash cause")
                recommendations.append("📊 Check call stack (k command) for crash context")
        elif analysis_type == "performance":
            recommendations.append("📈 Compare current values with baseline performance")
            recommendations.append("🎯 Focus on high resource usage areas")
        elif analysis_type == "memory":
            recommendations.append("💾 Check for memory leaks in pool usage")
            recommendations.append("🔧 Analyze heap corruption if present")
        
        if not recommendations:
            recommendations.append("✅ Analysis completed successfully")
        
        return recommendations 