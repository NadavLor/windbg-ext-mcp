#!/usr/bin/env python
"""
Simplified WinDbg MCP Server implementation - Hybrid Architecture Edition.

This is a streamlined version of the MCP server that focuses on core debugging
functionality with reduced complexity and better organization. Enhanced with
connection resilience, session recovery, and performance optimization for 
kernel debugging scenarios.

HYBRID ARCHITECTURE:
- FastMCP with stdio transport for Cursor ↔ Python MCP Server communication
- Named pipe client for Python MCP Server ↔ WinDbg Extension communication
- Enhanced error handling and network debugging resilience
"""
import sys
import os
import logging
import time
from typing import Any, Dict, List, Optional, Union

from fastmcp import FastMCP
from config import LOG_FORMAT, load_environment_config, OptimizationLevel, DebuggingMode
from tools import register_all_tools, get_tool_info
from core.communication import (
    test_connection, test_target_connection, send_command,
    start_connection_monitoring, stop_connection_monitoring,
    set_debugging_mode, get_connection_health, diagnose_connection_issues,
    NetworkDebuggingError
)
from core.session_recovery import capture_current_session, save_current_session
from core.performance import (
    set_optimization_level, get_performance_report, 
    performance_optimizer
)
from core.async_ops import (
    start_async_monitoring, stop_async_monitoring,
    get_async_stats, async_manager
)

# Configure logging with centralized config
load_environment_config()
from config import LOG_LEVEL, DEBUG_ENABLED

# CRITICAL: Use stderr for logging to avoid interfering with MCP JSON protocol on stdout
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

# Enable debug logging if configured
if DEBUG_ENABLED:
    logger.setLevel(logging.DEBUG)
    logging.getLogger('fastmcp').setLevel(logging.DEBUG)

# Create the FastMCP server instance
mcp = FastMCP()

def detect_debugging_mode() -> str:
    """
    Detect the current debugging mode with enhanced network debugging detection.
        
    Returns:
        "kernel", "user", or "unknown"
    """
    try:
        # Test target connection first
        target_connected, target_status = test_target_connection()
        
        if not target_connected:
            logger.warning(f"Target not connected: {target_status}")
            return "unknown"
        
        # Detect kernel mode
        if "kernel" in target_status.lower():
            return "kernel"
        elif "user" in target_status.lower():
            return "user"
        
        # Try kernel-mode detection commands
        try:
            result = send_command(".effmach", timeout_ms=5000)
            if result and any(x in result.lower() for x in ["x64_kernel", "x86_kernel", "kernel mode"]):
                return "kernel"
        except NetworkDebuggingError as e:
            logger.warning(f"Network debugging issue during mode detection: {e}")
            return "kernel"  # Assume kernel mode for network debugging
        except:
            pass
        
        # Try alternative kernel mode detection
        try:
            result = send_command("!pcr", timeout_ms=5000) 
            if result and not result.startswith("Error:") and "is not a recognized" not in result:
                return "kernel"
        except NetworkDebuggingError as e:
            logger.warning(f"Network debugging issue during PCR check: {e}")
            return "kernel"  # Assume kernel mode for network debugging
        except:
            pass
        
        # Default to user mode if kernel detection fails
        return "user"
        
    except Exception as e:
        logger.error(f"Error detecting debugging mode: {e}")
        return "unknown"

def setup_resilience_features(debugging_mode: str):
    """
    Set up connection resilience features based on debugging mode with hybrid architecture.
    
    Args:
        debugging_mode: The detected debugging mode
    """
    try:
        # Set appropriate network mode for the new communication manager
        if debugging_mode == "kernel":
            # Assume VM network debugging for kernel mode
            set_debugging_mode(DebuggingMode.VM_NETWORK)
            logger.info("Set debugging mode to 'vm_network' for kernel debugging")
        else:
            # Use standard network settings for user mode
            set_debugging_mode(DebuggingMode.LOCAL)
            logger.info("Set debugging mode to 'local' for user-mode debugging")
        
        # Skip automatic health monitoring to prevent WinDbg crashes during connection tests
        # Health monitoring can be started manually if needed
        # start_connection_monitoring()
        logger.info("Connection monitoring available but not auto-started to prevent WinDbg crashes")
        
        # Perform connection diagnostics
        try:
            diagnostics = diagnose_connection_issues()
            logger.info("Connection diagnostics completed:")
            logger.info(f"  - Extension available: {diagnostics['extension_available']}")
            logger.info(f"  - Target connected: {diagnostics['target_connected']}")
            logger.info(f"  - Network debugging: {diagnostics['network_debugging']}")
            
            if diagnostics.get("recommendations"):
                logger.info("Recommendations:")
                for rec in diagnostics["recommendations"]:
                    logger.info(f"  • {rec}")
        except Exception as e:
            logger.warning(f"Could not run connection diagnostics: {e}")
        
        # Capture initial session state if connected
        if test_connection():
            try:
                session_snapshot = capture_current_session("startup_session")
                if session_snapshot:
                    saved = save_current_session()
                    logger.info(f"Captured initial session state: {session_snapshot.session_id} (saved: {saved})")
                else:
                    logger.warning("Failed to capture initial session state")
            except NetworkDebuggingError as e:
                logger.warning(f"Network debugging issue during session capture: {e}")
            except Exception as e:
                logger.warning(f"Could not capture initial session state: {e}")
        
    except Exception as e:
        logger.warning(f"Failed to setup resilience features: {e}")

