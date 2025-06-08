"""
Core communication module for WinDbg MCP Extension.

This module provides all communication functionality including low-level protocols,
connection management, error handling, and diagnostic capabilities.
"""
import json
import time
import logging
import threading
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass
from contextlib import contextmanager
from enum import Enum
import win32pipe
import win32file
import win32api
import win32event
import pywintypes

from config import PIPE_NAME, BUFFER_SIZE, DEFAULT_TIMEOUT_MS, DebuggingMode, get_timeout_for_command

logger = logging.getLogger(__name__)


# Exception Classes
class CommunicationError(Exception):
    """Base exception for communication errors."""
    pass


class PipeTimeoutError(CommunicationError):
    """Raised when a command times out."""
    pass


# Backward compatibility alias
TimeoutError = PipeTimeoutError


class ConnectionError(CommunicationError):
    """Raised when connection to WinDbg extension fails."""
    pass


class NetworkDebuggingError(CommunicationError):
    """Raised when network debugging connection issues are detected."""
    pass


# Data Classes
@dataclass
class ConnectionHandle:
    """Represents a connection handle with metadata."""
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
    target_responsive: bool
    extension_responsive: bool
    last_error: Optional[str]


# Low-level Protocol Classes
class NamedPipeProtocol:
    """Handles low-level named pipe communication protocol."""
    
    @staticmethod
    def connect_to_pipe(pipe_name: str, timeout_ms: int) -> Any:
        """
        Connect to the WinDbg extension named pipe.
        
        Args:
            pipe_name: Name of the pipe to connect to
            timeout_ms: Connection timeout in milliseconds
            
        Returns:
            Handle to the connected pipe
            
        Raises:
            ConnectionError: If connection fails
        """
        try:
            handle = win32file.CreateFile(
                pipe_name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None
            )
            logger.debug(f"Connected to pipe: {pipe_name}")
            return handle
            
        except pywintypes.error as e:
            error_code = e.args[0]
            
            if error_code == 2:  # ERROR_FILE_NOT_FOUND
                raise ConnectionError("WinDbg extension not found. Make sure the extension is loaded in WinDbg.")
            elif error_code == 231:  # ERROR_PIPE_BUSY
                # Wait for pipe to become available
                start_time = time.time()
                while (time.time() - start_time) * 1000 < timeout_ms:
                    if win32pipe.WaitNamedPipe(pipe_name, min(5000, timeout_ms)):
                        try:
                            handle = win32file.CreateFile(
                                pipe_name,
                                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                0,
                                None,
                                win32file.OPEN_EXISTING,
                                0,
                                None
                            )
                            logger.debug(f"Connected to pipe after waiting: {pipe_name}")
                            return handle
                        except pywintypes.error as retry_error:
                            if retry_error.args[0] != 231:
                                raise ConnectionError(f"Failed to connect after wait: {str(retry_error)}")
                            time.sleep(0.1)
                    else:
                        time.sleep(0.1)
                
                raise ConnectionError("WinDbg extension is busy and timeout exceeded.")
            else:
                raise ConnectionError(f"Failed to connect to WinDbg extension: {str(e)}")
    
    @staticmethod
    def write_to_pipe(handle: Any, data: bytes, timeout_ms: int):
        """Write data to the pipe."""
        try:
            win32file.WriteFile(handle, data)
            logger.debug(f"Successfully wrote {len(data)} bytes to pipe")
        except pywintypes.error as e:
            raise ConnectionError(f"Failed to write to pipe: {str(e)}")
    
    @staticmethod
    def read_from_pipe(handle: Any, timeout_ms: int) -> bytes:
        """Read response from the pipe."""
        start_time = datetime.now()
        response_data = b''
        
        while True:
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            if elapsed_ms > timeout_ms:
                raise TimeoutError(f"Read operation timed out after {elapsed_ms}ms")
            
            try:
                hr, data = win32file.ReadFile(handle, BUFFER_SIZE)
                
                if data:
                    response_data += data
                    logger.debug(f"Read {len(data)} bytes, total: {len(response_data)} bytes")
                    
                    if response_data.endswith(b'\n'):
                        logger.debug("Found complete response")
                        break
                else:
                    time.sleep(0.01)
                    
            except pywintypes.error as e:
                error_code = e.args[0]
                if error_code == 109:  # ERROR_BROKEN_PIPE
                    if response_data:
                        logger.warning("Pipe broken but have partial data, using it")
                        break
                    raise ConnectionError("Pipe connection broken")
                elif error_code == 232:  # ERROR_NO_DATA
                    time.sleep(0.01)
                    continue
                else:
                    raise ConnectionError(f"Failed to read from pipe: {str(e)}")
        
        logger.debug(f"Successfully read complete response: {len(response_data)} bytes")
        return response_data
    
    @staticmethod
    def close_pipe(handle: Any):
        """Safely close a pipe handle."""
        if handle:
            try:
                win32file.CloseHandle(handle)
            except Exception as e:
                logger.warning(f"Error closing pipe handle: {e}")


