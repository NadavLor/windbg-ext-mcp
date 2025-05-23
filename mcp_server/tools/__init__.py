"""
Tool registry for WinDbg MCP server.

This module provides the central registration system for all MCP tools,
organized into logical categories for better maintainability.
"""
import logging
from fastmcp import FastMCP

from .session_tools import register_session_tools
from .execution_tools import register_execution_tools
from .analysis_tools import register_analysis_tools
from .performance_tools import register_performance_tools
from .support_tools import register_support_tools

logger = logging.getLogger(__name__)

def register_all_tools(mcp: FastMCP) -> None:
    """
    Register all MCP tools with the FastMCP server.
    
    This function orchestrates the registration of all tool categories:
    - Session management tools (debug_session, connection_manager, session_manager)
    - Command execution tools (run_command, run_sequence)
    - Analysis tools (analyze_process, analyze_thread, analyze_memory, analyze_kernel)
    - Performance tools (performance_manager, async_manager)
    - Support tools (troubleshoot, get_help)
    
    Args:
        mcp: The FastMCP server instance
    """
    logger.info("Starting tool registration for WinDbg MCP server")
    
    try:
        # Register session management tools
        logger.debug("Registering session management tools...")
        register_session_tools(mcp)
        
        # Register command execution tools
        logger.debug("Registering command execution tools...")
        register_execution_tools(mcp)
        
        # Register analysis tools
        logger.debug("Registering analysis tools...")
        register_analysis_tools(mcp)
        
        # Register performance tools
        logger.debug("Registering performance tools...")
        register_performance_tools(mcp)
        
        # Register support tools
        logger.debug("Registering support tools...")
        register_support_tools(mcp)
        
        logger.info("Successfully registered all MCP tools")
        
    except Exception as e:
        logger.error(f"Failed to register tools: {e}")
        raise

# Tool categories for reference
TOOL_CATEGORIES = {
    "session_management": {
        "tools": ["debug_session", "connection_manager", "session_manager"],
        "description": "Tools for managing debugging sessions, connections, and session recovery"
    },
    "command_execution": {
        "tools": ["run_command", "run_sequence"],
        "description": "Tools for executing WinDbg commands with enhanced validation and error handling"
    },
    "analysis": {
        "tools": ["analyze_process", "analyze_thread", "analyze_memory", "analyze_kernel"],
        "description": "Tools for analyzing debugging targets and system state"
    },
    "performance": {
        "tools": ["performance_manager", "async_manager"],
        "description": "Tools for performance optimization and asynchronous command execution"
    },
    "support": {
        "tools": ["troubleshoot", "get_help"],
        "description": "Tools for troubleshooting issues and getting help"
    }
}

def get_tool_info() -> dict:
    """
    Get information about all available tools.
    
    Returns:
        Dictionary containing tool categories and descriptions
    """
    return {
        "categories": TOOL_CATEGORIES,
        "total_tools": sum(len(cat["tools"]) for cat in TOOL_CATEGORIES.values()),
        "architecture": "Modular tool organization with separate registration functions"
    } 