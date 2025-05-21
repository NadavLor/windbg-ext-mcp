#!/usr/bin/env python
"""
WinDbg MCP Server implementation with FastMCP.
This server connects WinDbg to Cursor via the Model Context Protocol (MCP).
"""
from fastmcp import FastMCP, Context
from fastmcp.settings import ServerSettings
from commands import execute_command, display_type, display_memory, DEFAULT_TIMEOUT_MS
from commands.command_handlers import dispatch_command
import sys
import logging
import traceback
import os
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Set more verbose logging for FastMCP components when debugging
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
if DEBUG:
    logger.setLevel(logging.DEBUG)
    logging.getLogger('fastmcp').setLevel(logging.DEBUG)
    logging.getLogger('mcp').setLevel(logging.DEBUG)
    logging.getLogger('uvicorn').setLevel(logging.DEBUG)

# Create the FastMCP server instance
logger.info("Creating WinDbg MCP Server")
mcp = FastMCP(identifier="WinDbg MCP Server")

# Available tools for documentation
AVAILABLE_TOOLS = [
    "check_connection",
    "get_metadata",
    "get_current_address",
    "list_modules",
    "run_command",
    "display_type",
    "display_memory",
    "set_breakpoint",
    "list_processes",
    "get_peb",
    "get_teb",
    "switch_process",
    "list_threads",
    "switch_thread",
    "get_interrupt",
    "get_idt",
    "get_object",
    "get_object_header",
    "get_pte",
    "get_handle",
    "search_symbols",
    "get_stack_trace"
]