class MessageProtocol:
    """Handles message-level protocol for MCP communication."""
    
    @staticmethod
    def create_command_message(command: str, timeout_ms: int) -> Dict[str, Any]:
        """Create a command message for the WinDbg extension."""
        return {
            "type": "command",
            "command": "execute_command",
            "id": int(time.time() * 1000),
            "args": {
                "command": command,
                "timeout_ms": timeout_ms
            }
        }
    
    @staticmethod
    def create_handler_message(handler_name: str, **kwargs) -> Dict[str, Any]:
        """Create a direct handler message for the WinDbg extension."""
        message = {
            "type": "command",
            "command": handler_name,
            "id": int(time.time() * 1000)
        }
        
        if kwargs:
            message["args"] = kwargs
            
        return message
    
    @staticmethod
    def serialize_message(message: Dict[str, Any]) -> bytes:
        """Serialize a message to bytes for transmission."""
        try:
            message_str = json.dumps(message) + "\n"
            return message_str.encode('utf-8')
        except (TypeError, ValueError) as e:
            raise CommunicationError(f"Failed to serialize message: {e}")
    
    @staticmethod
    def parse_response(response_data: bytes) -> Dict[str, Any]:
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
    
    @staticmethod
    def validate_response(response: Dict[str, Any]) -> bool:
        """Validate that a response message has the expected structure."""
        try:
            if "status" not in response:
                return False
            
            status = response.get("status")
            if status not in ["success", "error"]:
                return False
            
            if status == "error" and "error" not in response:
                return False
            
            if status == "success" and "output" not in response:
                return False
            
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def detect_network_debugging_error(error_message: str) -> bool:
        """Detect if an error message indicates network debugging issues."""
        network_error_indicators = [
            "retry sending", "transport connection", "lost", "network",
            "target windows seems lost", "resync with target"
        ]
        
        return any(phrase in error_message.lower() for phrase in network_error_indicators)


# Connection Pool Management
class ConnectionPool:
    """Thread-safe connection pool for named pipe connections."""
    
    def __init__(self, max_connections: int = 3):
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
        """Acquire a connection from the pool."""
        current_thread = threading.get_ident()
        
        with self._lock:
            for conn in self._connections:
                if not conn.in_use:
                    conn.in_use = True
                    conn.last_used = datetime.now()
                    conn.use_count += 1
                    conn.thread_id = current_thread
                    logger.debug(f"Reusing connection (use count: {conn.use_count})")
                    return conn
            
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
                    logger.debug(f"Created new connection (total: {len(self._connections)})")
                    return connection
                except Exception as e:
                    logger.error(f"Failed to create connection: {e}")
                    raise ConnectionError(f"Unable to create connection: {e}")
            
            # Create temporary connection for high concurrency
            logger.debug("Creating temporary connection for high concurrency")
            try:
                handle = NamedPipeProtocol.connect_to_pipe(self._pipe_name, timeout_ms)
                return ConnectionHandle(
                    handle=handle,
                    created_at=datetime.now(),
                    last_used=datetime.now(),
                    in_use=True,
                    use_count=1,
                    thread_id=current_thread
                )
            except Exception as e:
                raise ConnectionError(f"Unable to acquire connection: {e}")
    
    def _release_connection(self, connection: ConnectionHandle):
        """Release connection back to pool."""
        with self._lock:
            connection.in_use = False
            connection.last_used = datetime.now()
            connection.thread_id = 0
            
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
                "max_connections": self._max_connections
            }


