"""
Enhanced communication protocols module for WinDbg MCP Extension.

This module provides thread-safe connection pooling and concurrency fixes for the
named pipe communication with the WinDbg extension.
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
from .communication_protocols import (
    CommunicationError, TimeoutError, ConnectionError, NetworkDebuggingError,
    NamedPipeProtocol, MessageProtocol
)

logger = logging.getLogger(__name__)


@dataclass
class ConnectionHandle:
    """Represents a connection handle with metadata."""
    handle: Any
    created_at: datetime
    last_used: datetime
    in_use: bool = False
    use_count: int = 0
    thread_id: int = 0


class EnhancedConnectionPool:
    """
    Thread-safe connection pool for named pipe connections.
    
    This addresses concurrency issues by:
    - Managing multiple pipe connections
    - Providing thread-safe access to connections
    - Implementing connection reuse and cleanup
    - Handling connection failures gracefully
    - Request queuing for high concurrency scenarios
    """
    
    def __init__(self, max_connections: int = 5):
        self._max_connections = max_connections
        self._connections: List[ConnectionHandle] = []
        self._lock = threading.RLock()  # Reentrant lock for nested access
        self._request_queue = []
        self._queue_condition = threading.Condition(self._lock)
        self._pipe_name = PIPE_NAME
        self._active_requests = 0
        self._max_concurrent_requests = 10
    
    @contextmanager
    def get_connection(self, timeout_ms: int = 10000):
        """
        Context manager to get a connection from the pool with request queuing.
        
        Args:
            timeout_ms: Connection timeout in milliseconds
            
        Yields:
            Connection handle for use
            
        Raises:
            ConnectionError: If unable to get a connection
            TimeoutError: If request times out in queue
        """
        start_time = time.time()
        connection = None
        
        # Check if we're over the concurrent request limit
        with self._lock:
            if self._active_requests >= self._max_concurrent_requests:
                # Wait for a slot to become available
                while self._active_requests >= self._max_concurrent_requests:
                    elapsed = (time.time() - start_time) * 1000
                    if elapsed > timeout_ms:
                        raise TimeoutError(f"Request timed out waiting in queue after {elapsed:.0f}ms")
                    
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
        """
        Acquire a connection from the pool (thread-safe).
        
        Args:
            timeout_ms: Connection timeout in milliseconds
            
        Returns:
            ConnectionHandle object
            
        Raises:
            ConnectionError: If unable to acquire a connection
        """
        current_thread = threading.get_ident()
        
        # First, try to find an available existing connection
        with self._lock:
            for conn in self._connections:
                if not conn.in_use:
                    conn.in_use = True
                    conn.last_used = datetime.now()
                    conn.use_count += 1
                    conn.thread_id = current_thread
                    logger.debug(f"Reusing existing connection (use count: {conn.use_count}, thread: {current_thread})")
                    return conn
            
            # Check if we can create a new connection (copy state while holding lock)
            can_create_new = len(self._connections) < self._max_connections
            pipe_name = self._pipe_name
            max_connections = self._max_connections
        
        # If we can create a new connection, do it outside the lock
        if can_create_new:
            try:
                handle = NamedPipeProtocol.connect_to_pipe(pipe_name, timeout_ms)
                
                # Re-acquire lock to check if we can still add the connection
                with self._lock:
                    if len(self._connections) < self._max_connections:
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
                    else:
                        # Pool limit reached while we were creating connection, use as temporary
                        connection = ConnectionHandle(
                            handle=handle,
                            created_at=datetime.now(),
                            last_used=datetime.now(),
                            in_use=True,
                            use_count=1,
                            thread_id=current_thread
                        )
                        logger.debug(f"Created temporary connection (pool limit reached during creation, thread: {current_thread})")
                        return connection
            except Exception as e:
                logger.error(f"Failed to create new connection: {e}")
                raise ConnectionError(f"Unable to create connection: {e}")
        
        # All connections are in use, create a temporary connection outside the lock
        logger.debug(f"All connections in use, creating temporary connection for thread {current_thread}")
        try:
            handle = NamedPipeProtocol.connect_to_pipe(pipe_name, timeout_ms)
            connection = ConnectionHandle(
                handle=handle,
                created_at=datetime.now(),
                last_used=datetime.now(),
                in_use=True,
                use_count=1,
                thread_id=current_thread
            )
            logger.debug(f"Created temporary connection for high concurrency (thread: {current_thread})")
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
            connection.thread_id = 0
            
            # If this connection is not in the pool (temporary connection), close it
            if connection not in self._connections:
                try:
                    NamedPipeProtocol.close_pipe(connection.handle)
                    logger.debug(f"Closed temporary connection")
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
                    age_minutes = (now - conn.last_used).total_seconds() / 60
                    NamedPipeProtocol.close_pipe(conn.handle)
                    self._connections.remove(conn)
                    logger.debug(f"Cleaned up stale connection (age: {age_minutes:.1f} minutes)")
                except Exception as e:
                    logger.warning(f"Error cleaning up stale connection: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        with self._lock:
            return {
                "total_connections": len(self._connections),
                "active_connections": sum(1 for conn in self._connections if conn.in_use),
                "active_requests": self._active_requests,
                "max_connections": self._max_connections,
                "max_concurrent_requests": self._max_concurrent_requests,
                "connection_details": [
                    {
                        "in_use": conn.in_use,
                        "use_count": conn.use_count,
                        "age_minutes": (datetime.now() - conn.created_at).total_seconds() / 60,
                        "thread_id": conn.thread_id
                    }
                    for conn in self._connections
                ]
            }


class EnhancedMessageProtocol(MessageProtocol):
    """
    Enhanced message protocol with better error handling and validation.
    """
    
    @staticmethod
    def create_command_message_with_retry_info(command: str, timeout_ms: int, retry_count: int = 0) -> Dict[str, Any]:
        """
        Create a command message with retry information.
        
        Args:
            command: The WinDbg command to execute
            timeout_ms: Timeout in milliseconds
            retry_count: Number of retries attempted
            
        Returns:
            Dictionary representing the message
        """
        message = MessageProtocol.create_command_message(command, timeout_ms)
        message["retry_count"] = retry_count
        message["thread_id"] = threading.get_ident()
        return message
    
    @staticmethod
    def validate_response_enhanced(response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhanced response validation with detailed error information.
        
        Args:
            response: Response dictionary to validate
            
        Returns:
            Dictionary with validation results and suggestions
        """
        validation_result = {
            "valid": False,
            "errors": [],
            "suggestions": []
        }
        
        try:
            # Check for required fields
            if "status" not in response:
                validation_result["errors"].append("Missing 'status' field")
                validation_result["suggestions"].append("Ensure extension returns proper status")
            
            # Validate status field
            status = response.get("status")
            if status not in ["success", "error"]:
                validation_result["errors"].append(f"Invalid status: {status}")
                validation_result["suggestions"].append("Status must be 'success' or 'error'")
            
            # For error responses, check error field
            if status == "error":
                if "error" not in response:
                    validation_result["errors"].append("Error response missing 'error' field")
                else:
                    # Check if it's a known error type
                    error_msg = response.get("error", "").lower()
                    if "timeout" in error_msg:
                        validation_result["suggestions"].append("Consider increasing timeout for this command")
                    elif "connection" in error_msg:
                        validation_result["suggestions"].append("Check WinDbg extension status and restart if needed")
            
            # For success responses, check output field
            if status == "success" and "output" not in response:
                validation_result["errors"].append("Success response missing 'output' field")
            
            validation_result["valid"] = len(validation_result["errors"]) == 0
            return validation_result
            
        except Exception as e:
            validation_result["errors"].append(f"Validation exception: {str(e)}")
            return validation_result


