"""
Session management tools for WinDbg MCP server.

Simplified session management with essential functionality.
"""
import logging
from typing import Dict, Any, List, Optional, Union
from fastmcp import FastMCP, Context

from core.communication import test_connection, send_command, send_handler_command

logger = logging.getLogger(__name__)

def register_session_tools(mcp: FastMCP):
    """Register session management tools."""
    
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
            if action == "connection":
                connected = test_connection()
                return {
                    "connected": connected,
                    "status": "Connected to WinDbg extension" if connected else "Not connected to WinDbg extension"
                }
            
            elif action == "status":
                try:
                    # Test connection and get basic status
                    connected = test_connection()
                    if connected:
                        version_output = send_command("version", timeout_ms=5000)
                        return {
                            "connected": True,
                            "status": "Active debugging session",
                            "version_info": version_output[:200] + "..." if len(version_output) > 200 else version_output
                        }
                    else:
                        return {
                            "connected": False,
                            "status": "No active connection to WinDbg extension"
                        }
                except Exception as e:
                    return {
                        "connected": False,
                        "status": "Connection test failed",
                        "error": str(e)
                    }
            
            elif action == "version":
                try:
                    result = send_handler_command("version", timeout_ms=5000)
                    return {
                        "version": result.get("output", "unknown"),
                        "extension_info": result
                    }
                except Exception as e:
                    return {
                        "error": f"Failed to get version: {e}",
                        "status": "version_failed"
                    }
            
            else:
                return {
                    "error": f"Unknown action '{action}'",
                    "available_actions": ["status", "connection", "version"],
                    "help": "Use debug_session with action='status' to get basic session info"
                }
                
        except Exception as e:
            return {
                "error": f"Debug session failed: {e}",
                "action": action
            }

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
                connected = test_connection()
                return {
                    "connection_status": "connected" if connected else "disconnected",
                    "extension_available": connected,
                    "status": "WinDbg extension is responding" if connected else "WinDbg extension not responding"
                }
            
            elif action == "test":
                try:
                    # Test with a simple command
                    result = send_command("version", timeout_ms=5000)
                    return {
                        "connection_test": "passed",
                        "test_command": "version",
                        "result_preview": result[:100] + "..." if len(result) > 100 else result,
                        "status": "Connection working normally"
                    }
                except Exception as e:
                    return {
                        "connection_test": "failed",
                        "error": str(e),
                        "recommendations": [
                            "Check WinDbg extension is loaded: .load path\\to\\windbgmcpExt.dll",
                            "Verify WinDbg is running and responsive"
                        ]
                    }
            
            else:
                return {
                    "error": f"Unknown action '{action}'",
                    "available_actions": ["status", "test"],
                    "help": "Use connection_manager to check and test WinDbg extension connection"
                }
                
        except Exception as e:
            return {
                "error": f"Connection manager failed: {e}",
                "action": action
            }

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
                try:
                    # Get basic session information
                    connected = test_connection()
                    if connected:
                        version_output = send_command("version", timeout_ms=5000)
                        
                        # Determine if kernel or user mode
                        is_kernel = "kernel" in version_output.lower()
                        
                        return {
                            "session_active": True,
                            "debugging_mode": "kernel" if is_kernel else "user",
                            "connection_status": "active",
                            "basic_info": version_output[:150] + "..." if len(version_output) > 150 else version_output
                        }
                    else:
                        return {
                            "session_active": False,
                            "connection_status": "disconnected",
                            "message": "No active debugging session"
                        }
                except Exception as e:
                    return {
                        "session_active": False,
                        "error": str(e),
                        "message": "Failed to get session status"
                    }
            
            elif action == "info":
                try:
                    # Get more detailed information
                    modules_output = send_command("lm", timeout_ms=10000)
                    return {
                        "session_info": "detailed",
                        "loaded_modules": modules_output[:300] + "..." if len(modules_output) > 300 else modules_output,
                        "status": "Retrieved session information successfully"
                    }
                except Exception as e:
                    return {
                        "error": f"Failed to get session info: {e}",
                        "message": "Could not retrieve detailed session information"
                    }
            
            else:
                return {
                    "error": f"Unknown action '{action}'",
                    "available_actions": ["status", "info"],
                    "help": "Use session_manager to get session status and information"
                }
                
        except Exception as e:
            return {
                "error": f"Session manager failed: {e}",
                "action": action
            } 