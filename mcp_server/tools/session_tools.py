"""
Session management tools for WinDbg MCP server.

This module contains tools for managing debugging sessions, connections, and diagnostics.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from fastmcp import FastMCP, Context

from core.communication import (
    send_command, send_handler_command, test_connection, test_target_connection
)
from core.hints import get_parameter_help
# _get_timeout moved to unified execution system

logger = logging.getLogger(__name__)

def _get_timeout(command: str) -> int:
    """Helper function to get timeout for commands using unified system."""
    from core.execution.timeout_resolver import resolve_timeout
    from config import DebuggingMode
    return resolve_timeout(command, DebuggingMode.VM_NETWORK)

def register_session_tools(mcp: FastMCP):
    """Register all session management tools."""
    
    @mcp.tool()
    async def debug_session(ctx: Context, action: str = "status") -> Dict[str, Any]:
        """
        Manage and get information about the debugging session.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "status", "connection", "version"
            
        Returns:
            Session information or status
        """
        logger.debug(f"Debug session action: {action}")
        
        try:
            if action == "status":
                # Get comprehensive session status
                connected = test_connection()
                if not connected:
                    return {
                        "connected": False,
                        "error": "WinDbg extension not connected",
                        "suggestions": [
                            "Load the extension: .load C:\\path\\to\\windbgmcpExt.dll",
                            "Verify WinDbg is running",
                            "Check extension is properly compiled"
                        ]
                    }
                
                # Get version and status information
                version_output = send_command("version", timeout_ms=_get_timeout("version"))
                
                return {
                    "connected": True,
                    "status": "Active debugging session",
                    "version_info": version_output[:200] + "..." if len(version_output) > 200 else version_output
                }
                
            elif action == "connection":
                # Test connection and return detailed status
                try:
                    connected = test_connection()
                    if connected:
                        return {"connected": True, "status": "Extension connection OK"}
                    else:
                        return {"connected": False, "status": "Extension not available"}
                except Exception as e:
                    return {"connected": False, "error": str(e)}
                    
            elif action == "version":
                try:
                    result = send_handler_command("version", timeout_ms=_get_timeout("version"))
                    return {
                        "success": True,
                        "version": result.get("output", "unknown"),
                        "timestamp": datetime.now().isoformat()
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Failed to get version: {e}",
                        "status": "version_failed"
                    }
            
            else:
                return {
                    "error": f"Unknown action: {action}",
                    "available_actions": ["status", "connection", "version"],
                    "usage": "debug_session(action='status')"
                }
                
        except Exception as e:
            logger.error(f"Debug session error: {e}")
            return {"error": str(e), "action": action}

    @mcp.tool()
    async def connection_manager(ctx: Context, action: str = "status") -> Dict[str, Any]:
        """
        Manage connection to WinDbg extension.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "status", "test"
            
        Returns:
            Connection management results
        """
        logger.debug(f"Connection manager action: {action}")
        
        try:
            if action == "status":
                # Get connection health from communication manager
                from core.communication import _get_communication_manager
                comm_manager = _get_communication_manager()
                health = comm_manager.get_connection_health()
                
                return {
                    "connection_status": "connected" if health.is_connected else "disconnected",
                    "extension_available": health.extension_responsive,
                    "target_responsive": health.target_responsive,
                    "consecutive_failures": health.consecutive_failures,
                    "last_error": health.last_error,
                    "status": "WinDbg extension is responding" if health.extension_responsive else "Extension not responding"
                }
                
            elif action == "test":
                # Run comprehensive connection test
                result = send_command("version", timeout_ms=_get_timeout("version"))
                
                return {
                    "test_command": "version",
                    "success": bool(result),
                    "response_length": len(result) if result else 0,
                    "status": "Connection test passed" if result else "Connection test failed"
                }
                
            else:
                return {
                    "error": f"Unknown action: {action}",
                    "available_actions": ["status", "test"],
                    "usage": "connection_manager(action='status')"
                }
                
        except Exception as e:
            logger.error(f"Connection manager error: {e}")
            return {"error": str(e), "action": action}

    @mcp.tool()
    async def session_manager(ctx: Context, action: str = "status") -> Dict[str, Any]:
        """
        Basic session management.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "status", "info"
            
        Returns:
            Session management results
        """
        logger.debug(f"Session manager action: {action}")
        
        try:
            if action == "status":
                # Get basic session status
                connected = test_connection()
                target_connected, target_status = test_target_connection()
                
                return {
                    "extension_connected": connected,
                    "target_connected": target_connected,
                    "target_status": target_status,
                    "overall_status": "ready" if connected and target_connected else "not_ready"
                }
                
            elif action == "info":
                # Get detailed session information
                if not test_connection():
                    return {"error": "Extension not connected"}
                
                try:
                    version_output = send_command("version", timeout_ms=_get_timeout("version"))
                    
                    # Detect debugging mode
                    is_kernel = "kernel" in version_output.lower()
                    is_user = "user" in version_output.lower() or not is_kernel
                    
                    # Try to get module information
                    try:
                        modules_output = send_command("lm", timeout_ms=_get_timeout("lm"))
                        module_count = len([line for line in modules_output.split('\n') if 'image' in line.lower()])
                    except:
                        module_count = "unknown"
                    
                    return {
                        "debugging_mode": "kernel" if is_kernel else "user",
                        "basic_info": version_output[:150] + "..." if len(version_output) > 150 else version_output,
                        "module_count": module_count,
                        "capabilities": {
                            "can_break": True,
                            "can_analyze": True,
                            "can_modify": is_kernel
                        }
                    }
                    
                except Exception as e:
                    return {"error": f"Failed to get session info: {e}"}
            
            else:
                return {
                    "error": f"Unknown action: {action}",
                    "available_actions": ["status", "info"],
                    "usage": "session_manager(action='status')"
                }
                
        except Exception as e:
            logger.error(f"Session manager error: {e}")
            return {"error": str(e), "action": action} 
