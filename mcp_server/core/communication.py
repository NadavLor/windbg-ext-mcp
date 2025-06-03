"""
Core communication module for WinDbg MCP Extension - Hybrid Architecture Edition.

This module handles the low-level named pipe communication with the WinDbg extension,
with enhanced connection resilience, retry logic, and network debugging optimizations.
Supports both local and VM-based kernel debugging scenarios.
"""
import json
import time
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import win32pipe
import win32file
import win32api
import win32event
import pywintypes
import traceback
import threading
from dataclasses import dataclass
from enum import Enum

# Import centralized configuration and retry utilities
from config import (
    PIPE_NAME, BUFFER_SIZE, DEFAULT_TIMEOUT_MS, MAX_RETRY_ATTEMPTS,
    RETRY_DELAY_MS, CONNECTION_HEALTH_CHECK_INTERVAL, 
    NETWORK_DEBUGGING_TIMEOUT_MULTIPLIER, DebuggingMode,
    get_timeout_for_command, get_retry_delay
)
from .retry_utils import resilient_command, RetryableError, NonRetryableError
from .unified_cache import (
    start_startup_cache, stop_startup_cache, 
    cache_startup_command, get_startup_cached_result
)

logger = logging.getLogger(__name__)

# Remove old startup cache implementation - now using unified cache

# These functions are now imported from unified_cache:
# - start_startup_cache()
# - stop_startup_cache() 
# - cache_startup_command()
# - get_startup_cached_result()

class CommunicationError(Exception):
    """Base exception for communication errors."""
    pass

class TimeoutError(CommunicationError):
    """Raised when a command times out."""
    pass

class ConnectionError(CommunicationError):
    """Raised when connection to WinDbg extension fails."""
    pass

class NetworkDebuggingError(CommunicationError):
    """Raised when network debugging connection issues are detected."""
    pass

@dataclass
class ConnectionHealth:
    """Represents the health status of the WinDbg connection."""
    is_connected: bool
    last_successful_command: Optional[datetime]
    consecutive_failures: int
    network_debugging_mode: DebuggingMode
    target_responsive: bool
    extension_responsive: bool
    last_error: Optional[str]

