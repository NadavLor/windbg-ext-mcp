"""
Main performance optimization coordinator.

Coordinates caching, compression, streaming, and execution optimization.
Simplified and cleaned of corrupted strings.
"""
from __future__ import annotations

import logging
import time
import threading
from typing import Dict, Any, List, Tuple, Generator
from dataclasses import dataclass, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

from .compression import DataCompressor
from .streaming import StreamingHandler
from .command_optimizer import CommandOptimizer
from core.communication import send_command
from core.unified_cache import (
    cache_command_result,
    get_cached_command_result,
    CacheContext,
    get_cache_stats,
    unified_cache,
)
from config import get_timeout_for_command, DebuggingMode

# Import unified execution system
from core.execution import execute_command as execute_unified

logger = logging.getLogger(__name__)


class OptimizationLevel(Enum):
    NONE = "none"
    BASIC = "basic"
    AGGRESSIVE = "aggressive"
    MAXIMUM = "maximum"


@dataclass
class PerformanceMetrics:
    total_commands: int = 0
    cached_hits: int = 0
    cache_miss: int = 0
    compression_saves: int = 0
    total_bytes_transferred: int = 0
    total_bytes_saved: int = 0
    average_command_time: float = 0.0
    network_latency: float = 0.0


# Commands that should bypass optimization and execute directly
BYPASS_OPTIMIZATION_COMMANDS = {
    ".reload /f", ".reload -f",
    ".restart", ".reboot",
    "g", "p", "t",
    "bp", "bc", "bd", "be",
    ".attach", ".detach",
    ".symfix", ".sympath",
}


class PerformanceOptimizer:
    def __init__(self, optimization_level: OptimizationLevel = OptimizationLevel.NONE) -> None:
        self.optimization_level = optimization_level
        self.compressor = DataCompressor()
        self.streaming = StreamingHandler()
        self.command_optimizer = CommandOptimizer()
        self.metrics = PerformanceMetrics()
        self._lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="PerfOpt")

    def should_bypass_optimization(self, command: str) -> bool:
        cmd = command.lower().strip()
        if any(b in cmd for b in BYPASS_OPTIMIZATION_COMMANDS):
            return True
        if any(p in cmd for p in [
            ".process /i", ".thread", "~", ".context",
            "ed ", "ew ", "eb ", "eq ",
            "!process", "!thread",
        ]):
            return True
        return False

    def _execute_direct_command(self, command: str, start_time: float) -> Tuple[bool, str, Dict[str, Any]]:
        try:
            timeout_ms = get_timeout_for_command(command, DebuggingMode.VM_NETWORK)
            result = send_command(command, timeout_ms=timeout_ms)
            exec_time = time.time() - start_time
            meta = {
                "cached": False,
                "compressed": False,
                "optimization_bypassed": True,
                "timeout_ms": timeout_ms,
                "response_time": exec_time,
                "optimization_level": "direct",
            }
            return True, result, meta
        except Exception as e:
            return False, str(e), {"error": str(e)}

    def execute_command(self, command: str) -> Dict[str, Any]:
        start = time.time()

        # Check cache first (unified cache)
        cache_key = command.strip()
        cached = get_cached_command_result(cache_key)
        if cached is not None:
            with self._lock:
                self.metrics.total_commands += 1
                self.metrics.cached_hits += 1
            return {
                "success": True,
                "result": cached,
                "metadata": {
                    "cached": True,
                    "response_time": 0.0,
                    "optimization_level": self.optimization_level.value,
                },
            }

        # Bypass if necessary
        if self.should_bypass_optimization(command):
            ok, res, meta = self._execute_direct_command(command, start)
            with self._lock:
                self.metrics.total_commands += 1
                self.metrics.cache_miss += 1
                self.metrics.average_command_time = (
                    (self.metrics.average_command_time + (time.time() - start)) / 2.0
                )
            return {"success": ok, "result": res if ok else None, "error": None if ok else res, "metadata": meta}

        # Use unified execution
        exec_result = execute_unified(command, resilient=True, optimize=True)
        with self._lock:
            self.metrics.total_commands += 1
            self.metrics.cache_miss += 1
            self.metrics.average_command_time = (
                (self.metrics.average_command_time + (time.time() - start)) / 2.0
            )

        if exec_result.success:
            cache_command_result(cache_key, exec_result.result, CacheContext.DEFAULT)
            return {
                "success": True,
                "result": exec_result.result,
                "metadata": exec_result.to_dict(),
            }
        return {"success": False, "error": exec_result.error, "metadata": exec_result.to_dict()}

    def execute_command_batch(self, commands: List[str]) -> Dict[str, Any]:
        if not commands:
            return {"results": [], "optimization": "empty_batch"}
        results: List[Dict[str, Any]] = []
        for cmd in commands:
            results.append(self.execute_command(cmd))
        return {"results": results, "optimization": "batched"}

    def get_performance_report(self) -> Dict[str, Any]:
        cache_stats = get_cache_stats()
        with self._lock:
            metrics = asdict(self.metrics)
        cache_hit_rate = metrics["cached_hits"] / max(metrics["total_commands"], 1)
        compression_rate = metrics["compression_saves"] / max(metrics["total_commands"], 1)
        bytes_saved_percent = metrics["total_bytes_saved"] / max(metrics["total_bytes_transferred"], 1) * 100

        return {
            "optimization_level": self.optimization_level.value,
            "performance_metrics": metrics,
            "cache_statistics": cache_stats,
            "performance_indicators": {
                "cache_hit_rate": cache_hit_rate,
                "compression_rate": compression_rate,
                "bytes_saved_percent": bytes_saved_percent,
                "average_command_time": metrics["average_command_time"],
            },
            "recommendations": self._get_performance_recommendations(cache_hit_rate, compression_rate, metrics),
        }

    def _get_performance_recommendations(self, cache_hit_rate: float, compression_rate: float, metrics: Dict[str, Any]) -> List[str]:
        rec: List[str] = []
        if cache_hit_rate < 0.3:
            rec.append("Low cache hit rate — consider increasing cache TTL for stable commands")
        elif cache_hit_rate > 0.8:
            rec.append("Excellent cache performance")
        if compression_rate < 0.1 and metrics["total_bytes_transferred"] > 1_000_000:
            rec.append("Consider enabling compression for large data transfers")
        if metrics["average_command_time"] > 5.0:
            rec.append("Slow command execution — check network connectivity and VM performance")
        if metrics["total_bytes_transferred"] > 10_000_000:
            rec.append("High data transfer volume — streaming optimization recommended")
        if not rec:
            rec.append("Performance optimization is working well")
        return rec

    def optimize_for_network_debugging(self) -> None:
        if self.optimization_level != OptimizationLevel.NONE:
            self.compressor.max_size = 300
            self.compressor.default_ttl = 600
        self.streaming.chunk_size = 2048
        logger.info("Applied network debugging optimizations")

    def clear_caches(self) -> None:
        unified_cache.clear_all()
        with self._lock:
            self.metrics = PerformanceMetrics()
        logger.info("Cleared performance caches and metrics")

