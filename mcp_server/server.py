#!/usr/bin/env python
"""
WinDbg MCP Server implementation with FastMCP.

This server connects WinDbg to Cursor via the Model Context Protocol (MCP),
enabling LLM-assisted debugging of Windows kernel and user-mode applications.
"""
from typing import Any, Dict, List, Optional, Union
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
    "restore_process_context",
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
async def check_connection(ctx: Context, random_string: Optional[str] = None) -> Dict[str, Any]:
    """
    Check if the connection to the MCP server is working.
    
    Args:
        ctx: The MCP context
        random_string: Optional string to echo back (for testing)
        
    Returns:
        Dict with connection status and optional echo
    """
    logger.debug(f"Connection check with random string: {random_string}")
    try:
        result = {"connection": True}
        if random_string:
            result["echo"] = random_string
        return result
    except Exception as e:
        logger.error(f"Error in check_connection: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "connection": False}

@mcp.tool()
async def get_metadata(ctx: Context, random_string: Optional[str] = None) -> Dict[str, Any]:
    """
    Get metadata about the WinDbg debugging session including version and loaded modules.
    
    Args:
        ctx: The MCP context
        random_string: Optional string for compatibility
        
    Returns:
        Dict with version info, modules list, and connection status
    """
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
async def get_current_address(ctx: Context, random_string: Optional[str] = None) -> Union[str, Dict[str, str]]:
    """
    Get the current instruction pointer address.
    
    Args:
        ctx: The MCP context
        random_string: Optional string for compatibility
        
    Returns:
        The instruction pointer address or error dict
    """
    logger.debug("Getting current address")
    try:
        # Execute command to get the current instruction pointer
        return execute_command("r @eip")
    except Exception as e:
        logger.error(f"Error getting current address: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def list_modules(ctx: Context, count: Optional[int] = None, offset: Optional[int] = None) -> Union[str, Dict[str, str]]:
    """
    List loaded modules in the debugging session.
    
    Args:
        ctx: The MCP context
        count: Optional number of modules to list
        offset: Optional offset to start listing from
        
    Returns:
        List of modules or error dict
    """
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
async def run_command(ctx: Context, command: str) -> Union[str, Dict[str, str]]:
    """
    Run a WinDbg command and return its output.
    
    Args:
        ctx: The MCP context
        command: The WinDbg command to execute
        
    Returns:
        Command output or error dict
    """
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
async def display_type_tool(ctx: Context, type_name: str, address: str = "") -> Union[str, Dict[str, str]]:
    """
    Display details about a data type or structure.
    
    Args:
        ctx: The MCP context
        type_name: The name of the type to display
        address: Optional memory address where the structure is located
        
    Returns:
        Type information or error dict
    """
    logger.debug(f"Displaying type {type_name} at address {address}")
    try:
        return display_type(type_name, address)
    except Exception as e:
        logger.error(f"Error displaying type '{type_name}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def display_memory(ctx: Context, address: str, length: int = 32) -> Union[str, Dict[str, str]]:
    """
    Display memory at the specified address.
    
    Args:
        ctx: The MCP context
        address: The memory address to display
        length: Number of bytes to display (default: 32)
        
    Returns:
        Memory contents or error dict
    """
    logger.debug(f"Displaying memory at {address} with length {length}")
    try:
        return display_memory(address, length)
    except Exception as e:
        logger.error(f"Error displaying memory at '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def set_breakpoint(ctx: Context, address: str) -> Union[str, Dict[str, str]]:
    """
    Set a breakpoint at the specified address or symbol.
    
    Args:
        ctx: The MCP context
        address: The address or symbol where to set the breakpoint
        
    Returns:
        Result of the breakpoint command or error dict
    """
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
async def list_processes(ctx: Context, random_string: Optional[str] = None) -> Union[str, Dict[str, str]]:
    """
    List all processes in the current debugging session.
    
    Args:
        ctx: The MCP context
        random_string: Optional string for compatibility
        
    Returns:
        List of processes or error message
    """
    logger.debug("Listing processes")
    try:
        # Use our improved handler for process commands with a longer timeout
        from commands.command_handlers import handle_process_command
        result = handle_process_command("!process 0 0", timeout_ms=60000)
        
        # Ensure we're returning a string, not a dictionary
        if isinstance(result, dict):
            if "error" in result:
                return f"Error: {result['error']}"
            return str(result)
        
        return result
    except Exception as e:
        logger.error(f"Error listing processes: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_peb(ctx: Context, random_string: Optional[str] = None) -> Union[str, Dict[str, str]]:
    """
    Get the Process Environment Block (PEB) information for the current process.
    
    Args:
        ctx: The MCP context
        random_string: Optional string for compatibility
        
    Returns:
        PEB information or error dict
    """
    logger.debug("Getting PEB information")
    try:
        # The !peb command displays information about the Process Environment Block
        return execute_command("!peb", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting PEB: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_teb(ctx: Context, random_string: Optional[str] = None) -> Union[str, Dict[str, str]]:
    """
    Get the Thread Environment Block (TEB) information for the current thread.
    
    Args:
        ctx: The MCP context
        random_string: Optional string for compatibility
        
    Returns:
        TEB information or error dict
    """
    logger.debug("Getting TEB information")
    try:
        # The !teb command displays information about the Thread Environment Block
        return execute_command("!teb", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting TEB: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def switch_process(ctx: Context, address: str, save_previous: bool = True) -> Union[str, Dict[str, str]]:
    """
    Switch to the specified process by address.
    
    Args:
        ctx: The MCP context
        address: Address of the process to switch to
        save_previous: Whether to save the current process context (default: True)
        
    Returns:
        Switch result or error dict
    """
    logger.debug(f"Switching to process at {address}")
    try:
        # Import context handling functions
        from commands.command_handlers import save_process_context, restore_process_context
        
        # Save the current process context if requested
        prev_context = None
        if save_previous:
            prev_context = save_process_context(timeout_ms=10000)
            logger.debug(f"Saved previous process context: {prev_context}")
        
        # The .process command switches the current process context
        result = execute_command(f".process /r /p {address}", timeout_ms=20000)
        
        # If successful, add the previous context to the result
        if result and not isinstance(result, dict):
            # Add information about the previous context to the result
            if prev_context and save_previous:
                result += f"\n\nPrevious process context ({prev_context}) saved. Use restore_process_context to switch back."
        
        return result
    except Exception as e:
        logger.error(f"Error switching to process at '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def restore_process_context(ctx: Context, random_string: Optional[str] = None) -> Union[str, Dict[str, str]]:
    """
    Restore the previously saved process context.
    
    Args:
        ctx: The MCP context
        random_string: Optional string for compatibility
        
    Returns:
        Restoration result or error dict
    """
    logger.debug("Restoring previous process context")
    try:
        # Import context restoration function
        from commands.command_handlers import restore_process_context as restore_ctx
        
        # Try to restore the saved context
        success = restore_ctx(timeout_ms=15000)
        
        if success:
            return "Successfully restored the previous process context."
        else:
            return "No previous process context available to restore."
    except Exception as e:
        logger.error(f"Error restoring process context: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def list_threads(ctx: Context, random_string: Optional[str] = None) -> Union[str, Dict[str, str]]:
    """
    List all threads in the current process.
    
    Args:
        ctx: The MCP context
        random_string: Optional string for compatibility
        
    Returns:
        List of threads or error dict
    """
    logger.debug("Listing threads")
    try:
        # The !thread command lists thread information
        return execute_command("!thread", timeout_ms=30000)
    except Exception as e:
        logger.error(f"Error listing threads: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def switch_thread(ctx: Context, address: str) -> Union[str, Dict[str, str]]:
    """
    Switch to the specified thread by address.
    
    Args:
        ctx: The MCP context
        address: Address of the thread to switch to
        
    Returns:
        Switch result or error dict
    """
    logger.debug(f"Switching to thread at {address}")
    try:
        # The .thread command switches the current thread context
        return execute_command(f".thread {address}", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error switching to thread at '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_interrupt(ctx: Context, address: str) -> Union[str, Dict[str, str]]:
    """
    Get details about an interrupt at the specified address.
    
    Args:
        ctx: The MCP context
        address: Address of the interrupt to examine
        
    Returns:
        Interrupt information or error dict
    """
    logger.debug(f"Getting interrupt information for {address}")
    try:
        # Using display_type similar to hybrid_server approach
        return display_type("nt!_KINTERRUPT", address)
    except Exception as e:
        logger.error(f"Error getting interrupt information for '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_idt(ctx: Context, random_string: Optional[str] = None) -> Union[str, Dict[str, str]]:
    """
    Get the Interrupt Descriptor Table (IDT).
    
    Args:
        ctx: The MCP context
        random_string: Optional string for compatibility
        
    Returns:
        IDT information or error dict
    """
    logger.debug("Getting IDT")
    try:
        # The !idt command without parameters shows the entire Interrupt Descriptor Table
        return execute_command("!idt", timeout_ms=20000)
    except Exception as e:
        logger.error(f"Error getting IDT: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_object(ctx: Context, address: str) -> Union[str, Dict[str, str]]:
    """
    Get details about a kernel object at the specified address.
    
    Args:
        ctx: The MCP context
        address: Address of the kernel object to examine
        
    Returns:
        Object information or error dict
    """
    logger.debug(f"Getting object information for {address}")
    try:
        # The !object command shows information about a kernel object
        return execute_command(f"!object {address}", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting object information for '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_object_header(ctx: Context, address: str) -> Union[str, Dict[str, str]]:
    """
    Get details about a kernel object header at the specified address.
    
    Args:
        ctx: The MCP context
        address: Address of the object header to examine
        
    Returns:
        Object header information or error dict
    """
    logger.debug(f"Getting object header information for {address}")
    try:
        # The !objheader command shows information about a kernel object header
        return execute_command(f"!objheader {address}", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting object header information for '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_pte(ctx: Context, address: str) -> Union[str, Dict[str, str]]:
    """
    Get Page Table Entry (PTE) for the specified address.
    
    Args:
        ctx: The MCP context
        address: Address to examine the PTE for
        
    Returns:
        PTE information or error dict
    """
    logger.debug(f"Getting PTE for {address}")
    try:
        # The !pte command shows the Page Table Entry for a given address
        return execute_command(f"!pte {address}", timeout_ms=15000)
    except Exception as e:
        logger.error(f"Error getting PTE for '{address}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_handle(ctx: Context, address: str = "") -> Union[str, Dict[str, str]]:
    """
    Get information about a handle or all handles in the system.
    
    Args:
        ctx: The MCP context
        address: Optional handle address to examine (if empty, lists all handles)
        
    Returns:
        Handle information or error dict
    """
    logger.debug(f"Getting handle information for {address or 'all handles'}")
    try:
        cmd = "!handle"
        if address:
            cmd += f" {address}"
        else:
            # List all handles with summary information
            cmd += " 0 f"
            
        # Handle command can take a long time to execute
        return execute_command(cmd, timeout_ms=120000)
    except Exception as e:
        logger.error(f"Error getting handle information: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def search_symbols(ctx: Context, pattern: str) -> Union[str, Dict[str, str]]:
    """
    Search for symbols matching the specified pattern.
    
    Args:
        ctx: The MCP context
        pattern: Symbol pattern to search for
        
    Returns:
        List of matching symbols or error dict
    """
    logger.debug(f"Searching for symbols matching '{pattern}'")
    try:
        # The x command finds symbols matching a pattern
        return execute_command(f"x {pattern}", timeout_ms=30000)
    except Exception as e:
        logger.error(f"Error searching for symbols matching '{pattern}': {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_stack_trace(ctx: Context, thread_id: str = "") -> Union[str, Dict[str, str]]:
    """
    Get the stack trace for the current or specified thread.
    
    Args:
        ctx: The MCP context
        thread_id: Optional thread ID or address to get stack trace for
        
    Returns:
        Stack trace information or error dict
    """
    logger.debug(f"Getting stack trace for {thread_id or 'current thread'}")
    try:
        cmd = "kb"
        if thread_id:
            # First switch to the specified thread
            switch_result = execute_command(f".thread {thread_id}", timeout_ms=10000)
            if isinstance(switch_result, dict) and "error" in switch_result:
                return {"error": f"Failed to switch to thread {thread_id}: {switch_result['error']}"}
                
        # Get a detailed stack trace with all parameters
        return execute_command(f"{cmd} 100", timeout_ms=30000)
    except Exception as e:
        logger.error(f"Error getting stack trace: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

def main():
    """
    Main entry point for the WinDbg MCP Server.
    
    Configures the server based on environment variables and starts it.
    """
    logger.info("Starting WinDbg MCP Server")
    
    # Print available tools
    print("WinDbg MCP Server")
    print("================")
    print(f"Available tools ({len(AVAILABLE_TOOLS)}):")
    for tool_name in AVAILABLE_TOOLS:
        print(f"  - {tool_name}")
    
    # Configure server settings from environment variables
    transport = os.environ.get("MCP_TRANSPORT", "sse").lower()
    host = os.environ.get("MCP_HOST", "localhost")
    port = int(os.environ.get("MCP_PORT", "8000"))
    
    # Configure timeouts
    timeout = os.environ.get("FASTMCP_TIMEOUT", "120")
    os.environ["FASTMCP_TIMEOUT"] = timeout
    
    # Log server configuration
    logger.info(f"Server configuration:")
    logger.info(f"  - Transport: {transport}")
    logger.info(f"  - Host: {host}")
    logger.info(f"  - Port: {port}")
    logger.info(f"  - Timeout: {timeout} seconds")
    
    if transport == "sse":
        print(f"Server URL: http://{host}:{port}/sse")
        logger.info(f"MCP Server available at: http://{host}:{port}/sse")
    else:
        print(f"Server running with {transport} transport on port {port}")
    
    try:
        # Run the FastMCP server with the configured settings
        mcp.run(
            host=host,
            port=port,
            transport=transport
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        print("Server stopped by user. Goodbye!")
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        logger.error(traceback.format_exc())
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 