"""
Shared utilities for WinDbg MCP tools.

This module contains helper functions and utilities used across multiple tool files.
"""
import logging
from typing import Dict, Any, List, Optional

from core.communication import send_command
from core.performance import OptimizationLevel


def detect_kernel_mode() -> bool:
    """Return True if the target is kernel-mode, else False."""
    try:
        from core.execution.timeout_resolver import resolve_timeout
        from config import DebuggingMode

        timeout_ms = resolve_timeout(".effmach", DebuggingMode.VM_NETWORK)
        result = send_command(".effmach", timeout_ms=timeout_ms)
        if result and any(x in result.lower() for x in ["x64_kernel", "x86_kernel", "kernel mode"]):
            return True

        timeout_ms = resolve_timeout("!pcr", DebuggingMode.VM_NETWORK)
        result = send_command("!pcr", timeout_ms=timeout_ms)
        if result and not result.startswith("Error:") and "is not a recognized" not in result:
            return True

        return False
    except Exception:
        return False


def get_command_suggestions(command: str, result: str) -> Optional[List[str]]:
    """Return simple suggestions based on output text."""
    suggestions: List[str] = []

    low = result.lower()
    if "not found" in low or "invalid" in low:
        if command.startswith("!"):
            suggestions.append(f"Try '.help {command}' for command documentation")
            suggestions.append("Check if the required extension is loaded")
        else:
            suggestions.append("Verify command syntax in WinDbg docs")

    if "access denied" in low:
        suggestions.append("Command may require elevated privileges or different context")
        suggestions.append("Switch to the appropriate process/thread context")

    return suggestions or None


def get_performance_recommendations(perf_report: Dict[str, Any], async_stats: Dict[str, Any]) -> List[str]:
    """Generate short performance recommendations from metrics."""
    rec: List[str] = []

    indicators = perf_report.get("performance_indicators", {})
    cache_hit_rate = indicators.get("cache_hit_rate", 0.0)
    if cache_hit_rate < 0.3:
        rec.append("Low cache hit rate — repeat common queries to warm caches")
    elif cache_hit_rate > 0.7:
        rec.append("Excellent cache performance — repeated commands are fast")

    async_success_rate = async_stats.get("success_rate", 1.0)
    if async_success_rate < 0.8:
        rec.append("Some async operations are failing — check connection stability")

    if async_stats.get("total_tasks", 0) > 10:
        rec.append("Heavy async usage detected — optimization is helping")

    return rec


def get_optimization_effects(level: OptimizationLevel) -> List[str]:
    """Return human text for optimization level effects."""
    if level == OptimizationLevel.NONE:
        return ["No optimization", "Direct command execution", "No caching or compression"]
    if level == OptimizationLevel.BASIC:
        return ["Basic result caching", "Simple timeout optimization", "Minimal overhead"]
    if level == OptimizationLevel.AGGRESSIVE:
        return [
            "Intelligent result caching with TTL",
            "Data compression for large outputs",
            "Adaptive timeout management",
            "Background performance monitoring",
            "Network debugging optimization",
        ]
    if level == OptimizationLevel.MAXIMUM:
        return [
            "Maximum caching with extended TTL",
            "Aggressive compression thresholds",
            "Concurrent command execution",
            "Full performance analytics",
            "All optimization features enabled",
        ]
    return ["Unknown optimization level"]


def summarize_benchmark(results: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize benchmark run results."""
    summary: Dict[str, Any] = {
        "total_commands": 0,
        "total_time": 0.0,
        "fastest_command": None,
        "slowest_command": None,
        "cache_benefit": "unknown",
    }

    if "results" in results:
        command_results = results["results"]
        summary["total_commands"] = len(command_results)

        times: List[float] = []
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
    """Return guidance based on summarized benchmark data."""
    rec: List[str] = []
    summary = summarize_benchmark(results)

    if summary.get("average_time", 0) > 2.0:
        rec.append("Commands are running slowly — check network and VM performance")

    if summary.get("total_commands", 0) > 5:
        rec.append("Multiple commands tested — consider async_manager for parallel execution")

    cache_hits = sum(1 for r in results.get("results", []) if r.get("metadata", {}).get("cached", False))
    if cache_hits > 0:
        rec.append(f"{cache_hits} commands served from cache — optimization is working")

    return rec


def get_async_insights(stats: Dict[str, Any]) -> List[str]:
    """Generate short insights from async stats."""
    insights: List[str] = []

    total_tasks = stats.get("total_tasks", 0)
    if total_tasks == 0:
        insights.append("No async tasks executed yet")
        return insights

    success_rate = stats.get("success_rate", 0.0)
    if success_rate > 0.9:
        insights.append(f"Excellent async success rate: {success_rate:.1%}")
    elif success_rate > 0.7:
        insights.append(f"Good async success rate: {success_rate:.1%}")
    else:
        insights.append(f"Low async success rate: {success_rate:.1%} — check connection stability")

    concurrent_peak = stats.get("concurrent_peak", 0)
    if concurrent_peak > 1:
        insights.append(f"Peak concurrent tasks: {concurrent_peak} — parallel execution active")

    avg_time = stats.get("average_execution_time", 0.0)
    if avg_time > 0:
        insights.append(f"Average task time: {avg_time:.2f}s")

    return insights