# High-level Communication Manager
class CommunicationManager:
    """Main communication manager for WinDbg extension interaction."""
    
    def __init__(self):
        self._connection_health = ConnectionHealth(
            is_connected=True,
            last_successful_command=None,
            consecutive_failures=0,
            target_responsive=True,
            extension_responsive=True,
            last_error=None
        )
        self._health_lock = threading.Lock()
        self._connection_pool = ConnectionPool()
    
    def send_command(self, command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
        """Send a command to the WinDbg extension."""
        logger.debug(f"Sending command: {command}")
        
        message = MessageProtocol.create_command_message(command, timeout_ms)
        
        try:
            response = self._send_message(message, timeout_ms)
            
            if not MessageProtocol.validate_response(response):
                raise CommunicationError("Invalid response structure from WinDbg extension")
            
            if response.get("status") == "error":
                error_message = response.get("error", "Unknown error")
                
                if MessageProtocol.detect_network_debugging_error(error_message):
                    raise NetworkDebuggingError(f"Network debugging connection issue: {error_message}")
                
                raise CommunicationError(f"WinDbg command failed: {error_message}")
                
            self._update_health_on_success()
            return response.get("output", "")
            
        except (TimeoutError, ConnectionError, NetworkDebuggingError):
            self._update_health_on_failure(f"Command '{command}' failed")
            raise
        except Exception as e:
            self._update_health_on_failure(str(e))
            logger.error(f"Unexpected error executing command '{command}': {e}")
            raise CommunicationError(f"Error executing command: {str(e)}")
    
    def send_handler_command(self, handler_name: str, timeout_ms: int = DEFAULT_TIMEOUT_MS, **kwargs) -> Dict[str, Any]:
        """Send a direct handler command to the WinDbg extension."""
        logger.debug(f"Sending handler command: {handler_name}")
        
        message = MessageProtocol.create_handler_message(handler_name, **kwargs)
        
        try:
            response = self._send_message(message, timeout_ms)
            
            if not isinstance(response, dict):
                raise CommunicationError("Invalid response structure from WinDbg extension handler")
            
            if response.get("type") == "error":
                error_message = response.get("error_message", "Unknown error")
                raise CommunicationError(f"Handler '{handler_name}' failed: {error_message}")
                
            self._update_health_on_success()
            return response
            
        except (TimeoutError, ConnectionError):
            self._update_health_on_failure(f"Handler '{handler_name}' failed")
            raise
        except Exception as e:
            self._update_health_on_failure(str(e))
            logger.error(f"Unexpected error executing handler '{handler_name}': {e}")
            raise CommunicationError(f"Error executing handler: {str(e)}")
    
    def test_connection(self) -> bool:
        """Test if the connection to the WinDbg extension is working."""
        try:
            result = self.send_handler_command("version", timeout_ms=get_timeout_for_command("version"))
            extension_responsive = bool(result.get("status") == "success")
            
            with self._health_lock:
                self._connection_health.extension_responsive = extension_responsive
                self._connection_health.is_connected = extension_responsive
                if extension_responsive:
                    self._connection_health.last_successful_command = datetime.now()
                    self._connection_health.consecutive_failures = 0
                    self._connection_health.last_error = None
                else:
                    self._connection_health.consecutive_failures += 1
            
            return extension_responsive
            
        except NetworkDebuggingError:
            logger.debug("Network debugging error during connection test - assuming connected")
            with self._health_lock:
                self._connection_health.extension_responsive = True
                self._connection_health.is_connected = True
                self._connection_health.last_successful_command = datetime.now()
                self._connection_health.consecutive_failures = 0
                self._connection_health.last_error = None
            return True
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            with self._health_lock:
                self._connection_health.extension_responsive = False
                self._connection_health.is_connected = False
                self._connection_health.consecutive_failures += 1
                self._connection_health.last_error = str(e)
            return False
    
    def test_target_connection(self) -> Tuple[bool, str]:
        """Test if the debugging target is responsive."""
        try:
            result = self.send_command("version", timeout_ms=get_timeout_for_command("version"))
            target_responsive = bool(result and not result.startswith("Error:"))
            
            with self._health_lock:
                self._connection_health.target_responsive = target_responsive
            
            if target_responsive:
                if "kernel" in result.lower():
                    return True, "Kernel debugging target connected"
                elif "user" in result.lower() or "process" in result.lower():
                    return True, "User-mode debugging target connected"
                else:
                    return True, "Debugging target connected"
            else:
                return False, "No response from debugging target"
                
        except NetworkDebuggingError as e:
            with self._health_lock:
                self._connection_health.target_responsive = False
            return False, f"Network debugging issue: {str(e)}"
        except Exception as e:
            with self._health_lock:
                self._connection_health.target_responsive = False
            return False, f"Target test failed: {str(e)}"
    
    def diagnose_connection_issues(self) -> Dict[str, Any]:
        """Run comprehensive connection diagnostics."""
        diagnostics = {
            "extension_available": False,
            "target_connected": False,
            "recommendations": []
        }
        
        try:
            diagnostics["extension_available"] = self.test_connection()
            
            target_connected, target_status = self.test_target_connection()
            diagnostics["target_connected"] = target_connected
            diagnostics["target_status"] = target_status
            
            recommendations = []
            
            if not diagnostics["extension_available"]:
                recommendations.extend([
                    "Load the WinDbg extension with: .load path\\to\\windbgmcpExt.dll",
                    "Ensure WinDbg is running and the extension DLL is accessible"
                ])
            
            if not diagnostics["target_connected"]:
                recommendations.extend([
                    "Ensure a debugging target is connected",
                    "For kernel debugging, verify target VM configuration"
                ])
            
            diagnostics["recommendations"] = recommendations
            
        except Exception as e:
            logger.error(f"Failed to run diagnostics: {e}")
            diagnostics["error"] = str(e)
        
        return diagnostics
    
    def get_connection_health(self) -> ConnectionHealth:
        """Get the current connection health status."""
        with self._health_lock:
            return self._connection_health
    
    def get_connection_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        return self._connection_pool.get_stats()
    
    def _send_message(self, message: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        """Send a message to the WinDbg extension via named pipe."""
        try:
            with self._connection_pool.get_connection(timeout_ms) as handle:
                message_bytes = MessageProtocol.serialize_message(message)
                logger.debug(f"Sending {len(message_bytes)} bytes via pooled connection")
                
                NamedPipeProtocol.write_to_pipe(handle, message_bytes, timeout_ms)
                response_data = NamedPipeProtocol.read_from_pipe(handle, timeout_ms)
                
                return MessageProtocol.parse_response(response_data)
                
        except Exception as pool_error:
            logger.debug(f"Pooled connection failed, falling back to direct connection: {pool_error}")
            
            handle = None
            try:
                message_bytes = MessageProtocol.serialize_message(message)
                handle = NamedPipeProtocol.connect_to_pipe(PIPE_NAME, timeout_ms)
                
                NamedPipeProtocol.write_to_pipe(handle, message_bytes, timeout_ms)
                response_data = NamedPipeProtocol.read_from_pipe(handle, timeout_ms)
                
                return MessageProtocol.parse_response(response_data)
                
            finally:
                if handle:
                    NamedPipeProtocol.close_pipe(handle)
    
    def _update_health_on_success(self):
        """Update connection health when a command succeeds."""
        with self._health_lock:
            self._connection_health.last_successful_command = datetime.now()
            self._connection_health.consecutive_failures = 0
            self._connection_health.last_error = None
            self._connection_health.extension_responsive = True
            self._connection_health.target_responsive = True
            self._connection_health.is_connected = True
    
    def _update_health_on_failure(self, error_message: str):
        """Update connection health when a failure occurs."""
        with self._health_lock:
            self._connection_health.consecutive_failures += 1
            self._connection_health.last_error = error_message
            
            if self._connection_health.consecutive_failures >= 3:
                self._connection_health.is_connected = False
                self._connection_health.extension_responsive = False


# Global Communication Manager Instance
_communication_manager: Optional[CommunicationManager] = None
_manager_lock = threading.Lock()

def _get_communication_manager() -> CommunicationManager:
    """Get the global communication manager instance."""
    global _communication_manager
    with _manager_lock:
        if _communication_manager is None:
            _communication_manager = CommunicationManager()
        return _communication_manager


# Public API Functions
def send_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Send a command to the WinDbg extension.
    
    Args:
        command: The WinDbg command to execute
        timeout_ms: Timeout in milliseconds
        
    Returns:
        The command output as a string
        
    Raises:
        ConnectionError: If connection to the extension fails
        TimeoutError: If the command times out
        CommunicationError: If the command fails
    """
    manager = _get_communication_manager()
    return manager.send_command(command, timeout_ms)


def send_handler_command(handler_name: str, timeout_ms: int = DEFAULT_TIMEOUT_MS, **kwargs) -> Dict[str, Any]:
    """
    Send a direct handler command to the WinDbg extension.
    
    Args:
        handler_name: Name of the handler
        timeout_ms: Timeout in milliseconds
        **kwargs: Additional arguments
        
    Returns:
        The handler response as a dictionary
    """
    manager = _get_communication_manager()
    return manager.send_handler_command(handler_name, timeout_ms, **kwargs)


def test_connection() -> bool:
    """
    Test if the connection to the WinDbg extension is working.
    
    Returns:
        True if connection is working, False otherwise
    """
    manager = _get_communication_manager()
    return manager.test_connection()


def test_target_connection() -> Tuple[bool, str]:
    """
    Test if the debugging target is responsive.
    
    Returns:
        Tuple of (is_connected, status_message)
    """
    manager = _get_communication_manager()
    return manager.test_target_connection()


def diagnose_connection_issues() -> Dict[str, Any]:
    """
    Run comprehensive connection diagnostics.
    
    Returns:
        Dictionary containing diagnostic results and recommendations
    """
    manager = _get_communication_manager()
    return manager.diagnose_connection_issues() 