def setup_performance_optimization(debugging_mode: str):
    """
    Set up performance optimization features for network debugging.
    
    Args:
        debugging_mode: The detected debugging mode
    """
    try:
        # Set optimization level based on debugging mode
        if debugging_mode == "kernel":
            # Aggressive optimization for kernel debugging over network
            set_optimization_level(OptimizationLevel.AGGRESSIVE)
            logger.info("Set optimization level to 'aggressive' for kernel debugging")
        else:
            # Basic optimization for user mode
            set_optimization_level(OptimizationLevel.BASIC)
            logger.info("Set optimization level to 'basic' for user-mode debugging")
        
        # Optimize for network debugging scenarios
        performance_optimizer.optimize_for_network_debugging()
        logger.info("Applied network debugging optimizations")
        
        # Start async operations monitoring
        start_async_monitoring()
        logger.info("Started async operations monitoring")
        
        # Display initial performance status
        try:
            perf_report = get_performance_report()
            async_stats = get_async_stats()
            
            logger.info(f"Performance optimization initialized:")
            logger.info(f"  - Optimization level: {perf_report['optimization_level']}")
            logger.info(f"  - Cache size: {perf_report.get('cache_statistics', {}).get('max_size', 'unknown')}")
            logger.info(f"  - Async workers: {async_stats.get('total_managed_tasks', 0)} task slots")
            
        except Exception as e:
            logger.warning(f"Could not get initial performance metrics: {e}")
        
    except Exception as e:
        logger.warning(f"Failed to setup performance optimization: {e}")

def main():
    """
    Main entry point for the WinDbg MCP Server with modular architecture and enhanced features.
    """
    logger.info("Starting WinDbg MCP Server (Modular Architecture Edition)")
    
    # Get tool information from the new modular system
    tool_info = get_tool_info()
    
    # Log startup information to stderr (not stdout to avoid MCP protocol conflicts)
    logger.info("WinDbg MCP Server - Modular Architecture Edition")
    logger.info("================================================")
    logger.info(f"Total tools: {tool_info['total_tools']}")
    logger.info("Tool categories:")
    for category, details in tool_info['categories'].items():
        logger.info(f"  📁 {category}: {len(details['tools'])} tools")
        for tool in details['tools']:
            logger.info(f"     • {tool}")
    logger.info("")
    
    # Test initial connection with enhanced diagnostics
    logger.info("Testing connection to WinDbg extension...")
    logger.info("=" * 50)
    
    try:
        connected = test_connection()
        if connected:
            logger.info("✓ Connected to WinDbg extension")
            
            # Test target connection
            target_connected, target_status = test_target_connection()
            if target_connected:
                logger.info(f"✓ Target connection: {target_status}")
            else:
                logger.info(f"⚠ Target issue: {target_status}")
        else:
            logger.info("✗ Not connected to WinDbg extension")
            logger.info("")
            logger.info("Diagnosing connection issues...")
            
            # Run comprehensive diagnostics
            diagnostics = diagnose_connection_issues()
            logger.info(f"Extension available: {diagnostics['extension_available']}")
            logger.info(f"Target connected: {diagnostics['target_connected']}")
            
            if diagnostics.get("recommendations"):
                logger.info("\nRecommendations:")
                for rec in diagnostics["recommendations"]:
                    logger.info(f"  • {rec}")
                    
    except NetworkDebuggingError as e:
        logger.info(f"⚠ Network debugging issue detected: {e}")
        logger.info("Note: This is common with VM-based kernel debugging")
        connected = True  # Assume connected for network debugging scenarios
    except Exception as e:
        logger.info(f"✗ Connection test failed: {e}")
        connected = False
    
    logger.info("")
    
    # Detect debugging mode and set up features
    if connected:
        debugging_mode = detect_debugging_mode()
        logger.info(f"Detected debugging mode: {debugging_mode}")
        
        # Setup resilience features
        setup_resilience_features(debugging_mode)
        
        # Setup performance optimization
        setup_performance_optimization(debugging_mode)
        
        logger.info("")
    
    # Register all tools with the modular system
    logger.info("Registering tools with modular architecture...")
    try:
        register_all_tools(mcp)
        logger.info("Successfully registered all tools")
    except Exception as e:
        logger.error(f"Failed to register tools: {e}")
        raise
    
    logger.info("MCP Server ready! Use get_help() to see available tools and examples.")
    logger.info("")
    
    # Run the server
    try:
        mcp.run()
    except KeyboardInterrupt:
        # FastMCP closes stdio streams, so avoid any print/logging after this
        # Just exit cleanly without trying to write to closed streams
        pass
    except Exception as e:
        # Only log if streams are still available
        try:
            logger.error(f"Server error: {e}")
        except:
            pass
        raise
    finally:
        # Cleanup without any I/O operations to avoid closed stream errors
        try:
            stop_connection_monitoring()
            stop_async_monitoring()
        except:
            pass
        
        # Exit immediately to avoid any further I/O errors
        import sys
        sys.exit(0)

if __name__ == "__main__":
    main() 