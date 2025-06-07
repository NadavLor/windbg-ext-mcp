"""
Communication protocols module for WinDbg MCP Extension.

This module handles the low-level named pipe communication protocols and message
formatting. It's responsible for:
- Named pipe connection management
- Message serialization/deserialization
- Protocol-level error handling
- Raw data transmission

Extracted from communication.py to improve maintainability and separation of concerns.
"""
import json
import time
import logging
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
from contextlib import contextmanager
import win32pipe
import win32file
import win32api
import win32event
import pywintypes

from config import PIPE_NAME, BUFFER_SIZE

logger = logging.getLogger(__name__)


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


@dataclass
class ConnectionHandle:
    """Represents a connection handle with metadata."""
    handle: Any
    created_at: datetime
    last_used: datetime
    in_use: bool = False
    use_count: int = 0


class ConnectionPool:
    """
    Thread-safe connection pool for named pipe connections.
    
    This addresses concurrency issues by:
    - Managing multiple pipe connections
    - Providing thread-safe access to connections
    - Implementing connection reuse and cleanup
    - Handling connection failures gracefully
    """
    
    def __init__(self, max_connections: int = 3):
        self._max_connections = max_connections
        self._connections: List[ConnectionHandle] = []
        self._lock = threading.RLock()  # Reentrant lock for nested access
        self._pipe_name = PIPE_NAME
    
    @contextmanager
    def get_connection(self, timeout_ms: int = 10000):
        """
        Context manager to get a connection from the pool.
        
        Args:
            timeout_ms: Connection timeout in milliseconds
            
        Yields:
            Connection handle for use
            
        Raises:
            ConnectionError: If unable to get a connection
        """
        connection = None
        try:
            connection = self._acquire_connection(timeout_ms)
            yield connection.handle
        finally:
            if connection:
                self._release_connection(connection)
    
    def _acquire_connection(self, timeout_ms: int) -> ConnectionHandle:
        """
        Acquire a connection from the pool (thread-safe).
        
        Args:
            timeout_ms: Connection timeout in milliseconds
            
        Returns:
            ConnectionHandle object
            
        Raises:
            ConnectionError: If unable to acquire a connection
        """
        with self._lock:
            # Try to find an available existing connection
            for conn in self._connections:
                if not conn.in_use:
                    conn.in_use = True
                    conn.last_used = datetime.now()
                    conn.use_count += 1
                    logger.debug(f"Reusing existing connection (use count: {conn.use_count})")
                    return conn
            
            # If we haven't reached max connections, create a new one
            if len(self._connections) < self._max_connections:
                try:
                    handle = NamedPipeProtocol.connect_to_pipe(self._pipe_name, timeout_ms)
                    connection = ConnectionHandle(
                        handle=handle,
                        created_at=datetime.now(),
                        last_used=datetime.now(),
                        in_use=True,
                        use_count=1
                    )
                    self._connections.append(connection)
                    logger.debug(f"Created new connection (total: {len(self._connections)})")
                    return connection
                except Exception as e:
                    logger.error(f"Failed to create new connection: {e}")
                    raise ConnectionError(f"Unable to create connection: {e}")
            
            # All connections are in use, wait for one to become available
            logger.warning("All connections in use, waiting for availability...")
            # For simplicity, we'll create a new connection anyway if needed
            # In production, you might want to implement a proper wait mechanism
            try:
                handle = NamedPipeProtocol.connect_to_pipe(self._pipe_name, timeout_ms)
                connection = ConnectionHandle(
                    handle=handle,
                    created_at=datetime.now(),
                    last_used=datetime.now(),
                    in_use=True,
                    use_count=1
                )
                # Don't add to pool since we're over the limit
                logger.debug("Created temporary connection due to high demand")
                return connection
            except Exception as e:
                raise ConnectionError(f"Unable to acquire connection: {e}")
    
    def _release_connection(self, connection: ConnectionHandle):
        """
        Release a connection back to the pool (thread-safe).
        
        Args:
            connection: ConnectionHandle to release
        """
        with self._lock:
            connection.in_use = False
            connection.last_used = datetime.now()
            
            # If this connection is not in the pool (temporary connection), close it
            if connection not in self._connections:
                try:
                    NamedPipeProtocol.close_pipe(connection.handle)
                    logger.debug("Closed temporary connection")
                except Exception as e:
                    logger.warning(f"Error closing temporary connection: {e}")
            
            logger.debug("Released connection back to pool")
    
    def cleanup_stale_connections(self, max_age_minutes: int = 30):
        """
        Clean up stale connections that haven't been used recently.
        
        Args:
            max_age_minutes: Maximum age for connections in minutes
        """
        with self._lock:
            now = datetime.now()
            stale_connections = []
            
            for conn in self._connections:
                if not conn.in_use:
                    age_minutes = (now - conn.last_used).total_seconds() / 60
                    if age_minutes > max_age_minutes:
                        stale_connections.append(conn)
            
            for conn in stale_connections:
                try:
                    NamedPipeProtocol.close_pipe(conn.handle)
                    self._connections.remove(conn)
                    logger.debug(f"Cleaned up stale connection (age: {age_minutes:.1f} minutes)")
                except Exception as e:
                    logger.warning(f"Error cleaning up stale connection: {e}")


# Global connection pool instance
_connection_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()


def get_connection_pool() -> ConnectionPool:
    """Get the global connection pool instance (thread-safe)."""
    global _connection_pool
    with _pool_lock:
        if _connection_pool is None:
            _connection_pool = ConnectionPool()
        return _connection_pool


