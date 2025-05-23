"""
Performance and asynchronous execution tools for WinDbg MCP server.

This module contains tools for managing performance optimization and async command execution.
"""
import logging
import time
from typing import Dict, Any, List, Optional, Union
from fastmcp import FastMCP, Context

from core.performance import (
    execute_optimized_command, stream_large_command, get_performance_report,
    set_optimization_level, clear_performance_caches, OptimizationLevel
)
from core.async_ops import (
    submit_async_command, get_async_result, execute_parallel_commands,
    get_async_stats, async_manager, batch_executor, TaskPriority, TaskStatus
)
from core.connection_resilience import execute_resilient_command

from .tool_utilities import (
    categorize_command_timeout, get_performance_recommendations, 
    get_optimization_effects, summarize_benchmark, get_benchmark_recommendations,
    get_async_insights
)

logger = logging.getLogger(__name__)

def register_performance_tools(mcp: FastMCP):
    """Register all performance and async tools."""
    
    @mcp.tool()
    async def performance_manager(ctx: Context, action: str, level: str = "", command: str = "") -> Dict[str, Any]:
        """
        Manage performance optimization settings and monitor performance metrics.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "report", "set_level", "clear_cache", "stream", "benchmark"
            level: Optimization level - "none", "basic", "aggressive", "maximum"
            command: Command for specific actions like streaming or benchmarking
            
        Returns:
            Performance management results
        """
        logger.debug(f"Performance manager action: {action}")
        
        try:
            if action == "report":
                # Get comprehensive performance report
                perf_report = get_performance_report()
                async_stats = get_async_stats()
                
                return {
                    "performance_report": perf_report,
                    "async_statistics": async_stats,
                    "recommendations": get_performance_recommendations(perf_report, async_stats),
                    "tip": "Use performance_manager(action='set_level', level='aggressive') to optimize for network debugging"
                }
            
            elif action == "set_level":
                if not level:
                    return {
                        "error": "Optimization level required",
                        "available_levels": ["none", "basic", "aggressive", "maximum"],
                        "current_level": get_performance_report()["optimization_level"]
                    }
                
                try:
                    opt_level = OptimizationLevel(level)
                    old_level = get_performance_report()["optimization_level"]
                    set_optimization_level(opt_level)
                    
                    return {
                        "message": f"Optimization level changed from '{old_level}' to '{level}'",
                        "effects": get_optimization_effects(opt_level),
                        "tip": "Changes take effect immediately for new commands"
                    }
                except ValueError:
                    return {
                        "error": f"Invalid optimization level: {level}",
                        "available_levels": [lvl.value for lvl in OptimizationLevel]
                    }
            
            elif action == "clear_cache":
                # Clear performance caches
                clear_performance_caches()
                
                return {
                    "message": "Performance caches cleared",
                    "effect": "Next commands will execute fresh (no cache hits)",
                    "tip": "Use this if you need fresh results or after system state changes"
                }
            
            elif action == "stream":
                if not command:
                    return {
                        "error": "Command required for streaming",
                        "example": "performance_manager(action='stream', command='!process 0 0')",
                        "suitable_commands": ["!process 0 0", "!handle 0 f", "lm v", "!analyze -v"]
                    }
                
                # Stream large command output
                stream_results = []
                try:
                    for chunk in stream_large_command(command):
                        stream_results.append(chunk)
                        if chunk.get("type") == "complete":
                            break
                    
                    # Format streaming results
                    total_chunks = len([r for r in stream_results if r.get("type") == "chunk"])
                    final_result = next((r for r in stream_results if r.get("type") == "complete"), {})
                    
                    return {
                        "streaming_completed": True,
                        "command": command,
                        "total_chunks": total_chunks,
                        "total_size": final_result.get("total_size", 0),
                        "metadata": final_result.get("metadata", {}),
                        "stream_data": stream_results,
                        "tip": "Large results were streamed in chunks to optimize network transfer"
                    }
                    
                except Exception as e:
                    return {
                        "error": f"Streaming failed: {str(e)}",
                        "suggestion": "Try with a smaller command or use run_command for direct execution"
                    }
            
            elif action == "benchmark":
                # Run performance benchmark
                test_commands = [
                    "version",  # Quick command
                    "lm",       # Medium command  
                    "!process -1 0"  # Slow command
                ]
                
                if command:
                    test_commands = [command]
                
                benchmark_results = {}
                
                for test_cmd in test_commands:
                    # Test with and without optimization
                    results = {}
                    
                    # Optimized execution
                    start_time = time.time()
                    success, result, metadata = execute_optimized_command(test_cmd, force_fresh=True)
                    optimized_time = time.time() - start_time
                    
                    results["optimized"] = {
                        "success": success,
                        "execution_time": optimized_time,
                        "cached": metadata.get("cached", False),
                        "compressed": metadata.get("compressed", False),
                        "data_size": metadata.get("original_size", 0)
                    }
                    
                    # Resilient execution (for comparison)
                    start_time = time.time()
                    success, result, metadata = execute_resilient_command(test_cmd, categorize_command_timeout(test_cmd))
                    resilient_time = time.time() - start_time
                    
                    results["resilient_only"] = {
                        "success": success,
                        "execution_time": resilient_time,
                        "retries": metadata.get("retries_attempted", 0)
                    }
                    
                    results["performance_gain"] = max(0, resilient_time - optimized_time)
                    results["gain_percentage"] = (results["performance_gain"] / max(resilient_time, 0.001)) * 100
                    
                    benchmark_results[test_cmd] = results
                
                return {
                    "benchmark_results": benchmark_results,
                    "summary": summarize_benchmark(benchmark_results),
                    "recommendations": get_benchmark_recommendations(benchmark_results)
                }
            
            else:
                return {
                    "error": f"Unknown action: {action}",
                    "available_actions": ["report", "set_level", "clear_cache", "stream", "benchmark"],
                    "examples": [
                        "performance_manager(action='report')",
                        "performance_manager(action='set_level', level='aggressive')",
                        "performance_manager(action='stream', command='!process 0 0')"
                    ]
                }
                
        except Exception as e:
            logger.error(f"Error in performance_manager: {e}")
            return {"error": str(e)}

    @mcp.tool()
    async def async_manager(ctx: Context, action: str, commands: List[str] = None, task_id: str = "", priority: str = "normal") -> Dict[str, Any]:
        """
        Manage asynchronous command execution for improved performance and concurrency.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "submit", "status", "result", "parallel", "stats", "cancel", "diagnostic"
            commands: List of commands for parallel execution
            task_id: Task ID for status/result/cancel actions
            priority: Task priority - "low", "normal", "high", "critical"
            
        Returns:
            Async operation results
        """
        logger.debug(f"Async manager action: {action}")
        
        try:
            if action == "submit":
                if not commands or len(commands) == 0:
                    return {
                        "error": "Commands required for submission",
                        "example": "async_manager(action='submit', commands=['version', 'lm'])"
                    }
                
                try:
                    task_priority = TaskPriority[priority.upper()]
                except (KeyError, AttributeError):
                    task_priority = TaskPriority.NORMAL
                
                # Submit commands for async execution
                task_ids = []
                for command in commands:
                    task_id = submit_async_command(command, task_priority)
                    task_ids.append(task_id)
                
                return {
                    "tasks_submitted": len(task_ids),
                    "task_ids": task_ids,
                    "priority": task_priority.name.lower(),
                    "tip": f"Use async_manager(action='status', task_id='<id>') to check progress"
                }
            
            elif action == "status":
                if not task_id:
                    # Get overall async system status
                    stats = get_async_stats()
                    return {
                        "async_system_status": stats,
                        "tip": "Provide task_id to get specific task status"
                    }
                else:
                    # Get specific task status
                    task = async_manager.get_task_status(task_id)
                    if task:
                        return {
                            "task_id": task_id,
                            "command": task.command,
                            "status": task.status.value,
                            "created_at": task.created_at.isoformat(),
                            "started_at": task.started_at.isoformat() if task.started_at else None,
                            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                            "error": task.error
                        }
                    else:
                        return {"error": f"Task not found: {task_id}"}
            
            elif action == "result":
                if not task_id:
                    return {"error": "Task ID required for result retrieval"}
                
                result = get_async_result(task_id, timeout=30.0)
                if result is not None:
                    return {
                        "task_id": task_id,
                        "result": result,
                        "tip": "Result retrieved successfully"
                    }
                else:
                    task = async_manager.get_task_status(task_id)
                    if task:
                        return {
                            "task_id": task_id,
                            "result": None,
                            "status": task.status.value,
                            "error": task.error,
                            "message": "Task not completed or failed"
                        }
                    else:
                        return {"error": f"Task not found: {task_id}"}
            
            elif action == "parallel":
                if not commands or len(commands) == 0:
                    return {
                        "error": "Commands required for parallel execution",
                        "example": "async_manager(action='parallel', commands=['version', 'lm', 'k'])"
                    }
                
                # Execute commands in parallel
                results = execute_parallel_commands(commands)
                
                # Format results
                formatted_results = {}
                for command, task in results.items():
                    formatted_results[command] = {
                        "status": task.status.value,
                        "success": task.status == TaskStatus.COMPLETED,
                        "result": task.result if task.status == TaskStatus.COMPLETED else None,
                        "error": task.error,
                        "execution_time": (task.completed_at - task.started_at).total_seconds() if task.started_at and task.completed_at else 0
                    }
                
                successful = sum(1 for r in formatted_results.values() if r["success"])
                
                return {
                    "parallel_execution_completed": True,
                    "commands_executed": len(commands),
                    "successful_commands": successful,
                    "results": formatted_results,
                    "performance_summary": f"{successful}/{len(commands)} commands completed successfully"
                }
            
            elif action == "stats":
                # Get detailed async statistics
                stats = get_async_stats()
                return {
                    "async_statistics": stats,
                    "performance_insights": get_async_insights(stats)
                }
            
            elif action == "cancel":
                if not task_id:
                    return {"error": "Task ID required for cancellation"}
                
                cancelled = async_manager.cancel_task(task_id)
                return {
                    "task_id": task_id,
                    "cancelled": cancelled,
                    "message": "Task cancelled" if cancelled else "Task could not be cancelled (may be running or completed)"
                }
            
            elif action == "diagnostic":
                # Run comprehensive diagnostic using async execution
                diagnostic_report = batch_executor.execute_diagnostic_sequence()
                
                return {
                    "diagnostic_report": diagnostic_report,
                    "execution_method": "async_parallel",
                    "tip": "Diagnostic commands were executed in parallel for better performance"
                }
            
            else:
                return {
                    "error": f"Unknown action: {action}",
                    "available_actions": ["submit", "status", "result", "parallel", "stats", "cancel", "diagnostic"],
                    "examples": [
                        "async_manager(action='parallel', commands=['version', 'lm'])",
                        "async_manager(action='diagnostic')",
                        "async_manager(action='stats')"
                    ]
                }
                
        except Exception as e:
            logger.error(f"Error in async_manager: {e}")
            return {"error": str(e)} 