"""
Connection resilience and monitoring for WinDbg MCP Extension.

This module provides robust connection handling for kernel debugging scenarios,
including auto-retry mechanisms, connection health monitoring, VM state detection,
and adaptive timeout management optimized for network debugging.
"""
import logging
import time
import threading
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .communication import send_command, test_connection, CommunicationError, TimeoutError, ConnectionError

logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    """Current state of the debugging connection."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNSTABLE = "unstable"
    RECOVERING = "recovering"
    UNKNOWN = "unknown"

class VMState(Enum):
    """Current state of the target VM."""
    RESPONSIVE = "responsive"
    SLOW = "slow"
    HUNG = "hung"
    BREAK_MODE = "break_mode"
    RUNNING = "running"
    UNKNOWN = "unknown"

@dataclass
class ConnectionMetrics:
    """Metrics for connection health monitoring."""
    last_successful_command: Optional[datetime] = None
    consecutive_failures: int = 0
    total_commands: int = 0
    total_failures: int = 0
    average_response_time: float = 0.0
    last_response_time: float = 0.0
    connection_established: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    failure_streak_start: Optional[datetime] = None

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    exponential_backoff: bool = True
    max_delay: float = 30.0
    timeout_multiplier: float = 1.5  # Increase timeout on retry
    max_timeout: int = 120000  # Maximum timeout in ms

class ConnectionResilience:
    """Main class for connection resilience and monitoring."""
    
    def __init__(self):
        self.state = ConnectionState.UNKNOWN
        self.vm_state = VMState.UNKNOWN
        self.metrics = ConnectionMetrics()
        self.retry_config = RetryConfig()
        self.monitoring_enabled = True
        self.health_check_interval = 30.0  # seconds
        self._health_check_thread = None
        self._lock = threading.Lock()
        
        # Adaptive timeout settings
        self.base_timeouts = {
            "quick": 5000,      # version, simple commands
            "normal": 15000,    # most commands
            "slow": 30000,      # process lists, stack traces
            "bulk": 60000,      # !process 0 0, module lists
            "analysis": 120000  # !analyze, complex operations
        }
        
        # Network debugging multipliers
        self.network_multipliers = {
            "local": 1.0,
            "network": 2.0,     # Network debugging is slower
            "vm_network": 3.0   # VM over network is slowest
        }
        
        self.current_multiplier = 2.0  # Default to network debugging
        
    def start_monitoring(self):
        """Start background health monitoring."""
        if self._health_check_thread and self._health_check_thread.is_alive():
            return
            
        self.monitoring_enabled = True
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
            name="ConnectionHealthMonitor"
        )
        self._health_check_thread.start()
        logger.info("Started connection health monitoring")
    
    def stop_monitoring(self):
        """Stop background health monitoring."""
        self.monitoring_enabled = False
        if self._health_check_thread:
            self._health_check_thread.join(timeout=5.0)
        logger.info("Stopped connection health monitoring")
    
    def execute_with_resilience(
        self, 
        command: str, 
        timeout_category: str = "normal",
        custom_timeout: Optional[int] = None,
        max_retries: Optional[int] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Execute a command with resilience and retry logic.
        
        Args:
            command: The WinDbg command to execute
            timeout_category: Category for adaptive timeout ("quick", "normal", "slow", "bulk", "analysis")
            custom_timeout: Override timeout in milliseconds
            max_retries: Override max retry count
            
        Returns:
            Tuple of (success, result, metadata)
        """
        start_time = datetime.now()
        retries = max_retries if max_retries is not None else self.retry_config.max_retries
        
        # Calculate adaptive timeout
        if custom_timeout:
            timeout_ms = custom_timeout
        else:
            base_timeout = self.base_timeouts.get(timeout_category, self.base_timeouts["normal"])
            timeout_ms = int(base_timeout * self.current_multiplier)
        
        metadata = {
            "command": command,
            "timeout_category": timeout_category,
            "initial_timeout": timeout_ms,
            "retries_attempted": 0,
            "vm_state": self.vm_state.value,
            "connection_state": self.state.value,
            "start_time": start_time.isoformat()
        }
        
        last_error = None
        
        for attempt in range(retries + 1):
            try:
                # Update metrics
                with self._lock:
                    self.metrics.total_commands += 1
                
                # Detect VM state before command
                self._update_vm_state()
                
                # Calculate timeout for this attempt
                current_timeout = timeout_ms
                if attempt > 0:
                    # Increase timeout on retries
                    multiplier = self.retry_config.timeout_multiplier ** attempt
                    current_timeout = min(
                        int(timeout_ms * multiplier),
                        self.retry_config.max_timeout
                    )
                
                logger.debug(f"Attempt {attempt + 1}/{retries + 1}: executing '{command}' with timeout {current_timeout}ms")
                
                # Execute the command
                cmd_start = time.time()
                result = send_command(command, timeout_ms=current_timeout)
                cmd_duration = time.time() - cmd_start
                
                # Update success metrics
                with self._lock:
                    self.metrics.last_successful_command = datetime.now()
                    self.metrics.consecutive_failures = 0
                    self.metrics.last_response_time = cmd_duration
                    self._update_average_response_time(cmd_duration)
                    
                    if self.metrics.failure_streak_start:
                        self.metrics.failure_streak_start = None
                
                # Update connection state
                self._update_connection_state(success=True, response_time=cmd_duration)
                
                # Add success metadata
                metadata.update({
                    "success": True,
                    "retries_attempted": attempt,
                    "final_timeout": current_timeout,
                    "response_time": cmd_duration,
                    "end_time": datetime.now().isoformat()
                })
                
                return True, result, metadata
                
            except (CommunicationError, TimeoutError, ConnectionError) as e:
                last_error = e
                
                # Update failure metrics
                with self._lock:
                    self.metrics.consecutive_failures += 1
                    self.metrics.total_failures += 1
                    self.metrics.last_failure = datetime.now()
                    
                    if not self.metrics.failure_streak_start:
                        self.metrics.failure_streak_start = datetime.now()
                
                # Update connection state
                self._update_connection_state(success=False, error=e)
                
                logger.warning(f"Command '{command}' failed (attempt {attempt + 1}): {e}")
                
                # Check if we should retry
                if attempt < retries:
                    # Calculate retry delay
                    delay = self._calculate_retry_delay(attempt, e)
                    
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                    
                    # Try to recover connection if needed
                    if isinstance(e, ConnectionError):
                        self._attempt_connection_recovery()
                else:
                    logger.error(f"Command '{command}' failed after {retries + 1} attempts")
        
        # All retries exhausted
        total_duration = (datetime.now() - start_time).total_seconds()
        
        metadata.update({
            "success": False,
            "retries_attempted": retries,
            "final_error": str(last_error),
            "total_duration": total_duration,
            "end_time": datetime.now().isoformat()
        })
        
        return False, str(last_error), metadata
    
    def detect_vm_state(self) -> VMState:
        """
        Detect the current state of the target VM.
        
        Returns:
            The detected VM state
        """
        try:
            # Quick responsiveness test with kernel-compatible command
            start_time = time.time()
            result = send_command("version", timeout_ms=5000)  # Use version instead of ?
            response_time = time.time() - start_time
            
            if response_time > 10.0:
                return VMState.SLOW
            
            # Check if we're at a breakpoint
            try:
                registers = send_command("r", timeout_ms=3000)
                if "rip=" in registers.lower() or "eip=" in registers.lower():
                    return VMState.BREAK_MODE
            except:
                pass
            
            # Check if target is running
            try:
                thread_info = send_command("~", timeout_ms=3000)
                if "running" in thread_info.lower():
                    return VMState.RUNNING
            except:
                pass
            
            return VMState.RESPONSIVE
            
        except TimeoutError:
            return VMState.HUNG
        except ConnectionError:
            return VMState.UNKNOWN
        except:
            return VMState.UNKNOWN
    
    def get_adaptive_timeout(self, category: str, command: str = "") -> int:
        """
        Get adaptive timeout based on category, command, and current conditions.
        
        Args:
            category: Timeout category
            command: The specific command (for command-specific adjustments)
            
        Returns:
            Adaptive timeout in milliseconds
        """
        base_timeout = self.base_timeouts.get(category, self.base_timeouts["normal"])
        
        # Apply network multiplier
        timeout = int(base_timeout * self.current_multiplier)
        
        # Command-specific adjustments
        if command:
            if any(cmd in command.lower() for cmd in ["!process 0 0", "!handle 0 f"]):
                timeout = max(timeout, self.base_timeouts["bulk"])
            elif "!analyze" in command.lower():
                timeout = max(timeout, self.base_timeouts["analysis"])
            elif command.lower() in ["version", "r"]:
                timeout = min(timeout, self.base_timeouts["quick"] * 2)
        
        # Adjust based on VM state
        if self.vm_state == VMState.SLOW:
            timeout = int(timeout * 2.0)
        elif self.vm_state == VMState.HUNG:
            timeout = min(timeout, 10000)  # Don't wait too long for hung VM
        
        # Adjust based on connection state
        if self.state == ConnectionState.UNSTABLE:
            timeout = int(timeout * 1.5)
        
        return min(timeout, self.retry_config.max_timeout)
    
    def get_connection_health(self) -> Dict[str, Any]:
        """
        Get comprehensive connection health information.
        
        Returns:
            Dictionary with health metrics and recommendations
        """
        with self._lock:
            metrics = self.metrics
            
        now = datetime.now()
        health_score = self._calculate_health_score()
        
        health_info = {
            "connection_state": self.state.value,
            "vm_state": self.vm_state.value,
            "health_score": health_score,
            "metrics": {
                "total_commands": metrics.total_commands,
                "total_failures": metrics.total_failures,
                "failure_rate": metrics.total_failures / max(metrics.total_commands, 1),
                "consecutive_failures": metrics.consecutive_failures,
                "average_response_time": metrics.average_response_time,
                "last_response_time": metrics.last_response_time
            },
            "timing": {
                "connection_established": metrics.connection_established.isoformat() if metrics.connection_established else None,
                "last_successful_command": metrics.last_successful_command.isoformat() if metrics.last_successful_command else None,
                "last_failure": metrics.last_failure.isoformat() if metrics.last_failure else None,
                "uptime": str(now - metrics.connection_established) if metrics.connection_established else None
            },
            "recommendations": self._get_health_recommendations(health_score)
        }
        
        return health_info
    
    def set_network_mode(self, mode: str):
        """
        Set the network debugging mode for adaptive timeouts.
        
        Args:
            mode: "local", "network", or "vm_network"
        """
        if mode in self.network_multipliers:
            self.current_multiplier = self.network_multipliers[mode]
            logger.info(f"Set network mode to '{mode}' (multiplier: {self.current_multiplier})")
        else:
            logger.warning(f"Unknown network mode: {mode}")
    
    def _health_check_loop(self):
        """Background health monitoring loop."""
        while self.monitoring_enabled:
            try:
                # Perform health check
                is_connected = test_connection()
                
                with self._lock:
                    if is_connected:
                        if self.state == ConnectionState.DISCONNECTED:
                            self.state = ConnectionState.CONNECTED
                            self.metrics.connection_established = datetime.now()
                            logger.info("Connection restored")
                    else:
                        if self.state == ConnectionState.CONNECTED:
                            self.state = ConnectionState.DISCONNECTED
                            logger.warning("Connection lost")
                
                # Update VM state periodically
                if is_connected:
                    self._update_vm_state()
                
                time.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"Health check error: {e}")
                time.sleep(self.health_check_interval)
    
    def _update_vm_state(self):
        """Update VM state detection."""
        try:
            new_state = self.detect_vm_state()
            if new_state != self.vm_state:
                logger.debug(f"VM state changed: {self.vm_state.value} -> {new_state.value}")
                self.vm_state = new_state
        except Exception as e:
            logger.debug(f"Failed to update VM state: {e}")
    
    def _update_connection_state(self, success: bool, response_time: float = 0.0, error: Exception = None):
        """Update connection state based on command results."""
        if success:
            if response_time > 10.0:
                self.state = ConnectionState.UNSTABLE
            else:
                self.state = ConnectionState.CONNECTED
        else:
            if isinstance(error, ConnectionError):
                self.state = ConnectionState.DISCONNECTED
            elif isinstance(error, TimeoutError):
                self.state = ConnectionState.UNSTABLE
            else:
                # Keep current state for other errors
                pass
    
    def _calculate_retry_delay(self, attempt: int, error: Exception) -> float:
        """Calculate delay before retry based on attempt and error type."""
        base_delay = self.retry_config.base_delay
        
        if self.retry_config.exponential_backoff:
            delay = base_delay * (2 ** attempt)
        else:
            delay = base_delay * (attempt + 1)
        
        # Adjust based on error type
        if isinstance(error, ConnectionError):
            delay *= 2.0  # Wait longer for connection errors
        elif isinstance(error, TimeoutError):
            delay *= 1.5  # Moderate delay for timeouts
        
        return min(delay, self.retry_config.max_delay)
    
    def _attempt_connection_recovery(self):
        """Attempt to recover from connection failures."""
        logger.info("Attempting connection recovery...")
        
        self.state = ConnectionState.RECOVERING
        
        # Try a simple connection test
        try:
            if test_connection():
                self.state = ConnectionState.CONNECTED
                logger.info("Connection recovery successful")
            else:
                self.state = ConnectionState.DISCONNECTED
                logger.warning("Connection recovery failed")
        except Exception as e:
            logger.error(f"Connection recovery attempt failed: {e}")
            self.state = ConnectionState.DISCONNECTED
    
    def _update_average_response_time(self, response_time: float):
        """Update the rolling average response time."""
        if self.metrics.average_response_time == 0.0:
            self.metrics.average_response_time = response_time
        else:
            # Simple exponential moving average
            alpha = 0.1
            self.metrics.average_response_time = (
                alpha * response_time + 
                (1 - alpha) * self.metrics.average_response_time
            )
    
    def _calculate_health_score(self) -> float:
        """Calculate a health score from 0.0 (poor) to 1.0 (excellent)."""
        score = 1.0
        
        # Penalize for consecutive failures
        if self.metrics.consecutive_failures > 0:
            score *= max(0.1, 1.0 - (self.metrics.consecutive_failures * 0.2))
        
        # Penalize for high failure rate
        if self.metrics.total_commands > 10:
            failure_rate = self.metrics.total_failures / self.metrics.total_commands
            score *= max(0.2, 1.0 - failure_rate)
        
        # Penalize for slow responses
        if self.metrics.average_response_time > 5.0:
            score *= max(0.3, 1.0 - (self.metrics.average_response_time / 30.0))
        
        # Penalize based on connection state
        if self.state == ConnectionState.DISCONNECTED:
            score *= 0.1
        elif self.state == ConnectionState.UNSTABLE:
            score *= 0.5
        elif self.state == ConnectionState.RECOVERING:
            score *= 0.3
        
        return max(0.0, min(1.0, score))
    
    def _get_health_recommendations(self, health_score: float) -> List[str]:
        """Get recommendations based on health score and metrics."""
        recommendations = []
        
        if health_score < 0.3:
            recommendations.append("⚠️ Connection health is poor - consider restarting the debugging session")
        elif health_score < 0.6:
            recommendations.append("⚡ Connection is unstable - check network connectivity")
        
        if self.metrics.consecutive_failures > 3:
            recommendations.append("🔄 Multiple consecutive failures detected - verify WinDbg extension is loaded")
        
        if self.metrics.average_response_time > 10.0:
            recommendations.append("🐌 Slow response times detected - target VM may be under load")
        
        if self.vm_state == VMState.HUNG:
            recommendations.append("🚫 Target VM appears hung - try breaking into debugger")
        elif self.vm_state == VMState.SLOW:
            recommendations.append("⏳ Target VM is responding slowly - consider increasing timeouts")
        
        if self.state == ConnectionState.DISCONNECTED:
            recommendations.append("❌ Connection lost - check WinDbg and extension status")
        
        if not recommendations:
            recommendations.append("✅ Connection health is good")
        
        return recommendations

# Global instance for use across the application
connection_resilience = ConnectionResilience()

# Convenience functions
def execute_resilient_command(
    command: str, 
    timeout_category: str = "normal", 
    max_retries: Optional[int] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """Execute a command with resilience. Returns (success, result, metadata)."""
    return connection_resilience.execute_with_resilience(
        command, timeout_category, max_retries=max_retries
    )

def get_connection_health() -> Dict[str, Any]:
    """Get current connection health information."""
    return connection_resilience.get_connection_health()

def set_network_debugging_mode(mode: str):
    """Set network debugging mode for adaptive timeouts."""
    connection_resilience.set_network_mode(mode)

def start_connection_monitoring():
    """Start background connection monitoring."""
    connection_resilience.start_monitoring()

def stop_connection_monitoring():
    """Stop background connection monitoring."""
    connection_resilience.stop_monitoring() 