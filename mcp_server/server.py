#!/usr/bin/env python
"""
WinDbg MCP Server - Production Edition.

This is the main entry point for the MCP server that provides AI-assisted
Windows kernel debugging through natural language interactions.
"""
import sys
import logging
from typing import Any, Dict, List, Optional, Union

from fastmcp import FastMCP
from config import LOG_FORMAT, load_environment_config, LOG_LEVEL, DEBUG_ENABLED
from tools import register_all_tools, get_tool_info
from core.server_initialization import ServerInitializer, InitializationConfig


# Configure logging
load_environment_config()

# Create different handlers for different log levels
class SplitLevelHandler:
    """Split logging by level to avoid INFO messages showing as errors in MCP client."""
    
    def __init__(self):
        # Handler for actual errors (goes to stderr - will show as [error] in client)
        self.error_handler = logging.StreamHandler(sys.stderr)
        self.error_handler.setLevel(logging.ERROR)
        self.error_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        
        # Handler for info/debug (goes to stderr but with different format to distinguish)
        self.info_handler = logging.StreamHandler(sys.stderr)
        self.info_handler.setLevel(logging.INFO)
        self.info_handler.setFormatter(logging.Formatter('📋 %(message)s'))
        
        # Filter to only show INFO/DEBUG (not ERROR+)
        class InfoOnlyFilter(logging.Filter):
            def filter(self, record):
                return record.levelno < logging.ERROR
        
        self.info_handler.addFilter(InfoOnlyFilter())

# Configure split-level logging
split_handler = SplitLevelHandler()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    handlers=[split_handler.error_handler, split_handler.info_handler]
)

logger = logging.getLogger(__name__)

if DEBUG_ENABLED:
    logger.setLevel(logging.DEBUG)
    logging.getLogger('fastmcp').setLevel(logging.DEBUG)


class WinDbgMCPServer:
    """Main WinDbg MCP Server class."""
    
    def __init__(self):
        self.mcp = FastMCP()
        self.initializer = ServerInitializer(InitializationConfig())
        self._initialized = False
    
    def start(self):
        """Start the WinDbg MCP Server."""
        try:
            # Log startup banner
            self._log_startup_banner()
            
            # Run initialization sequence
            connection_result = self.initializer.initialize()
            self._initialized = True
            
            # Register all tools
            self._register_tools()
        
            # Log ready message
            logger.info("MCP Server ready! Use get_help() to see available tools and examples.")
            logger.info("")
            
            # Run the server
            self._run_server()
            
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise
    
    def _log_startup_banner(self):
        """Log the startup banner with tool information."""
        tool_info = get_tool_info()
        
        logger.info("WinDbg MCP Server - Production Edition")
        logger.info("=" * 50)
        logger.info(f"Total tools: {tool_info['total_tools']}")
        logger.info("Tool categories:")
        
        for category, details in tool_info['categories'].items():
            logger.info(f"  📁 {category}: {len(details['tools'])} tools")
            for tool in details['tools']:
                logger.info(f"     • {tool}")
        logger.info("")
    
    def _register_tools(self):
        """Register all tools with the MCP server."""
        logger.info("Registering tools...")
        try:
            register_all_tools(self.mcp)
            logger.info("Successfully registered all tools")
        except Exception as e:
            logger.error(f"Failed to register tools: {e}")
            raise
    
    def _run_server(self):
        """Run the FastMCP server."""
        try:
            self.mcp.run()
        except KeyboardInterrupt:
            # FastMCP closes stdio streams, so avoid logging after this
            pass
        except Exception as e:
            # Only log if streams are still available
            try:
                logger.error(f"Server error: {e}")
            except:
                pass
            raise


def main():
    """Main entry point for the WinDbg MCP Server."""
    server = WinDbgMCPServer()
    server.start()


if __name__ == "__main__":
    main() 