# Global enhanced connection pool instance
_enhanced_connection_pool: Optional[EnhancedConnectionPool] = None
_enhanced_pool_lock = threading.Lock()


def get_enhanced_connection_pool() -> EnhancedConnectionPool:
    """Get the global enhanced connection pool instance (thread-safe)."""
    global _enhanced_connection_pool
    with _enhanced_pool_lock:
        if _enhanced_connection_pool is None:
            _enhanced_connection_pool = EnhancedConnectionPool()
        return _enhanced_connection_pool


def send_command_with_pooling(command: str, timeout_ms: int, retry_count: int = 0) -> str:
    """
    Send a command using the enhanced connection pool.
    
    Args:
        command: The WinDbg command to execute
        timeout_ms: Timeout in milliseconds
        retry_count: Current retry attempt count
        
    Returns:
        Command output as string
        
    Raises:
        ConnectionError: If connection fails
        TimeoutError: If command times out
        CommunicationError: If command execution fails
    """
    pool = get_enhanced_connection_pool()
    
    try:
        with pool.get_connection(timeout_ms) as handle:
            # Create message with retry info
            message = EnhancedMessageProtocol.create_command_message_with_retry_info(
                command, timeout_ms, retry_count
            )
            
            # Send the message
            message_bytes = MessageProtocol.serialize_message(message)
            logger.debug(f"Sending command with pooled connection: {command}")
            
            NamedPipeProtocol.write_to_pipe(handle, message_bytes, timeout_ms)
            
            # Read the response
            response_data = NamedPipeProtocol.read_from_pipe(handle, timeout_ms)
            response = MessageProtocol.parse_response(response_data)
            
            # Enhanced validation
            validation = EnhancedMessageProtocol.validate_response_enhanced(response)
            if not validation["valid"]:
                logger.warning(f"Response validation failed: {validation['errors']}")
                if validation["suggestions"]:
                    logger.info(f"Suggestions: {validation['suggestions']}")
            
            # Handle response
            if response.get("status") == "error":
                error_message = response.get("error", "Unknown error")
                if MessageProtocol.detect_network_debugging_error(error_message):
                    raise NetworkDebuggingError(error_message)
                raise CommunicationError(error_message)
                
            return response.get("output", "")
            
    except (ConnectionError, TimeoutError, NetworkDebuggingError):
        # Re-raise these specific exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in pooled command execution: {e}")
        raise CommunicationError(f"Command execution failed: {str(e)}")


def get_connection_pool_stats() -> Dict[str, Any]:
    """Get statistics about the connection pool."""
    try:
        pool = get_enhanced_connection_pool()
        return pool.get_stats()
    except Exception as e:
        return {"error": str(e)} 