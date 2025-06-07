"""
Core communication module for WinDbg MCP Extension.

Simplified architecture with direct communication to WinDbg extension.
"""
import logging
from typing import Dict, Any, Optional, Tuple

from config import DEFAULT_TIMEOUT_MS, PIPE_NAME
from .communication_protocols import (
    NamedPipeProtocol, MessageProtocol, CommunicationError,
    TimeoutError, ConnectionError, NetworkDebuggingError
)

logger = logging.getLogger(__name__)


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
    handle = None
    try:
        # Connect to the named pipe
        handle = NamedPipeProtocol.connect_to_pipe(PIPE_NAME, timeout_ms)
        
        # Create and send message
        message = MessageProtocol.create_command_message(command, timeout_ms)
        message_bytes = MessageProtocol.serialize_message(message)
        NamedPipeProtocol.write_to_pipe(handle, message_bytes, timeout_ms)
        
        # Read and parse response
        response_data = NamedPipeProtocol.read_from_pipe(handle, timeout_ms)
        response = MessageProtocol.parse_response(response_data)
        
        # Handle response
        if response.get("status") == "error":
            error_message = response.get("error", "Unknown error")
            if MessageProtocol.detect_network_debugging_error(error_message):
                raise NetworkDebuggingError(f"Network debugging issue: {error_message}")
            raise CommunicationError(f"Command failed: {error_message}")
            
        return response.get("output", "")
        
    finally:
        if handle:
            NamedPipeProtocol.close_pipe(handle)


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
    handle = None
    try:
        # Connect to the named pipe
        handle = NamedPipeProtocol.connect_to_pipe(PIPE_NAME, timeout_ms)
        
        # Create and send message
        message = MessageProtocol.create_handler_message(handler_name, **kwargs)
        message_bytes = MessageProtocol.serialize_message(message)
        NamedPipeProtocol.write_to_pipe(handle, message_bytes, timeout_ms)
        
        # Read and parse response
        response_data = NamedPipeProtocol.read_from_pipe(handle, timeout_ms)
        response = MessageProtocol.parse_response(response_data)
        
        return response
        
    finally:
        if handle:
            NamedPipeProtocol.close_pipe(handle)


def test_connection() -> bool:
    """
    Test if the connection to the WinDbg extension is working.
    
    Returns:
        True if connection is working, False otherwise
    """
    try:
        result = send_handler_command("version", timeout_ms=3000)
        return result.get("type") in ["success", "response"]
    except Exception as e:
        logger.debug(f"Connection test failed: {e}")
        return False


def test_target_connection() -> Tuple[bool, str]:
    """
    Test the WinDbg target connection.
    
    Returns:
        Tuple of (is_connected, status_message)
    """
    try:
        # Try a simple command to test target responsiveness
        output = send_command("version", timeout_ms=5000)
        if output and "kernel" in output.lower():
            return True, "Kernel debugging target connected"
        elif output:
            return True, "Debugging target connected"
        else:
            return False, "No response from debugging target"
    except NetworkDebuggingError as e:
        return False, f"Network debugging issue: {str(e)}"
    except Exception as e:
        return False, f"Target test failed: {str(e)}"


def diagnose_connection_issues() -> Dict[str, Any]:
    """
    Perform basic connection diagnostics.
    
    Returns:
        Dictionary with diagnostic information
    """
    diagnostics = {
        "extension_available": False,
        "target_connected": False,
        "recommendations": []
    }
    
    try:
        diagnostics["extension_available"] = test_connection()
        target_connected, target_status = test_target_connection()
        diagnostics["target_connected"] = target_connected
        diagnostics["target_status"] = target_status
        
        # Generate recommendations
        if not diagnostics["extension_available"]:
            diagnostics["recommendations"].extend([
                "Load the WinDbg extension with: .load path\\to\\windbgmcpExt.dll",
                "Ensure WinDbg is running and the extension DLL is accessible"
            ])
        
        if not diagnostics["target_connected"]:
            diagnostics["recommendations"].extend([
                "Ensure a debugging target is connected",
                "For kernel debugging, verify target VM configuration"
            ])
            
    except Exception as e:
        logger.error(f"Failed to run diagnostics: {e}")
        diagnostics["error"] = str(e)
    
    return diagnostics 