"""
Constants for the WinDbg MCP server
"""
import os

# Named pipe settings
PIPE_NAME = r"\\.\pipe\windbgmcp"

# Timeout settings in milliseconds
DEFAULT_TIMEOUT_MS = 30000        # Default timeout
LONG_TIMEOUT_MS = 60000           # Longer operations

# Server configuration
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8000
DEFAULT_TRANSPORT = "sse"

# Debug settings
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Command prefixes for different operations
BREAKPOINT_CMD = "bp"
PROCESS_LIST_CMD = "!process 0 0"
PEB_CMD = "!peb"
TEB_CMD = "!teb" 