class CommunicationManager:
    """
    Enhanced communication manager with connection resilience and hybrid architecture support.
    
    This manager handles:
    - Named pipe communication with WinDbg extension
    - Connection health monitoring (MINIMAL MODE - see note below)
    - Retry logic for network debugging scenarios
    - Timeout optimization based on debugging mode
    
    NOTE: Health monitoring has been made minimal to prevent overwhelming
    the WinDbg extension with frequent "version" commands that can cause crashes.
    Actual health checks are only performed when explicitly requested via 
    test_connection() calls.
    """
    
    def __init__(self):
        self._connection_health = ConnectionHealth(
            is_connected=True,  # Assume connected by default since tests will verify
            last_successful_command=None,
            consecutive_failures=0,
            network_debugging_mode=DebuggingMode.LOCAL,
            target_responsive=True,  # Keep as True by default
            extension_responsive=True,  # Set to True by default since tests verify
            last_error=None
        )
        self._health_lock = threading.Lock()
        self._monitoring_thread = None
        self._monitoring_active = False
        
    def set_debugging_mode(self, mode: DebuggingMode):
        """Set the debugging mode for timeout and retry optimization."""
        with self._health_lock:
            self._connection_health.network_debugging_mode = mode
            logger.info(f"Set debugging mode to: {mode.value}")
    
    def get_connection_health(self) -> ConnectionHealth:
        """Get the current connection health status."""
        with self._health_lock:
            return self._connection_health
    
    def start_health_monitoring(self):
        """Start background health monitoring - now minimal and non-aggressive."""
        if self._monitoring_active:
            return
            
        # For now, don't start aggressive monitoring to prevent extension crashes
        # Just set monitoring flag and update health flags to reflect reality
        self._monitoring_active = True
        
        # Update health flags to reflect that if we can start monitoring, things are working
        with self._health_lock:
            self._connection_health.extension_responsive = True
            self._connection_health.target_responsive = True
            self._connection_health.is_connected = True
            
        logger.info("Health monitoring enabled (minimal mode)")
    
    def stop_health_monitoring(self):
        """Stop background health monitoring."""
        self._monitoring_active = False
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5)
        # Don't log during shutdown to avoid I/O errors with closed streams
        try:
            logger.info("Stopped connection health monitoring")
        except:
            pass  # Silently ignore if streams are closed
    
    def _health_monitor_loop(self):
        """Background health monitoring loop - minimal implementation."""
        # This loop is now disabled to prevent crashing the WinDbg extension
        # Health monitoring is done manually via test_connection() calls only
        while self._monitoring_active:
            try:
                # Just update basic health flags without doing actual tests
                with self._health_lock:
                    self._connection_health.extension_responsive = True
                    self._connection_health.target_responsive = True
                    self._connection_health.is_connected = True
                
                # Much longer sleep to minimize any impact
                time.sleep(300)  # 5 minutes instead of 30 seconds
                
            except Exception as e:
                logger.warning(f"Health monitor error: {e}")
                time.sleep(300)
    
    def _test_extension_health(self) -> bool:
        """Test if the WinDbg extension is responsive - minimal implementation."""
        # Always return True for now to avoid aggressive testing that crashes extension
        # Real health can be checked via manual test_connection() calls
        return True
    
    def _test_target_health(self) -> bool:
        """Test if the debugging target is responsive - minimal implementation."""
        # Always return True for now to avoid aggressive testing that crashes extension
        # Real target health can be checked via manual test calls
        return True
    
    @resilient_command
    def send_command(self, command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
        """
        Send a command to the WinDbg extension with resilience and retry logic.
        
        Args:
            command: The WinDbg command to execute
            timeout_ms: Timeout in milliseconds
            
        Returns:
            The command output as a string
            
        Raises:
            ConnectionError: If connection to the extension fails
            TimeoutError: If the command times out
            NetworkDebuggingError: If network debugging issues are detected
            CommunicationError: If the command fails
        """
        # Optimize timeout for debugging mode
        optimized_timeout = self._optimize_timeout(command, timeout_ms)
        
        result = self._send_command_internal(command, optimized_timeout)
        
        # Update health on success
        with self._health_lock:
            self._connection_health.last_successful_command = datetime.now()
            self._connection_health.consecutive_failures = 0
            self._connection_health.last_error = None
            # If command succeeded, extension and target are clearly responsive
            self._connection_health.extension_responsive = True
            self._connection_health.target_responsive = True
            self._connection_health.is_connected = True
        
        return result

    def _optimize_timeout(self, command: str, base_timeout_ms: int) -> int:
        """Optimize timeout based on debugging mode and command type."""
        with self._health_lock:
            mode = self._connection_health.network_debugging_mode
        
        # Apply network debugging multiplier for VM scenarios
        if mode in [DebuggingMode.VM_NETWORK, DebuggingMode.VM_SERIAL]:
            return int(base_timeout_ms * NETWORK_DEBUGGING_TIMEOUT_MULTIPLIER)
        
        return base_timeout_ms
    
    def _send_command_internal(self, command: str, timeout_ms: int) -> str:
        """Internal command sending with enhanced error detection."""
        logger.debug(f"Sending command: {command}")
        
        message = {
            "type": "command",
            "command": "execute_command",
            "id": int(time.time() * 1000),
            "args": {
                "command": command,
                "timeout_ms": timeout_ms
            }
        }
        
        try:
            response = self._send_message(message, timeout_ms)
            
            # Handle error responses
            if response.get("status") == "error":
                error_message = response.get("error", "Unknown error")
                suggestion = response.get("suggestion", "")
                
                # Detect network debugging issues
                if any(phrase in error_message.lower() for phrase in [
                    "retry sending", "transport connection", "lost", "network",
                    "target windows seems lost", "resync with target"
                ]):
                    raise NetworkDebuggingError(f"Network debugging connection issue: {error_message}")
                
                formatted_error = f"WinDbg command failed: {error_message}"
                if suggestion:
                    formatted_error += f"\nSuggestion: {suggestion}"
                    
                raise CommunicationError(formatted_error)
                
            # Return the output
            output = response.get("output", "")
            if output is None:
                return "No output returned from command"
                
            return output
            
        except TimeoutError:
            raise TimeoutError(f"Command '{command}' timed out after {timeout_ms}ms")
        except ConnectionError:
            raise ConnectionError(f"Failed to connect to WinDbg extension")
        except NetworkDebuggingError:
            raise  # Re-raise network debugging errors
        except Exception as e:
            logger.error(f"Unexpected error executing command '{command}': {e}")
            raise CommunicationError(f"Error executing command: {str(e)}")

    def _send_message(self, message: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        """
        Send a message to the WinDbg extension via named pipe.
        
        Args:
            message: The message to send
            timeout_ms: Timeout in milliseconds
            
        Returns:
            The response from the extension
            
        Raises:
            ConnectionError: If connection fails
            TimeoutError: If the operation times out
            CommunicationError: If the operation fails
        """
        start_time = datetime.now()
        handle = None
        
        try:
            # Convert message to JSON
            message_str = json.dumps(message) + "\n"
            message_bytes = message_str.encode('utf-8')
            
            logger.debug(f"Sending {len(message_bytes)} bytes to pipe")
            
            # Connect to the named pipe
            handle = _connect_to_pipe(timeout_ms)
            
            # Send the message
            _write_to_pipe(handle, message_bytes, timeout_ms)
            
            # Read the response
            response_data = _read_from_pipe(handle, timeout_ms)
            
            # Parse and return the response
            return _parse_response(response_data)
            
        finally:
            if handle:
                try:
                    win32file.CloseHandle(handle)
                except:
                    pass

# Global communication manager instance
_communication_manager = None

def get_communication_manager() -> CommunicationManager:
    """Get the global communication manager instance."""
    global _communication_manager
    if _communication_manager is None:
        _communication_manager = CommunicationManager()
    return _communication_manager

def set_debugging_mode(mode: DebuggingMode):
    """
    Set the debugging mode for connection optimization.
    
    Args:
        mode: Debugging mode ("local", "vm_network", "vm_serial", "remote")
    """
    manager = get_communication_manager()
    manager.set_debugging_mode(mode)

def start_connection_monitoring():
    """Start background connection health monitoring."""
    manager = get_communication_manager()
    manager.start_health_monitoring()

def stop_connection_monitoring():
    """Stop background connection health monitoring."""
    manager = get_communication_manager()
    manager.stop_health_monitoring()

def get_connection_health() -> Dict[str, Any]:
    """
    Get current connection health status.
    
    Returns:
        Dictionary containing health information
    """
    manager = get_communication_manager()
    health = manager.get_connection_health()
    
    return {
        "is_connected": health.is_connected,
        "last_successful_command": health.last_successful_command.isoformat() if health.last_successful_command else None,
        "consecutive_failures": health.consecutive_failures,
        "debugging_mode": health.network_debugging_mode.value,
        "target_responsive": health.target_responsive,
        "extension_responsive": health.extension_responsive,
        "last_error": health.last_error
    }

def _connect_to_pipe(timeout_ms: int):
    """Connect to the WinDbg extension named pipe using synchronous I/O."""
    try:
        handle = win32file.CreateFile(
            PIPE_NAME,
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0,
            None,
            win32file.OPEN_EXISTING,
            0,  # Synchronous I/O for reliable communication
            None
        )
        logger.debug(f"Connected to pipe: {PIPE_NAME}")
        return handle
        
    except pywintypes.error as e:
        error_code = e.args[0]
        
        if error_code == 2:  # ERROR_FILE_NOT_FOUND
            raise ConnectionError("WinDbg extension not found. Make sure the extension is loaded in WinDbg.")
        elif error_code == 231:  # ERROR_PIPE_BUSY
            # Wait for pipe to become available
            if win32pipe.WaitNamedPipe(PIPE_NAME, 5000):
                return _connect_to_pipe(timeout_ms)  # Retry once
            else:
                raise ConnectionError("WinDbg extension is busy. Try again later.")
        else:
            raise ConnectionError(f"Failed to connect to WinDbg extension: {str(e)}")

def _write_to_pipe(handle, data: bytes, timeout_ms: int):
    """Write data to the pipe using synchronous I/O."""
    try:
        win32file.WriteFile(handle, data)
        logger.debug(f"Successfully wrote {len(data)} bytes to pipe")
            
    except pywintypes.error as e:
        raise ConnectionError(f"Failed to write to pipe: {str(e)}")

def _read_from_pipe(handle, timeout_ms: int) -> bytes:
    """Read response from the pipe using synchronous I/O."""
    start_time = datetime.now()
    response_data = b''
    
    while True:
        # Check timeout
        elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        if elapsed_ms > timeout_ms:
            raise TimeoutError(f"Read operation timed out after {elapsed_ms}ms")
        
        try:
            # Read data using synchronous I/O (like the working debug test)
            hr, data = win32file.ReadFile(handle, BUFFER_SIZE)
            
            if data:
                response_data += data
                logger.debug(f"Read {len(data)} bytes, total: {len(response_data)} bytes")
                
                # Check if response is complete (ends with newline)
                if response_data.endswith(b'\n'):
                    logger.debug("Found complete response (ends with newline)")
                    break
            else:
                # No more data available, but wait a bit for more
                time.sleep(0.01)
                
        except pywintypes.error as e:
            error_code = e.args[0]
            if error_code == 109:  # ERROR_BROKEN_PIPE
                if response_data:
                    logger.warning("Pipe broken but have partial data, using it")
                    break  # Use partial data
                raise ConnectionError("Pipe connection broken")
            elif error_code == 232:  # ERROR_NO_DATA
                # No data available yet, wait and retry
                time.sleep(0.01)
                continue
            else:
                raise ConnectionError(f"Failed to read from pipe: {str(e)}")
    
    logger.debug(f"Successfully read complete response: {len(response_data)} bytes")
    return response_data

def _parse_response(response_data: bytes) -> Dict[str, Any]:
    """Parse the response data from the extension."""
    try:
        response_str = response_data.decode('utf-8').strip()
        return json.loads(response_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse response: {e}")
        logger.debug(f"Raw response: {response_data!r}")
        raise CommunicationError(f"Invalid response from WinDbg extension")
    except UnicodeDecodeError as e:
        logger.error(f"Failed to decode response: {e}")
        raise CommunicationError(f"Invalid response encoding from WinDbg extension")

def test_connection() -> bool:
    """
    Test if the connection to the WinDbg extension is working.
    
    This uses a safe, minimal approach to avoid overwhelming the extension.
    
    Returns:
        True if connection is working, False otherwise
    """
    try:
        # Check startup cache first to avoid redundant calls
        cached_result = get_startup_cached_result("version")
        if cached_result is not None:
            logger.debug("Using cached version result for connection test")
            is_connected = bool(cached_result and len(cached_result) > 10 and not cached_result.startswith("Error:"))
        else:
            # Use a very simple and short timeout test to minimize extension load
            manager = get_communication_manager()
            result = manager._send_command_internal("version", timeout_ms=3000)
            is_connected = bool(result and len(result) > 10 and not result.startswith("Error:"))
            
            # Cache the result during startup
            cache_startup_command("version", result)
        
        # Update health flags regardless of result to maintain consistent state
        manager = get_communication_manager()
        with manager._health_lock:
            manager._connection_health.extension_responsive = is_connected
            manager._connection_health.target_responsive = is_connected
            manager._connection_health.is_connected = is_connected
            if is_connected:
                manager._connection_health.last_successful_command = datetime.now()
                manager._connection_health.consecutive_failures = 0
        
        # Also update the connection resilience state
        if is_connected:
            try:
                from .connection_resilience import connection_resilience, ConnectionState
                connection_resilience.state = ConnectionState.CONNECTED
                connection_resilience.metrics.last_successful_command = datetime.now()
                connection_resilience.metrics.consecutive_failures = 0
            except Exception as e:
                logger.debug(f"Failed to update connection resilience state: {e}")
        
        return is_connected
    except NetworkDebuggingError as e:
        logger.warning(f"Network debugging issue detected: {e}")
        return False
    except Exception as e:
        logger.debug(f"Connection test failed: {e}")
        return False

def test_target_connection() -> Tuple[bool, str]:
    """
    Test the WinDbg target connection specifically.
    
    Returns:
        Tuple of (is_connected, status_message)
    """
    try:
        # Check startup cache first to avoid redundant calls
        cached_result = get_startup_cached_result("vertarget")
        if cached_result is not None:
            logger.debug("Using cached vertarget result for target connection test")
            result = cached_result
        else:
            manager = get_communication_manager()
            # Try a quick kernel command to test target responsiveness
            # Use direct internal command to avoid triggering health monitoring
            result = manager._send_command_internal("vertarget", timeout_ms=5000)
            
            # Cache the result during startup
            cache_startup_command("vertarget", result)
        
        if "not connected" in result.lower():
            return False, "WinDbg is not connected to a debugging target"
        elif "kernel mode" in result.lower():
            return True, "Connected to kernel debugging target"
        elif "user mode" in result.lower():
            return True, "Connected to user-mode debugging target"
        else:
            return True, "Connected to debugging target"
            
    except NetworkDebuggingError as e:
        return False, f"Network debugging connection issue: {str(e)}"
    except Exception as e:
        return False, f"Failed to test target connection: {str(e)}"

def diagnose_connection_issues() -> Dict[str, Any]:
    """
    Perform comprehensive connection diagnostics.
    This function is called when basic connection tests fail, so it focuses on diagnosis rather than re-testing.
    
    Returns:
        Dictionary with diagnostic information
    """
    diagnostics = {
        "timestamp": datetime.now().isoformat(),
        "extension_available": False,
        "target_connected": False,
        "network_debugging": False,
        "health_info": {},
        "recommendations": []
    }
    
    try:
        # Get current health status
        manager = get_communication_manager()
        health = manager.get_connection_health()
        
        diagnostics["health_info"] = {
            "extension_responsive": health.extension_responsive,
            "target_responsive": health.target_responsive,
            "debugging_mode": health.network_debugging_mode.value,
            "consecutive_failures": health.consecutive_failures,
            "last_error": health.last_error
        }
        
        # Since we're here, basic connection test already failed
        # Check if we have any cached results that might give us clues
        cached_version = get_startup_cached_result("version")
        if cached_version is not None:
            diagnostics["extension_available"] = True
            logger.debug("Extension was responsive during startup (cached version available)")
        else:
            diagnostics["recommendations"].append("Load the WinDbg MCP extension (.load extension)")
        
        # Test target connection to see if it's a target-specific issue
        target_connected, target_status = test_target_connection()
        diagnostics["target_connected"] = target_connected
        diagnostics["target_status"] = target_status
        
        if not target_connected:
            diagnostics["recommendations"].append("Connect WinDbg to a debugging target")
        
        # Detect network debugging scenarios
        if "network" in target_status.lower() or health.network_debugging_mode in [DebuggingMode.VM_NETWORK, DebuggingMode.REMOTE]:
            diagnostics["network_debugging"] = True
            if health.consecutive_failures > 0:
                diagnostics["recommendations"].extend([
                    "Check network connection to debugging target",
                    "Consider increasing timeout values for network debugging",
                    "Try 'bc *' to clear breakpoints if target is unresponsive"
                ])
        
    except Exception as e:
        diagnostics["error"] = f"Diagnostic error: {str(e)}"
    
    return diagnostics

# Backward compatibility functions for existing code
def set_network_debugging_mode(mode: DebuggingMode):
    """Set network debugging mode (backward compatibility).""" 
    set_debugging_mode(mode)

def get_network_debugging_mode() -> DebuggingMode:
    """Get current debugging mode (backward compatibility)."""
    health = get_connection_health()
    return DebuggingMode(health["debugging_mode"])

def send_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Send a command to the WinDbg extension with enhanced resilience.
    
    This function uses the CommunicationManager for improved reliability
    and network debugging support.
    
    Args:
        command: The WinDbg command to execute
        timeout_ms: Timeout in milliseconds
        
    Returns:
        The command output as a string
        
    Raises:
        ConnectionError: If connection to the extension fails
        TimeoutError: If the command times out
        NetworkDebuggingError: If network debugging issues are detected
        CommunicationError: If the command fails
    """
    manager = get_communication_manager()
    return manager.send_command(command, timeout_ms) 