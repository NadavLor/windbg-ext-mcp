#!/usr/bin/env python
"""
WinDbg MCP Server implementation with FastMCP.

This server connects WinDbg to Cursor via the Model Context Protocol (MCP),
enabling LLM-assisted debugging of Windows kernel and user-mode applications.
"""
from typing import Any, Dict, List, Optional, Union
from fastmcp import FastMCP, Context
from commands import execute_command, display_type, display_memory, DEFAULT_TIMEOUT_MS
from commands.command_handlers import dispatch_command
import commands.windbg_api as windbg_api
import sys
import logging
import traceback
import os
import time
import re

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

# Initialize debugging mode detection before starting server
def initialize_debugging_mode():
    """Initialize debugging mode detection to prevent recursive loops later."""
    try:
        # Send raw commands directly to check the mode without going through validation
        logger.info("Detecting debugging mode on startup...")
        
        # Use the windbg_api methods directly with direct messaging
        message = {
            "type": "command",
            "command": "execute_command",
            "id": int(time.time() * 1000),
            "args": {
                "command": ".effmach",
                "timeout_ms": 5000
            }
        }
        
        try:
            response = windbg_api._send_message(message, 5000)
            result = response.get("output", "")
            
            # Check for kernel mode indicators
            if result and any(x in result.lower() for x in ["x64_kernel", "x86_kernel", "kernel mode"]):
                windbg_api._is_kernel_mode = True
                logger.info("✓ Kernel-mode debugging detected.")
                return
        except Exception as e:
            logger.warning(f"Error checking debugging mode via .effmach: {e}")
            
        # Try alternative command: !pcr (processor control region, kernel-only)
        message = {
            "type": "command",
            "command": "execute_command",
            "id": int(time.time() * 1000),
            "args": {
                "command": "!pcr",
                "timeout_ms": 5000
            }
        }
        
        try:
            response = windbg_api._send_message(message, 5000)
            result = response.get("output", "")
            
            # If !pcr works, we're in kernel mode
            if result and not (result.startswith("Error:") or "is not a recognized extension command" in result):
                windbg_api._is_kernel_mode = True
                logger.info("✓ Kernel-mode debugging detected via !pcr command.")
                return
        except Exception as e:
            logger.warning(f"Error checking debugging mode via !pcr: {e}")
        
        # Try a third check with !process 0 0 which works in kernel mode
        message = {
            "type": "command",
            "command": "execute_command",
            "id": int(time.time() * 1000),
            "args": {
                "command": "!process 0 0",
                "timeout_ms": 10000  # Longer timeout for process command
            }
        }
        
        try:
            response = windbg_api._send_message(message, 10000)
            result = response.get("output", "")
            
            # If !process 0 0 successfully shows PROCESS blocks, we're in kernel debugging
            if result and "PROCESS" in result and "SESSION" in result:
                windbg_api._is_kernel_mode = True
                logger.info("✓ Kernel-mode debugging detected via !process command.")
                return
        except Exception as e:
            logger.warning(f"Error checking debugging mode via !process: {e}")
            
        # If we get here, we're in user-mode
        windbg_api._is_kernel_mode = False
        logger.info("✓ User-mode debugging detected.")
    except Exception as e:
        # Set default mode to user-mode on error
        windbg_api._is_kernel_mode = False
        logger.warning(f"Failed to detect debugging mode: {e}. Defaulting to user-mode.")

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
    "get_stack_trace",
    "get_all_thread_stacks",
    "troubleshoot_symbols",
    "run_command_sequence",
    "analyze_exception"
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
    logger.debug(f"Getting stack trace for thread: {thread_id if thread_id else 'current'}")
    try:
        # Save the current thread context if we're going to switch
        saved_thread = None
        if thread_id:
            # Get current thread first
            current_thread = execute_command(".thread", timeout_ms=5000)
            if current_thread:
                match = re.search(r'Current thread is ([0-9a-fA-F`]+)', current_thread)
                if match:
                    saved_thread = match.group(1)
            
            # Switch to requested thread
            thread_result = execute_command(f".thread {thread_id}", timeout_ms=10000)
            if thread_result and "Invalid thread" in thread_result:
                return {"error": f"Invalid thread ID or address: {thread_id}"}
                
        # Get the stack trace
        result = execute_command("k 25", timeout_ms=15000)  # Show 25 frames
        
        # Restore original thread context if we switched
        if saved_thread:
            execute_command(f".thread {saved_thread}", timeout_ms=10000)
            
        return result
    except Exception as e:
        logger.error(f"Error getting stack trace: {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

@mcp.tool()
async def get_all_thread_stacks(ctx: Context, count: int = 5) -> Union[str, Dict[str, str]]:
    """
    Get stack traces for all threads in the current process, or the first N threads.
    This tool provides functionality similar to the "~* k" command but works in MCP.
    
    Args:
        ctx: The MCP context
        count: Maximum number of threads to show stacks for (default: 5)
        
    Returns:
        Combined stack traces or error dict
    """
    logger.debug(f"Getting stack traces for up to {count} threads")
    try:
        # First check if we're in kernel mode
        from commands.windbg_api import check_debugging_mode
        is_kernel_mode = check_debugging_mode()
        
        # Save current thread context
        current_thread = None
        thread_cmd_result = execute_command(".thread", timeout_ms=5000)
        if thread_cmd_result:
            match = re.search(r'Current thread is ([0-9a-fA-F`]+)', thread_cmd_result)
            if match:
                current_thread = match.group(1)
                logger.debug(f"Saved current thread context: {current_thread}")
        
        # Get the list of threads
        if is_kernel_mode:
            # In kernel mode, use !thread without params to list threads in the current process
            threads_output = execute_command("!thread", timeout_ms=30000)
        else:
            # In user mode, list all threads with ~
            threads_output = execute_command("~", timeout_ms=10000)
        
        if threads_output.startswith("Error:"):
            return {"error": threads_output.replace("Error: ", "")}
        
        # Parse thread IDs
        thread_ids = []
        
        if is_kernel_mode:
            # Parse kernel mode !thread output
            for match in re.finditer(r'THREAD\s+([a-fA-F0-9`]+)', threads_output):
                thread_ids.append(match.group(1))
        else:
            # Parse user mode ~ output
            for line in threads_output.splitlines():
                if re.match(r'^\s*\d+\s+Id:', line):
                    match = re.search(r'Id:\s+([a-fA-F0-9]+)', line)
                    if match:
                        thread_ids.append(match.group(1))
        
        if not thread_ids:
            return {"error": "No threads found in current process"}
        
        # Limit to requested count
        thread_ids = thread_ids[:min(count, len(thread_ids))]
        logger.debug(f"Found {len(thread_ids)} threads, showing stack for first {len(thread_ids)}")
        
        # Get stack for each thread
        results = []
        for i, tid in enumerate(thread_ids):
            try:
                # Switch to thread and get stack
                switch_result = execute_command(f".thread {tid}", timeout_ms=10000)
                
                # If thread switch failed, note the error and continue
                if switch_result and "Invalid thread" in switch_result:
                    results.append(f"Thread {tid}: Error - Could not switch to thread")
                    continue
                
                # Get stack trace with frame count
                stack = execute_command("k 15", timeout_ms=15000)  # Get 15 frames
                
                # Format the result
                if stack:
                    results.append(f"Thread {tid} stack trace:\n{stack}\n")
                else:
                    results.append(f"Thread {tid}: No stack trace available")
            except Exception as e:
                results.append(f"Thread {tid}: Error getting stack - {str(e)}")
        
        # Restore original thread context
        if current_thread:
            logger.debug(f"Restoring original thread context: {current_thread}")
            execute_command(f".thread {current_thread}", timeout_ms=10000)
        
        # Combine all stack traces
        if results:
            return "\n".join(results)
        else:
            return {"warning": "No thread stack traces could be collected"}
    except Exception as e:
        logger.error(f"Error getting all thread stacks: {e}")
        logger.error(traceback.format_exc())
        return {"error": f"Failed to get thread stacks: {str(e)}"}

@mcp.tool()
async def troubleshoot_symbols(ctx: Context) -> Union[str, Dict[str, str]]:
    """
    Run a comprehensive symbol troubleshooting procedure.
    
    Args:
        ctx: The MCP context
        
    Returns:
        Symbol diagnostics or error dict
    """
    logger.debug("Running comprehensive symbol troubleshooting")
    try:
        # First check if we're in kernel mode
        from commands.windbg_api import check_debugging_mode
        is_kernel_mode = check_debugging_mode()
        
        results = []
        results.append("===== SYMBOL TROUBLESHOOTING REPORT =====")
        results.append(f"Mode: {'Kernel-Mode' if is_kernel_mode else 'User-Mode'} Debugging")
        
        # 1. Check current symbol path
        results.append("\n=== Current Symbol Path ===")
        sympath = execute_command(".sympath", timeout_ms=10000)
        results.append(sympath.strip())
        
        # 2. Check symbol search path environment variable
        results.append("\n=== Symbol Environment ===")
        symenv = execute_command(".symopt", timeout_ms=10000)
        results.append(symenv.strip())
        
        # 3. Check if symbols are loaded for critical modules
        results.append("\n=== Critical Module Symbol Status ===")
        
        # Different critical modules based on mode
        critical_modules = ["nt", "ntoskrnl", "hal"] if is_kernel_mode else ["ntdll", "kernel32", "user32"]
        
        for module in critical_modules:
            results.append(f"\nChecking symbols for '{module}':")
            
            # Try to get module information
            module_info = execute_command(f"lmv m {module}", timeout_ms=15000)
            results.append(module_info.strip())
            
            # Check for loaded symbols
            if "No symbols loaded" in module_info:
                # Try to reload symbols for this module
                results.append(f"\n> Attempting to reload symbols for {module}...")
                
                # First get the base address if available
                base_addr = None
                for line in module_info.splitlines():
                    if "Base Address:" in line:
                        match = re.search(r'Base Address:\s+([a-fA-F0-9`]+)', line)
                        if match:
                            base_addr = match.group(1)
                
                # Build reload command
                reload_cmd = f".reload {module}"
                if base_addr:
                    reload_cmd += f"={base_addr}"
                
                reload_result = execute_command(reload_cmd, timeout_ms=30000)
                results.append(f"{reload_cmd} result:\n{reload_result.strip()}")
                
                # Check if reload helped
                module_info_after = execute_command(f"lmv m {module}", timeout_ms=15000)
                if "No symbols loaded" not in module_info_after and "Symbol file not found" not in module_info_after:
                    results.append(f"> Successfully loaded symbols for {module}")
                else:
                    results.append(f"> Could not load symbols for {module}")
        
        # 4. Enable symbol noisy mode and try to load some symbols
        results.append("\n=== Symbol Loading Diagnostics ===")
        
        # Enable verbose symbol loading
        sym_noisy = execute_command("!sym noisy", timeout_ms=5000)
        results.append("Enabled verbose symbol loading:")
        results.append(sym_noisy.strip())
        
        # Try to look up a common symbol
        if is_kernel_mode:
            test_symbol = execute_command("x nt!ExAllocatePool*", timeout_ms=20000)
        else:
            test_symbol = execute_command("x ntdll!Rtl*Heap*", timeout_ms=20000)
        
        results.append("\nSymbol lookup test:")
        results.append(test_symbol.strip())
        
        # 5. Check symbol load failures
        results.append("\n=== Symbol Verification ===")
        
        # Get symbol loaded modules
        lme_result = execute_command("lme", timeout_ms=15000)
        results.append("Modules with loaded symbols:")
        results.append(lme_result.strip())
        
        # Get symbol missing modules
        lmn_result = execute_command("lmn", timeout_ms=15000)
        results.append("\nModules missing symbols:")
        results.append(lmn_result.strip())
        
        # 6. Provide recommendations
        results.append("\n=== Recommendations ===")
        
        if "srv*" not in sympath and "_NT_SYMBOL_PATH" not in symenv:
            results.append("1. Set up symbol server path:")
            results.append("   .sympath+ srv*c:\\symbols*https://msdl.microsoft.com/download/symbols")
        
        if "No symbols loaded" in module_info:
            results.append("2. Try manual symbol reload for specific modules:")
            results.append("   .reload /f <module>=<base_address>")
        
        if is_kernel_mode:
            results.append("3. For kernel debugging, ensure kernel symbols match the target:")
            results.append("   .reload /f /k")
            results.append("   !lmi nt")
        
        results.append("4. To restore normal symbol settings after troubleshooting:")
        results.append("   !sym quiet")
        
        # Turn off noisy symbol mode when finished
        execute_command("!sym quiet", timeout_ms=5000)
        
        return "\n".join(results)
    except Exception as e:
        logger.error(f"Error in symbol troubleshooting: {e}")
        logger.error(traceback.format_exc())
        return {"error": f"Symbol troubleshooting failed: {str(e)}"}

@mcp.tool()
async def run_command_sequence(ctx: Context, commands: List[str]) -> Dict[str, List[Dict[str, str]]]:
    """
    Run a sequence of commands and return all results.
    This provides basic scripting capability to overcome dot-command limitations.
    
    Args:
        ctx: The MCP context
        commands: List of commands to execute in sequence
        
    Returns:
        Dictionary with results for each command
    """
    logger.debug(f"Running command sequence with {len(commands)} commands")
    results = []
    
    # First check if we're in kernel mode
    from commands.windbg_api import check_debugging_mode
    is_kernel_mode = check_debugging_mode()
    
    # Save current context if needed for restoration
    saved_process = None
    saved_thread = None
    
    # Check if we need to track context changes
    context_changing = any(cmd.startswith((".process", ".thread", "!process")) for cmd in commands)
    
    if context_changing:
        try:
            # Get and save current process context
            process_info = execute_command(".process", timeout_ms=5000)
            if process_info:
                match = re.search(r'Implicit process is ([0-9a-fA-F`]+)', process_info)
                if match:
                    saved_process = match.group(1)
                    logger.debug(f"Saved process context: {saved_process}")
            
            # Get and save current thread context
            thread_info = execute_command(".thread", timeout_ms=5000)
            if thread_info:
                match = re.search(r'Current thread is ([0-9a-fA-F`]+)', thread_info)
                if match:
                    saved_thread = match.group(1)
                    logger.debug(f"Saved thread context: {saved_thread}")
        except Exception as e:
            logger.warning(f"Error saving context before command sequence: {e}")
    
    # Process each command in sequence
    try:
        for i, cmd in enumerate(commands):
            if not cmd or not cmd.strip():
                results.append({
                    "command": cmd,
                    "result": "(empty command)",
                    "success": False
                })
                continue
                
            logger.info(f"Executing command {i+1}/{len(commands)}: {cmd}")
            
            try:
                # Check if this is a command that requires special handling
                if cmd.startswith(".logopen"):
                    # Logging commands aren't supported in MCP, provide feedback
                    results.append({
                        "command": cmd,
                        "result": "Logging commands (.logopen, .logappend, .logclose) are not supported in MCP. Use the run_command tool output for command logging.",
                        "success": False
                    })
                elif cmd.startswith(".foreach") or cmd.startswith(".for") or cmd.startswith(".while"):
                    # Loop commands aren't supported, provide feedback
                    results.append({
                        "command": cmd,
                        "result": "Loop commands (.foreach, .for, .while) are not supported in MCP. Use the run_command_sequence tool with multiple commands instead.",
                        "success": False
                    })
                elif cmd.startswith(".if") or cmd.startswith(".else"):
                    # Conditional commands aren't supported, provide feedback
                    results.append({
                        "command": cmd,
                        "result": "Conditional commands (.if, .else, .elsif) are not supported in MCP. Use the LLM's logic to determine which commands to run.",
                        "success": False
                    })
                elif cmd.startswith(".alias"):
                    # Alias commands aren't supported, provide feedback
                    results.append({
                        "command": cmd,
                        "result": "Alias commands (.alias) are not supported in MCP. Use direct commands instead.",
                        "success": False
                    })
                else:
                    # Normal command execution
                    result = execute_command(cmd, timeout_ms=30000)
                    success = not (result.startswith("Error:") if result else True)
                    
                    results.append({
                        "command": cmd,
                        "result": result,
                        "success": success
                    })
            except Exception as e:
                # Handle individual command errors without breaking the sequence
                logger.error(f"Error executing command '{cmd}': {e}")
                logger.error(traceback.format_exc())
                results.append({
                    "command": cmd,
                    "result": f"Error: {str(e)}",
                    "success": False
                })
    finally:
        # Restore context if we saved it
        if saved_process or saved_thread:
            logger.debug("Restoring saved debugging context after command sequence")
            try:
                if saved_process:
                    logger.debug(f"Restoring process context to {saved_process}")
                    execute_command(f".process /r /p {saved_process}", timeout_ms=15000)
                
                if saved_thread:
                    logger.debug(f"Restoring thread context to {saved_thread}")
                    execute_command(f".thread {saved_thread}", timeout_ms=10000)
            except Exception as e:
                logger.warning(f"Error restoring context after command sequence: {e}")
                # Add a warning to the results
                results.append({
                    "command": "(context restoration)",
                    "result": f"Warning: Failed to restore original debugging context: {e}",
                    "success": False
                })
    
    # Create a formatted summary for easier reading
    summary = "\n".join([
        f"Command {i+1}: {r['command']}\n"
        f"Success: {r['success']}\n"
        f"Result:\n"
        f"{r['result']}\n"
        f"{'-' * 40}"
        for i, r in enumerate(results)
    ])
    
    return {
        "results": results,
        "summary": summary,
        "mode": "kernel" if is_kernel_mode else "user",
        "success_count": sum(1 for r in results if r.get("success", False)),
        "total_count": len(results)
    }

@mcp.tool()
async def analyze_exception(ctx: Context) -> Union[str, Dict[str, str]]:
    """
    Analyze the current exception or bugcheck with useful context.
    This tool enhances the standard '!analyze -v' command with additional information and explanation.
    
    Args:
        ctx: The MCP context
        
    Returns:
        Analysis information or error dict
    """
    logger.debug("Running enhanced exception analysis")
    try:
        # First check if we're in kernel mode
        from commands.windbg_api import check_debugging_mode
        is_kernel_mode = check_debugging_mode()
        
        # Setup results array
        results = []
        results.append("===== EXCEPTION ANALYSIS =====")
        
        # Run the analyze command for detailed information
        analysis = execute_command("!analyze -v", timeout_ms=60000)
        
        # Check for manual break-in vs real exception
        if "Break instruction exception" in analysis or "80000003" in analysis:
            results.append("*** MANUAL BREAK-IN DETECTED ***")
            results.append("This is a manual break-in or debugger pause, not a real bugcheck/exception.")
            results.append("For real bugcheck analysis, examine crash dumps or trigger a test bugcheck.")
            results.append("\nSummary: User initiated debugger break-in")
            results.append("\n--- Basic analysis information follows ---\n")
        elif "EXCEPTION_CODE:" in analysis or "BUGCHECK_CODE:" in analysis:
            # Real exception/bugcheck detected
            if is_kernel_mode:
                results.append("*** KERNEL BUGCHECK DETECTED ***")
            else:
                results.append("*** USER-MODE EXCEPTION DETECTED ***")
                
        # Include the standard analysis
        results.append(analysis)
        
        # Add supplementary information based on mode and exception type
        bugcheck_code = None
        exception_code = None
        
        # Extract bugcheck code if present
        bugcheck_match = re.search(r'BUGCHECK_CODE:\s+(0x[0-9a-fA-F]+)', analysis)
        if bugcheck_match:
            bugcheck_code = bugcheck_match.group(1)
            
        # Extract exception code if present
        exception_match = re.search(r'EXCEPTION_CODE:\s+(0x[0-9a-fA-F]+)', analysis)
        if exception_match:
            exception_code = exception_match.group(1)
        
        # Add supplementary analysis based on what we found
        results.append("\n===== SUPPLEMENTARY ANALYSIS =====")
        
        if is_kernel_mode and bugcheck_code:
            # Get additional information about the bugcheck
            results.append(f"\nBugcheck code {bugcheck_code} details:")
            bugcheck_info = execute_command(f"!bugcheck {bugcheck_code}", timeout_ms=10000)
            results.append(bugcheck_info.strip())
            
            # Add stack trace of the current thread
            results.append("\nCurrent thread stack trace:")
            stack_trace = execute_command("kb 20", timeout_ms=15000)  # 20 frames
            results.append(stack_trace.strip())
            
            # Try to get triage dump information
            results.append("\nTriage analysis of current bugcheck:")
            triage = execute_command("!triage", timeout_ms=20000)
            results.append(triage.strip())
            
        elif not is_kernel_mode and exception_code:
            # Get additional information about the exception
            results.append(f"\nException code {exception_code} details:")
            # Look for common exception codes
            if "c0000005" in exception_code.lower():
                results.append("This is an access violation exception (EXCEPTION_ACCESS_VIOLATION).")
                results.append("Common causes include null pointer dereference, use-after-free, buffer overflow.")
                
                # Check for memory at the exception address
                if "ExceptionAddress:" in analysis:
                    address_match = re.search(r'ExceptionAddress:\s+([0-9a-fA-F`]+)', analysis)
                    if address_match:
                        exception_address = address_match.group(1)
                        results.append(f"\nMemory near exception address {exception_address}:")
                        memory_info = execute_command(f"db {exception_address} L40", timeout_ms=10000)
                        results.append(memory_info.strip())
            
            # Add current stack and registers
            results.append("\nRegisters at time of exception:")
            registers = execute_command("r", timeout_ms=10000)
            results.append(registers.strip())
            
            results.append("\nStack trace at time of exception:")
            ex_stack = execute_command("kb 20", timeout_ms=15000)
            results.append(ex_stack.strip())
        
        # Add recommendations for next debugging steps
        results.append("\n===== RECOMMENDED NEXT STEPS =====")
        
        if "Break instruction exception" in analysis or "80000003" in analysis:
            results.append("Since this is a manual break-in, you may want to:")
            results.append("1. Set breakpoints at points of interest")
            results.append("2. Use 'g' to continue execution")
            results.append("3. Examine process and thread information with '!process 0 0'")
        elif is_kernel_mode and bugcheck_code:
            results.append("For this kernel bugcheck, recommended steps:")
            results.append("1. Check stack trace of the bugcheck to identify failing component")
            results.append("2. Review memory near key pointers in the bugcheck parameters")
            results.append("3. Use '!pool' on suspect memory addresses to check for corruptions")
            results.append("4. Consider using '.reload' to ensure all symbols are loaded")
        elif not is_kernel_mode and exception_code:
            results.append("For this user-mode exception, recommended steps:")
            results.append("1. Check the call stack to find the function that caused the exception")
            results.append("2. Examine variables and memory at the exception location")
            results.append("3. Consider setting breakpoints before the exception location")
            
        return "\n".join(results)
    except Exception as e:
        logger.error(f"Error during exception analysis: {e}")
        logger.error(traceback.format_exc())
        return {"error": f"Exception analysis failed: {str(e)}"}

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
        # Initialize debugging mode detection before starting the server
        # This prevents recursive loops when mode detection is needed later
        logger.info("Initializing debugging mode detection...")
        initialize_debugging_mode()
        mode = "Kernel-Mode" if windbg_api._is_kernel_mode else "User-Mode"
        logger.info(f"Debugging mode initialized: {mode}")
        print(f"Debugging mode: {mode}")
        
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