"""
Shared utilities for WinDbg MCP tools.

This module contains helper functions and utilities used across multiple tool files.
"""
import logging
from typing import Dict, Any, List, Optional
from core.communication import send_command
from core.performance import execute_optimized_command
from core.connection_resilience import execute_resilient_command
from core.performance import OptimizationLevel

logger = logging.getLogger(__name__)

def categorize_command_timeout(command: str) -> str:
    """
    Categorize command for timeout optimization.
    
    Args:
        command: The WinDbg command
        
    Returns:
        Timeout category string
    """
    command_lower = command.lower().strip()
    
    if any(cmd in command_lower for cmd in ["version", "r", "?", ".effmach"]):
        return "quick"
    elif any(cmd in command_lower for cmd in ["!process 0 0", "!handle 0 f", "lm"]):
        return "bulk"
    elif any(cmd in command_lower for cmd in ["!analyze", "!poolfind", "!poolused"]):
        return "analysis"
    elif any(cmd in command_lower for cmd in ["k", "!thread", "!dlls"]):
        return "slow"
    else:
        return "normal"

def get_direct_timeout(command: str) -> int:
    """
    Get direct timeout for a command in milliseconds.
    
    Args:
        command: The WinDbg command
        
    Returns:
        Timeout in milliseconds
    """
    category = categorize_command_timeout(command)
    timeouts = {
        "quick": 5000,
        "normal": 15000,
        "slow": 30000,
        "bulk": 60000,
        "analysis": 120000
    }
    return timeouts.get(category, 15000)

def detect_kernel_mode() -> bool:
    """
    Detect if we're in kernel-mode debugging.
    
    Returns:
        True if kernel mode, False if user mode
    """
    try:
        success, result, _ = execute_resilient_command(".effmach", "quick")
        if success and any(x in result.lower() for x in ["x64_kernel", "x86_kernel", "kernel mode"]):
            return True
        
        # Try alternative detection
        success, result, _ = execute_resilient_command("!pcr", "quick")
        if success and not result.startswith("Error:") and "is not a recognized" not in result:
            return True
        
        return False
    except:
        return False

def get_command_suggestions(command: str, result: str) -> Optional[List[str]]:
    """
    Get suggestions for alternative commands based on command and result.
    
    Args:
        command: The original command
        result: The command result
        
    Returns:
        List of suggestions or None
    """
    suggestions = []
    
    if "not found" in result.lower() or "invalid" in result.lower():
        if command.startswith("!"):
            suggestions.append(f"Try '.help {command}' for command documentation")
            suggestions.append("Check if required extension is loaded")
        else:
            suggestions.append("Verify command syntax with WinDbg documentation")
    
    if "access denied" in result.lower():
        suggestions.append("Command requires higher privileges or different context")
        suggestions.append("Try switching to appropriate process/thread context")
    
    if suggestions:
        return suggestions
    
    return None

def get_performance_recommendations(perf_report: Dict[str, Any], async_stats: Dict[str, Any]) -> List[str]:
    """
    Generate performance recommendations based on metrics.
    
    Args:
        perf_report: Performance report data
        async_stats: Async operation statistics
        
    Returns:
        List of performance recommendations
    """
    recommendations = []
    
    indicators = perf_report.get("performance_indicators", {})
    cache_hit_rate = indicators.get("cache_hit_rate", 0)
    
    if cache_hit_rate < 0.3:
        recommendations.append("📈 Low cache hit rate - try using similar commands to benefit from caching")
    elif cache_hit_rate > 0.7:
        recommendations.append("🚀 Excellent cache performance - repeated commands are very fast")
    
    async_success_rate = async_stats.get("success_rate", 1.0)
    if async_success_rate < 0.8:
        recommendations.append("⚠️ Some async operations failing - check connection stability")
    
    if async_stats.get("total_tasks", 0) > 10:
        recommendations.append("🔄 Heavy async usage detected - performance optimization is helping")
    
    return recommendations

def get_optimization_effects(level) -> List[str]:
    """
    Get the effects of an optimization level.
    
    Args:
        level: OptimizationLevel enum value
        
    Returns:
        List of optimization effects
    """
    if level == OptimizationLevel.NONE:
        return ["No optimization", "Direct command execution", "No caching or compression"]
    elif level == OptimizationLevel.BASIC:
        return ["Basic result caching", "Simple timeout optimization", "Minimal overhead"]
    elif level == OptimizationLevel.AGGRESSIVE:
        return [
            "Intelligent result caching with TTL",
            "Data compression for large outputs",
            "Adaptive timeout management", 
            "Background performance monitoring",
            "Network debugging optimization"
        ]
    elif level == OptimizationLevel.MAXIMUM:
        return [
            "Maximum caching with extended TTL",
            "Aggressive compression thresholds",
            "Concurrent command execution",
            "Full performance analytics",
            "All optimization features enabled"
        ]
    else:
        return ["Unknown optimization level"]

def summarize_benchmark(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize benchmark results.
    
    Args:
        results: Raw benchmark results
        
    Returns:
        Summarized benchmark data
    """
    summary = {
        "total_commands": 0,
        "total_time": 0.0,
        "fastest_command": None,
        "slowest_command": None,
        "cache_benefit": "unknown"
    }
    
    if "results" in results:
        command_results = results["results"]
        summary["total_commands"] = len(command_results)
        
        times = []
        for cmd_result in command_results:
            if "execution_time" in cmd_result:
                times.append(cmd_result["execution_time"])
        
        if times:
            summary["total_time"] = sum(times)
            summary["average_time"] = sum(times) / len(times)
            summary["fastest_time"] = min(times)
            summary["slowest_time"] = max(times)
    
    return summary

def get_benchmark_recommendations(results: Dict[str, Any]) -> List[str]:
    """
    Get recommendations based on benchmark results.
    
    Args:
        results: Benchmark results
        
    Returns:
        List of recommendations
    """
    recommendations = []
    summary = summarize_benchmark(results)
    
    if summary.get("average_time", 0) > 2.0:
        recommendations.append("⏱️ Commands are running slowly - check network connection and VM performance")
    
    if summary.get("total_commands", 0) > 5:
        recommendations.append("📊 Multiple commands tested - consider using async_manager for parallel execution")
    
    cache_hits = sum(1 for r in results.get("results", []) if r.get("metadata", {}).get("cached", False))
    if cache_hits > 0:
        recommendations.append(f"🎯 {cache_hits} commands served from cache - optimization is working")
    
    return recommendations

def get_async_insights(stats: Dict[str, Any]) -> List[str]:
    """
    Generate insights from async operation statistics.
    
    Args:
        stats: Async operation statistics
        
    Returns:
        List of insights
    """
    insights = []
    
    total_tasks = stats.get("total_tasks", 0)
    if total_tasks == 0:
        insights.append("No async tasks executed yet")
        return insights
    
    success_rate = stats.get("success_rate", 0)
    if success_rate > 0.9:
        insights.append(f"🎯 Excellent async success rate: {success_rate:.1%}")
    elif success_rate > 0.7:
        insights.append(f"👍 Good async success rate: {success_rate:.1%}")
    else:
        insights.append(f"⚠️ Low async success rate: {success_rate:.1%} - check connection stability")
    
    concurrent_peak = stats.get("concurrent_peak", 0)
    if concurrent_peak > 1:
        insights.append(f"🚀 Peak concurrent tasks: {concurrent_peak} - parallel execution active")
    
    avg_time = stats.get("average_execution_time", 0)
    if avg_time > 0:
        insights.append(f"⏱️ Average task time: {avg_time:.2f}s")
    
    return insights 