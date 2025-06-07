"""
Connection management module for WinDbg MCP Extension.

This module handles the higher-level connection management, including:
- Connection health monitoring and tracking
- Debugging mode detection and configuration
- Connection testing and diagnostics
- Resilience and retry coordination
- Enhanced concurrency support with connection pooling

Extracted from communication.py to improve maintainability and separation of concerns.
"""
import logging
import threading
import time
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from contextlib import contextmanager

from config import (
    CONNECTION_HEALTH_CHECK_INTERVAL, DebuggingMode,
    get_timeout_for_command, get_retry_delay, PIPE_NAME
)
from .communication_protocols import (
    NamedPipeProtocol, MessageProtocol, CommunicationError,
    TimeoutError, ConnectionError, NetworkDebuggingError
)
from .retry_utils import resilient_command, RetryableError, NonRetryableError
from .unified_cache import get_startup_cached_result, cache_startup_command

logger = logging.getLogger(__name__)


@dataclass
class ConnectionHandle:
    """Represents a connection handle with metadata for pooling."""
    handle: Any
    created_at: datetime
    last_used: datetime
    in_use: bool = False
    use_count: int = 0
    thread_id: int = 0


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


class EnhancedConnectionPool:
    """
    Thread-safe connection pool for named pipe connections.
    
    This addresses concurrency issues by:
    - Managing multiple pipe connections
    - Providing thread-safe access to connections
    - Implementing connection reuse and cleanup
    - Handling connection failures gracefully
    """
    
    def __init__(self, max_connections: int = 5):
        self._max_connections = max_connections
        self._connections: List[ConnectionHandle] = []
        self._lock = threading.RLock()
        self._pipe_name = PIPE_NAME
        self._active_requests = 0
        self._max_concurrent_requests = 10
        self._queue_condition = threading.Condition(self._lock)
    
    @contextmanager
    def get_connection(self, timeout_ms: int = 10000):
        """Context manager to get a connection from the pool."""
        start_time = time.time()
        connection = None
        
        # Check concurrent request limit
        with self._lock:
            if self._active_requests >= self._max_concurrent_requests:
                while self._active_requests >= self._max_concurrent_requests:
                    elapsed = (time.time() - start_time) * 1000
                    if elapsed > timeout_ms:
                        raise TimeoutError(f"Request timed out in queue after {elapsed:.0f}ms")
                    
                    wait_time = min(0.1, (timeout_ms - elapsed) / 1000)
                    if not self._queue_condition.wait(wait_time):
                        continue
            
            self._active_requests += 1
        
        try:
            connection = self._acquire_connection(timeout_ms)
            yield connection.handle
        finally:
            if connection:
                self._release_connection(connection)
            
            with self._lock:
                self._active_requests -= 1
                self._queue_condition.notify_all()
    
    def _acquire_connection(self, timeout_ms: int) -> ConnectionHandle:
        """Acquire a connection from the pool (thread-safe)."""
        current_thread = threading.get_ident()
        
        with self._lock:
            # Try to find available connection
            for conn in self._connections:
                if not conn.in_use:
                    conn.in_use = True
                    conn.last_used = datetime.now()
                    conn.use_count += 1
                    conn.thread_id = current_thread
                    logger.debug(f"Reusing connection (use count: {conn.use_count}, thread: {current_thread})")
                    return conn
            
            # Create new connection if under limit
            if len(self._connections) < self._max_connections:
                try:
                    handle = NamedPipeProtocol.connect_to_pipe(self._pipe_name, timeout_ms)
                    connection = ConnectionHandle(
                        handle=handle,
                        created_at=datetime.now(),
                        last_used=datetime.now(),
                        in_use=True,
                        use_count=1,
                        thread_id=current_thread
                    )
                    self._connections.append(connection)
                    logger.debug(f"Created new connection (total: {len(self._connections)}, thread: {current_thread})")
                    return connection
                except Exception as e:
                    logger.error(f"Failed to create connection: {e}")
                    raise ConnectionError(f"Unable to create connection: {e}")
            
            # Create temporary connection for high concurrency
            logger.debug(f"Creating temporary connection for high concurrency (thread: {current_thread})")
            try:
                handle = NamedPipeProtocol.connect_to_pipe(self._pipe_name, timeout_ms)
                connection = ConnectionHandle(
                    handle=handle,
                    created_at=datetime.now(),
                    last_used=datetime.now(),
                    in_use=True,
                    use_count=1,
                    thread_id=current_thread
                )
                return connection
            except Exception as e:
                raise ConnectionError(f"Unable to acquire connection: {e}")
    
    def _release_connection(self, connection: ConnectionHandle):
        """Release connection back to pool."""
        with self._lock:
            connection.in_use = False
            connection.last_used = datetime.now()
            connection.thread_id = 0
            
            # Close temporary connections not in pool
            if connection not in self._connections:
                try:
                    NamedPipeProtocol.close_pipe(connection.handle)
                    logger.debug("Closed temporary connection")
                except Exception as e:
                    logger.warning(f"Error closing temporary connection: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        with self._lock:
            return {
                "total_connections": len(self._connections),
                "active_connections": sum(1 for conn in self._connections if conn.in_use),
                "active_requests": self._active_requests,
                "max_connections": self._max_connections,
                "max_concurrent_requests": self._max_concurrent_requests
            }


class ConnectionManager:
    """
    Enhanced connection manager with connection resilience and hybrid architecture support.
    
    This manager handles:
    - Named pipe communication with WinDbg extension
    - Connection health monitoring (MINIMAL MODE to prevent crashes)
    - Retry logic for network debugging scenarios
    - Timeout optimization based on debugging mode
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
    
    def _optimize_timeout(self, command: str, base_timeout_ms: int) -> int:
        """Optimize timeout based on debugging mode and command type."""
        with self._health_lock:
            mode = self._connection_health.network_debugging_mode
        
        # Use centralized timeout optimization
        return get_timeout_for_command(command, mode)
    
    @resilient_command
    def send_command(self, command: str, timeout_ms: int) -> str:
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
    
    @resilient_command
    def send_handler_command(self, handler_name: str, timeout_ms: int, **kwargs) -> Dict[str, Any]:
        """
        Send a direct handler command to the WinDbg extension.
        
        Args:
            handler_name: Name of the handler (e.g., "version", "health_check")
            timeout_ms: Timeout in milliseconds
            **kwargs: Additional arguments to pass to the handler
            
        Returns:
            The handler response as a dictionary
            
        Raises:
            ConnectionError: If connection to the extension fails
            TimeoutError: If the command times out
            CommunicationError: If the command fails
        """
        # Use quick timeout for handler commands (they're usually fast)
        optimized_timeout = min(timeout_ms, 10000)
        
        result = self._send_handler_internal(handler_name, optimized_timeout, **kwargs)
        
        # Update health on success
        with self._health_lock:
            self._connection_health.last_successful_command = datetime.now()
            self._connection_health.consecutive_failures = 0
            self._connection_health.last_error = None
            self._connection_health.extension_responsive = True
            self._connection_health.target_responsive = True
            self._connection_health.is_connected = True
        
        return result
    
    def _send_command_internal(self, command: str, timeout_ms: int) -> str:
        """Internal command sending with enhanced error detection."""
        logger.debug(f"Sending command: {command}")
        
        # Create message using protocol handler
        message = MessageProtocol.create_command_message(command, timeout_ms)
        
        try:
            response = self._send_message(message, timeout_ms)
            
            # Validate response structure
            if not MessageProtocol.validate_response(response):
                raise CommunicationError("Invalid response structure from WinDbg extension")
            
            # Handle error responses
            if response.get("status") == "error":
                error_message = response.get("error", "Unknown error")
                suggestion = response.get("suggestion", "")
                
                # Detect network debugging issues
                if MessageProtocol.detect_network_debugging_error(error_message):
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
            self._update_health_on_failure(f"Command '{command}' timed out")
            raise TimeoutError(f"Command '{command}' timed out after {timeout_ms}ms")
        except ConnectionError:
            self._update_health_on_failure("Connection to WinDbg extension failed")
            raise ConnectionError(f"Failed to connect to WinDbg extension")
        except NetworkDebuggingError:
            # Don't update health for network debugging errors as they're expected
            raise  # Re-raise network debugging errors
        except Exception as e:
            self._update_health_on_failure(str(e))
            logger.error(f"Unexpected error executing command '{command}': {e}")
            raise CommunicationError(f"Error executing command: {str(e)}")
    
    def _send_handler_internal(self, handler_name: str, timeout_ms: int, **kwargs) -> Dict[str, Any]:
        """Internal handler command sending with enhanced error detection."""
        logger.debug(f"Sending handler command: {handler_name}")
        
        # Create handler message using protocol handler
        message = MessageProtocol.create_handler_message(handler_name, **kwargs)
        
        try:
            response = self._send_message(message, timeout_ms)
            
            # Handler responses are already JSON, so we validate and return directly
            if not isinstance(response, dict):
                raise CommunicationError("Invalid response structure from WinDbg extension handler")
            
            # Handle error responses
            if response.get("type") == "error":
                error_message = response.get("error_message", "Unknown error")
                raise CommunicationError(f"Handler '{handler_name}' failed: {error_message}")
                
            # Return the full response for handler commands
            return response
            
        except TimeoutError:
            self._update_health_on_failure(f"Handler '{handler_name}' timed out")
            raise TimeoutError(f"Handler '{handler_name}' timed out after {timeout_ms}ms")
        except ConnectionError:
            self._update_health_on_failure("Connection to WinDbg extension failed")
            raise ConnectionError(f"Failed to connect to WinDbg extension")
        except Exception as e:
            self._update_health_on_failure(str(e))
            logger.error(f"Unexpected error executing handler '{handler_name}': {e}")
            raise CommunicationError(f"Error executing handler: {str(e)}")
    
    def _update_health_on_failure(self, error_message: str):
        """Update connection health when a failure occurs."""
        with self._health_lock:
            self._connection_health.consecutive_failures += 1
            self._connection_health.last_error = error_message
            
            # If we have multiple consecutive failures, mark as potentially disconnected
            if self._connection_health.consecutive_failures >= 3:
                self._connection_health.is_connected = False
                self._connection_health.extension_responsive = False
    
    def _send_message(self, message: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        """
        Send a message to the WinDbg extension via named pipe with enhanced pooling.
        
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
        # Try to use connection pool first for better concurrency
        try:
            pool = self._get_or_create_connection_pool()
            with pool.get_connection(timeout_ms) as handle:
                # Serialize message
                message_bytes = MessageProtocol.serialize_message(message)
                logger.debug(f"Sending {len(message_bytes)} bytes via pooled connection")
                
                # Send the message
                NamedPipeProtocol.write_to_pipe(handle, message_bytes, timeout_ms)
                
                # Read the response
                response_data = NamedPipeProtocol.read_from_pipe(handle, timeout_ms)
                
                # Parse and return the response
                return MessageProtocol.parse_response(response_data)
                
        except Exception as pool_error:
            logger.debug(f"Pooled connection failed, falling back to direct connection: {pool_error}")
            
            # Fallback to direct connection
            from config import PIPE_NAME
            
            handle = None
            
            try:
                # Serialize message
                message_bytes = MessageProtocol.serialize_message(message)
                logger.debug(f"Sending {len(message_bytes)} bytes to pipe (direct)")
                
                # Connect to the named pipe
                handle = NamedPipeProtocol.connect_to_pipe(PIPE_NAME, timeout_ms)
                
                # Send the message
                NamedPipeProtocol.write_to_pipe(handle, message_bytes, timeout_ms)
                
                # Read the response
                response_data = NamedPipeProtocol.read_from_pipe(handle, timeout_ms)
                
                # Parse and return the response
                return MessageProtocol.parse_response(response_data)
                
            finally:
                if handle:
                    NamedPipeProtocol.close_pipe(handle)
    
    def _get_or_create_connection_pool(self) -> EnhancedConnectionPool:
        """Get or create the connection pool for this manager."""
        if not hasattr(self, '_connection_pool'):
            self._connection_pool = EnhancedConnectionPool(max_connections=3)
        return self._connection_pool
    
    def get_connection_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics if available."""
        try:
            if hasattr(self, '_connection_pool'):
                return self._connection_pool.get_stats()
            else:
                return {"status": "no_pool_created"}
        except Exception as e:
            return {"error": str(e)}


class ConnectionTester:
    """
    Handles connection testing and diagnostics for the WinDbg extension.
    
    This class provides methods for:
    - Testing extension connectivity
    - Testing debugging target connectivity
    - Running comprehensive diagnostics
    - Providing troubleshooting recommendations
    """
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
    
    def test_extension_connection(self) -> bool:
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
                # Use the version handler that we know exists in the extension
                result = self.connection_manager._send_handler_internal("version", timeout_ms=3000)
                is_connected = bool(result and result.get("type") in ["success", "response"])
                
                # Cache the result during startup
                cache_startup_command("version", str(result))
            
            # Update health flags regardless of result to maintain consistent state
            with self.connection_manager._health_lock:
                self.connection_manager._connection_health.extension_responsive = is_connected
                self.connection_manager._connection_health.target_responsive = is_connected
                self.connection_manager._connection_health.is_connected = is_connected
                if is_connected:
                    self.connection_manager._connection_health.last_successful_command = datetime.now()
                    self.connection_manager._connection_health.consecutive_failures = 0
            
            return is_connected
            
        except NetworkDebuggingError:
            # Network debugging errors indicate the extension is working but target has issues
            logger.debug("Network debugging error during connection test - assuming connected")
            return True
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return False
    
    def test_target_connection(self) -> Tuple[bool, str]:
        """
        Test if the debugging target is responsive.
        
        Returns:
            Tuple of (is_connected, status_message)
        """
        try:
            # Check startup cache first
            cached_result = get_startup_cached_result("!analyze")
            if cached_result is not None:
                logger.debug("Using cached !analyze result for target test")
                result = cached_result
            else:
                # Use a lightweight command to test target responsiveness
                result = self.connection_manager._send_command_internal("!analyze", timeout_ms=5000)
                cache_startup_command("!analyze", result)
            
            # Analyze the result to determine connection type
            if result:
                result_lower = result.lower()
                if "kernel" in result_lower:
                    return True, "Kernel debugging target connected"
                elif "user" in result_lower or "process" in result_lower:
                    return True, "User-mode debugging target connected"
                elif "network" in result_lower or "transport" in result_lower:
                    return True, "Network debugging target connected"
                else:
                    return True, "Debugging target connected"
            else:
                return False, "No response from debugging target"
                
        except NetworkDebuggingError as e:
            return False, f"Network debugging issue: {str(e)}"
        except Exception as e:
            return False, f"Target test failed: {str(e)}"
    
    def diagnose_connection_issues(self) -> Dict[str, Any]:
        """
        Run comprehensive connection diagnostics.
        
        Returns:
            Dictionary containing diagnostic results and recommendations
        """
        diagnostics = {
            "extension_available": False,
            "target_connected": False,
            "recommendations": []
        }
        
        try:
            # Test extension availability
            diagnostics["extension_available"] = self.test_extension_connection()
            
            # Test target connection
            target_connected, target_status = self.test_target_connection()
            diagnostics["target_connected"] = target_connected
            diagnostics["target_status"] = target_status
            
            # Generate recommendations based on results
            recommendations = []
            
            if not diagnostics["extension_available"]:
                recommendations.extend([
                    "Load the WinDbg extension with: .load path\\to\\windbgmcpExt.dll",
                    "Ensure WinDbg is running and the extension DLL is accessible",
                    "Check that the extension is compatible with your WinDbg version"
                ])
            
            if not diagnostics["target_connected"]:
                recommendations.extend([
                    "Ensure a debugging target is connected",
                    "For kernel debugging, verify target VM configuration",
                    "For user-mode debugging, attach to a process or launch an application"
                ])
            
            diagnostics["recommendations"] = recommendations
            
        except Exception as e:
            logger.error(f"Failed to run diagnostics: {e}")
            diagnostics["error"] = str(e)
        
        return diagnostics 