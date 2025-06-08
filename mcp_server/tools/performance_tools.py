"""
Performance management and optimization tools for WinDbg MCP server.

This module provides tools for managing performance optimization settings,
monitoring performance metrics, and controlling execution optimization.
"""
import logging
import time
import asyncio
from typing import Dict, Any, List, Optional, Union
from fastmcp import FastMCP, Context

from core.performance import (
    stream_large_command, get_performance_report,
    set_optimization_level, clear_performance_caches, OptimizationLevel
)
from core.async_ops import (
    submit_async_command, get_async_result, execute_parallel_commands,
    get_async_stats, async_manager, batch_executor, TaskPriority, TaskStatus
)
from core.communication import send_command
from .tool_utilities import (
    get_performance_recommendations, 
    get_optimization_effects, summarize_benchmark, get_benchmark_recommendations,
    get_async_insights
)

logger = logging.getLogger(__name__)

def register_performance_tools(mcp: FastMCP):
    """Register all performance management tools."""
    
    @mcp.tool()
    async def performance_manager(ctx: Context, action: str, level: str = "", command: str = "") -> Union[str, Dict[str, Any]]:
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
                    "recommendations": f"Current optimization level: {perf_report.get('optimization_level', 'unknown')}",
                    "status": "Performance report generated"
                }
                
            elif action == "set_level":
                if not level:
                    return {"error": "Optimization level required. Use: none, basic, aggressive, maximum"}
                
                try:
                    opt_level = OptimizationLevel(level)
                    set_optimization_level(opt_level)
                    return {
                        "success": True,
                        "optimization_level": level,
                        "effects": {
                            "none": "No optimization, direct command execution",
                            "basic": "Basic caching and timeout optimization",
                            "aggressive": "Advanced caching, parallel execution, smart retries",
                            "maximum": "Full optimization with prediction and streaming"
                        }.get(level, "Unknown level"),
                        "status": f"Optimization level set to {level}"
                    }
                except ValueError:
                    return {"error": f"Invalid optimization level: {level}. Use: none, basic, aggressive, maximum"}
                    
            elif action == "clear_cache":
                clear_performance_caches()
                return {
                    "cache_cleared": True,
                    "entries_removed": "cleared",
                    "status": "Performance cache cleared"
                }
                
            elif action == "stream":
                if not command:
                    return {"error": "Command required for streaming action"}
                
                try:
                    # Execute streaming command
                    stream_results = []
                    for chunk in stream_large_command(command):
                        stream_results.append(chunk)
                        if chunk.get("type") == "complete":
                            break
                    
                    return {
                        "streaming_result": stream_results,
                        "command": command,
                        "status": "Streaming execution completed"
                    }
                except Exception as e:
                    return {"error": f"Streaming execution failed: {str(e)}"}
                    
            elif action == "benchmark":
                if not command:
                    command = "version"  # Default benchmark command
                
                # Run benchmark test
                times = []
                iterations = 5
                
                for i in range(iterations):
                    start_time = time.time()
                    try:
                        from core.execution.timeout_resolver import resolve_timeout
                        from config import DebuggingMode
                        timeout_ms = resolve_timeout(command, DebuggingMode.VM_NETWORK)
                        result = send_command(command, timeout_ms=timeout_ms)
                        end_time = time.time()
                        if result:  # Only count successful executions
                            times.append((end_time - start_time) * 1000)  # Convert to ms
                    except Exception as e:
                        logger.warning(f"Benchmark iteration {i+1} failed: {e}")
                
                if times:
                    avg_time = sum(times) / len(times)
                    min_time = min(times)
                    max_time = max(times)
                    
                    return {
                        "benchmark_results": {
                            "command": command,
                            "iterations": len(times),
                            "average_time_ms": f"{avg_time:.2f}",
                            "min_time_ms": f"{min_time:.2f}",
                            "max_time_ms": f"{max_time:.2f}",
                            "success_rate": f"{len(times)/iterations*100:.1f}%"
                        },
                        "status": "Benchmark completed"
                    }
                else:
                    return {"error": "Benchmark failed - no successful command executions"}
                    
            else:
                return {
                    "error": f"Unknown action: {action}",
                    "available_actions": ["report", "set_level", "clear_cache", "stream", "benchmark"],
                    "examples": [
                        "performance_manager(action='report')",
                        "performance_manager(action='set_level', level='aggressive')",
                        "performance_manager(action='benchmark', command='version')"
                    ]
                }
                
        except Exception as e:
            logger.error(f"Performance manager error: {e}")
            return {"error": str(e)}

    @mcp.tool()
    async def async_manager(ctx: Context, action: str, commands: List[str] = None, task_id: str = "", priority: str = "normal") -> Dict[str, Any]:
        """
        Manage asynchronous command execution for performance and concurrency.
        
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