@mcp.tool()
async def check_connection(ctx: Context, random_string=None):
    """Check if the connection to the MCP server is working"""
    logger.debug(f"Connection check with random string: {random_string}")
    try:
        # Just return True, this doesn't actually check WinDBG connection
        return True
    except Exception as e:
        logger.error(f"Error in check_connection: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "connection": False}

@mcp.tool()
async def get_metadata(ctx: Context, random_string=None):
    """Get metadata about the WinDbg debugging session including version and loaded modules"""
    logger.debug("Getting metadata")
    try:
        # Execute 'version' command to get WinDbg version
        version_info = execute_command("version")
        
        # Execute 'lm' command to list modules with a longer timeout
        modules = execute_command("lm", timeout_ms=30000)
        
        return {
            "version": version_info,
            "modules": modules,
            "connected": True
        }
    except Exception as e:
        logger.error(f"Error getting metadata: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "connected": False}

@mcp.tool()
async def get_current_address(ctx: Context, random_string=None):
    """Get the current instruction pointer address"""
    logger.debug("Getting current address")
    try:
        # Execute command to get the current instruction pointer
        return execute_command("r @eip")
    except Exception as e:
        logger.error(f"Error getting current address: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def list_modules(ctx: Context, count=None, offset=None):
    """List loaded modules in the debugging session"""
    logger.debug(f"Listing modules with count={count}, offset={offset}")
    try:
        cmd = "lm"
        if count is not None:
            cmd += f" {count}"
        return execute_command(cmd, timeout_ms=30000)
    except Exception as e:
        logger.error(f"Error listing modules: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def run_command(ctx: Context, command: str):
    """Run a WinDbg command and return its output"""
    logger.debug(f"Running command: {command}")
    try:
        # Determine appropriate timeout based on command complexity
        timeout_ms = DEFAULT_TIMEOUT_MS
        if command.startswith("lm") or command.startswith("!process"):
            timeout_ms = 60000  # Longer timeout for potentially lengthy operations
        elif command.startswith("!handle"):
            timeout_ms = 120000  # Even longer timeout for handle commands
        
        # Use improved command dispatcher
        result = dispatch_command(command, timeout_ms=timeout_ms)
        
        # Proper error handling
        if not result or result.strip() in ["", "NONE", "None"]:
            logger.warning(f"Command '{command}' returned empty result")
            return {"warning": "Command returned no output. The command might be invalid or not applicable in the current context."}
        
        if result.startswith("Error:"):
            logger.error(f"Command '{command}' returned error: {result}")
            return {"error": result[7:] if result.startswith("Error: ") else result}
        
        return result
    except Exception as e:
        logger.error(f"Error executing command '{command}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def display_type_tool(ctx: Context, type_name: str, address: str = ""):
    """Display details about a data type or structure"""
    logger.debug(f"Displaying type {type_name} at address {address}")
    try:
        return display_type(type_name, address)
    except Exception as e:
        logger.error(f"Error displaying type '{type_name}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def display_memory(ctx: Context, address: str, length: int = 32):
    """Display memory at the specified address"""
    logger.debug(f"Displaying memory at {address} with length {length}")
    try:
        return display_memory(address, length)
    except Exception as e:
        logger.error(f"Error displaying memory at '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def set_breakpoint(ctx: Context, address: str):
    """Set a breakpoint at the specified address or symbol"""
    logger.debug(f"Setting breakpoint at {address}")
    try:
        # Set breakpoint and get confirmation
        result = execute_command(f"bp {address}", timeout_ms=15000)
        return result
    except Exception as e:
        logger.error(f"Error setting breakpoint at '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def list_processes(ctx: Context, random_string=None):
    """List all processes in the current debugging session"""
    logger.debug("Listing processes")
    try:
        # Use our improved handler for process commands
        from commands.command_handlers import handle_process_command
        return handle_process_command("!process 0 0", timeout_ms=60000)
    except Exception as e:
        logger.error(f"Error listing processes: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_peb(ctx: Context, random_string=None):
    """Get the Process Environment Block (PEB) information for the current process"""
    logger.debug("Getting PEB information")
    try:
        # The !peb command displays information about the Process Environment Block
        return execute_command("!peb", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting PEB: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_teb(ctx: Context, random_string=None):
    """Get the Thread Environment Block (TEB) information for the current thread"""
    logger.debug("Getting TEB information")
    try:
        # The !teb command displays information about the Thread Environment Block
        return execute_command("!teb", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting TEB: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def switch_process(ctx: Context, address: str):
    """Switch to the specified process by address"""
    logger.debug(f"Switching to process at {address}")
    try:
        # The .process command switches the current process context
        return execute_command(f".process {address}", timeout_ms=20000)
    except Exception as e:
        logger.error(f"Error switching to process at '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def list_threads(ctx: Context, random_string=None):
    """List all threads in the current process"""
    logger.debug("Listing threads")
    try:
        # The !thread command lists thread information
        return execute_command("!thread", timeout_ms=30000)
    except Exception as e:
        logger.error(f"Error listing threads: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def switch_thread(ctx: Context, address: str):
    """Switch to the specified thread by address"""
    logger.debug(f"Switching to thread at {address}")
    try:
        # The .thread command switches the current thread context
        return execute_command(f".thread {address}", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error switching to thread at '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_interrupt(ctx: Context, address: str):
    """Get details about an interrupt at the specified address"""
    logger.debug(f"Getting interrupt information for {address}")
    try:
        # Using display_type similar to hybrid_server approach
        return display_type("nt!_KINTERRUPT", address)
    except Exception as e:
        logger.error(f"Error getting interrupt information for '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_idt(ctx: Context, random_string=None):
    """Get the Interrupt Descriptor Table (IDT)"""
    logger.debug("Getting IDT")
    try:
        # The !idt command without parameters shows the entire Interrupt Descriptor Table
        return execute_command("!idt", timeout_ms=20000)
    except Exception as e:
        logger.error(f"Error getting IDT: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_object(ctx: Context, address: str):
    """Get details about a kernel object at the specified address"""
    logger.debug(f"Getting object information for {address}")
    try:
        # The !object command shows information about a kernel object
        return execute_command(f"!object {address}", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting object information for '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_object_header(ctx: Context, address: str):
    """Get the object header for the object at the specified address"""
    logger.debug(f"Getting object header for {address}")
    try:
        # The !objheader command shows the header information for an object
        return execute_command(f"!objheader {address}", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting object header for '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_pte(ctx: Context, address: str):
    """Get the Page Table Entry (PTE) for the specified address"""
    logger.debug(f"Getting PTE for {address}")
    try:
        # The !pte command shows the Page Table Entry for an address
        return execute_command(f"!pte {address}", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting PTE for '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_handle(ctx: Context, address: str = ""):
    """Get handle information for the current process or a specific handle"""
    logger.debug(f"Getting handle information for {address}")
    try:
        # Use our improved handler for handle commands
        from commands.command_handlers import handle_handle_command
        
        cmd = "!handle"
        if address:
            cmd += f" {address}"
        else:
            # Add flags for full output when no specific handle is requested
            cmd += " 0 f"
        
        return handle_handle_command(cmd, timeout_ms=120000)
    except Exception as e:
        logger.error(f"Error getting handle information: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def search_symbols(ctx: Context, pattern: str):
    """Search for symbols matching the specified pattern"""
    logger.debug(f"Searching for symbols matching {pattern}")
    try:
        # The x command (examine symbols) can be used to search for symbols
        # Match the exact format from hybrid_server
        return execute_command(f"x {pattern}", timeout_ms=30000)
    except Exception as e:
        logger.error(f"Error searching for symbols matching '{pattern}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_stack_trace(ctx: Context, thread_id: str = ""):
    """Get the stack trace for the current thread or a specific thread"""
    logger.debug(f"Getting stack trace for thread {thread_id}")
    try:
        if thread_id:
            # If a thread ID is specified, first switch to that thread
            try:
                execute_command(f".thread {thread_id}", timeout_ms=15000)
            except Exception as e:
                logger.error(f"Error switching to thread '{thread_id}': {e}")
                return {"error": f"Failed to switch to thread {thread_id}: {str(e)}"}
        
        # Get a stack trace with a good depth
        return execute_command("k 100", timeout_ms=30000)
    except Exception as e:
        logger.error(f"Error getting stack trace: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

# Main entry point
def main():
    logger.info("Starting WinDbg MCP Server")
    
    print("WinDbg MCP Server")
    print("================")
    print("Available tools:")
    for tool_name in AVAILABLE_TOOLS:
        print(f"  - {tool_name}")
    
    # Determine which transport to use
    transport = os.environ.get("MCP_TRANSPORT", "sse")
    host = os.environ.get("MCP_HOST", "localhost")
    port = int(os.environ.get("MCP_PORT", "8000"))
    
    # Use environment variables for timeouts
    os.environ["FASTMCP_TIMEOUT"] = os.environ.get("FASTMCP_TIMEOUT", "120")
    
    logger.info(f"Using transport: {transport}")
    if transport.lower() == "sse":
        logger.info(f"MCP Server available at: http://{host}:{port}/sse")
    
    try:
        # Run with appropriate transport settings
        mcp.run(
            host=host,
            port=port,
            transport=transport
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main() 