class NamedPipeProtocol:
    """
    Handles low-level named pipe communication protocol.
    
    This class is responsible for the actual pipe operations:
    - Connecting to named pipes
    - Reading and writing data
    - Handling pipe-specific errors
    - Managing timeouts at the protocol level
    """
    
    @staticmethod
    def connect_to_pipe(pipe_name: str, timeout_ms: int) -> Any:
        """
        Connect to the WinDbg extension named pipe using synchronous I/O.
        
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
                0,  # Synchronous I/O for reliable communication
                None
            )
            logger.debug(f"Connected to pipe: {pipe_name}")
            return handle
            
        except pywintypes.error as e:
            error_code = e.args[0]
            
            if error_code == 2:  # ERROR_FILE_NOT_FOUND
                raise ConnectionError("WinDbg extension not found. Make sure the extension is loaded in WinDbg.")
            elif error_code == 231:  # ERROR_PIPE_BUSY
                # Wait for pipe to become available with iterative retry
                start_time = time.time()
                while (time.time() - start_time) * 1000 < timeout_ms:
                    if win32pipe.WaitNamedPipe(pipe_name, min(5000, timeout_ms)):
                        try:
                            # Try to connect again
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
                            if retry_error.args[0] != 231:  # If not busy anymore, re-raise
                                raise ConnectionError(f"Failed to connect after wait: {str(retry_error)}")
                            # Still busy, continue waiting
                            time.sleep(0.1)
                    else:
                        time.sleep(0.1)
                
                raise ConnectionError("WinDbg extension is busy and timeout exceeded.")
            else:
                raise ConnectionError(f"Failed to connect to WinDbg extension: {str(e)}")
    
    @staticmethod
    def write_to_pipe(handle: Any, data: bytes, timeout_ms: int):
        """
        Write data to the pipe using synchronous I/O.
        
        Args:
            handle: Pipe handle
            data: Data to write
            timeout_ms: Write timeout in milliseconds
            
        Raises:
            ConnectionError: If write operation fails
        """
        try:
            win32file.WriteFile(handle, data)
            logger.debug(f"Successfully wrote {len(data)} bytes to pipe")
                
        except pywintypes.error as e:
            raise ConnectionError(f"Failed to write to pipe: {str(e)}")
    
    @staticmethod
    def read_from_pipe(handle: Any, timeout_ms: int) -> bytes:
        """
        Read response from the pipe using synchronous I/O.
        
        Args:
            handle: Pipe handle
            timeout_ms: Read timeout in milliseconds
            
        Returns:
            Data read from the pipe
            
        Raises:
            TimeoutError: If read operation times out
            ConnectionError: If read operation fails
        """
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
    
    @staticmethod
    def close_pipe(handle: Any):
        """
        Safely close a pipe handle.
        
        Args:
            handle: Pipe handle to close
        """
        if handle:
            try:
                win32file.CloseHandle(handle)
            except Exception as e:
                logger.warning(f"Error closing pipe handle: {e}")


class MessageProtocol:
    """
    Handles message-level protocol for MCP communication.
    
    This class is responsible for:
    - Message serialization and deserialization
    - Message validation
    - Protocol-level error detection
    - Message formatting for the WinDbg extension
    """
    
    @staticmethod
    def create_command_message(command: str, timeout_ms: int) -> Dict[str, Any]:
        """
        Create a command message for the WinDbg extension.
        
        Args:
            command: The WinDbg command to execute
            timeout_ms: Timeout in milliseconds
            
        Returns:
            Dictionary representing the message
        """
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
        """
        Create a direct handler message for the WinDbg extension.
        
        This is used for session management and other non-WinDbg commands
        that map directly to C++ extension handlers.
        
        Args:
            handler_name: Name of the handler (e.g., "version", "health_check")
            **kwargs: Additional arguments to pass to the handler
            
        Returns:
            Dictionary representing the message
        """
        message = {
            "type": "command",
            "command": handler_name,
            "id": int(time.time() * 1000)
        }
        
        # Add any additional arguments
        if kwargs:
            message["args"] = kwargs
            
        return message
    
    @staticmethod
    def serialize_message(message: Dict[str, Any]) -> bytes:
        """
        Serialize a message to bytes for transmission.
        
        Args:
            message: Message dictionary to serialize
            
        Returns:
            Serialized message as bytes
            
        Raises:
            CommunicationError: If serialization fails
        """
        try:
            message_str = json.dumps(message) + "\n"
            return message_str.encode('utf-8')
        except (TypeError, ValueError) as e:
            raise CommunicationError(f"Failed to serialize message: {e}")
    
    @staticmethod
    def parse_response(response_data: bytes) -> Dict[str, Any]:
        """
        Parse the response data from the extension.
        
        Args:
            response_data: Raw response data from the pipe
            
        Returns:
            Parsed response dictionary
            
        Raises:
            CommunicationError: If parsing fails
        """
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
        """
        Validate that a response message has the expected structure.
        
        Args:
            response: Response dictionary to validate
            
        Returns:
            True if response is valid, False otherwise
        """
        try:
            # Check for required fields
            if "status" not in response:
                return False
            
            # Validate status field
            status = response.get("status")
            if status not in ["success", "error"]:
                return False
            
            # For error responses, check error field
            if status == "error" and "error" not in response:
                return False
            
            # For success responses, check output field
            if status == "success" and "output" not in response:
                return False
            
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def detect_network_debugging_error(error_message: str) -> bool:
        """
        Detect if an error message indicates network debugging issues.
        
        Args:
            error_message: Error message to analyze
            
        Returns:
            True if this appears to be a network debugging error
        """
        network_error_indicators = [
            "retry sending", "transport connection", "lost", "network",
            "target windows seems lost", "resync with target"
        ]
        
        return any(phrase in error_message.lower() for phrase in network_error_indicators) 