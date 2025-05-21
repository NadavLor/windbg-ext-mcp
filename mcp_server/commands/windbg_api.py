import json
import time
import os
import re
from typing import Any, Dict, List, Optional, Union
import win32pipe
import win32file
import win32api
import win32event
import pywintypes
import msvcrt
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Default timeout for command execution in milliseconds
DEFAULT_TIMEOUT_MS = 30000  # Increased from 10s to 30s

# Pipe name for communication with the WinDBG extension
PIPE_NAME = r"\\.\pipe\windbgmcp"

def _send_message(message: Dict[str, Any], timeout_ms: int = DEFAULT_TIMEOUT_MS) -> Dict[str, Any]:
    """
    Send a message to the WinDBG extension via the named pipe.
    
    Args:
        message: The message to send as a dictionary
        timeout_ms: Timeout in milliseconds
        
    Returns:
        The response from the extension as a dictionary
    
    Raises:
        ConnectionError: If connection to the extension fails
        TimeoutError: If the command times out
        RuntimeError: If the command fails
    """
    # Convert the message to a JSON string
    message_str = json.dumps(message) + "\n"
    message_bytes = message_str.encode('utf-8')
    
    logger.debug(f"Sending message to WinDBG extension: {message_str}")
    
    try:
        # Try to open the named pipe
        try:
            handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None
            )
            logger.debug(f"Opened pipe {PIPE_NAME} successfully")
        except pywintypes.error as e:
            error_code = e.args[0]
            error_message = e.args[2] if len(e.args) > 2 else str(e)
            
            if error_code == 2:  # ERROR_FILE_NOT_FOUND
                logger.error(f"Named pipe {PIPE_NAME} not found. Is WinDBG running with the extension loaded?")
                raise ConnectionError(f"WinDBG extension pipe not found: {PIPE_NAME}. Make sure WinDBG is running with the extension loaded.")
            elif error_code == 5:  # ERROR_ACCESS_DENIED
                logger.error(f"Access denied when opening pipe {PIPE_NAME}. Check permissions.")
                raise ConnectionError(f"Access denied when connecting to WinDBG extension. Check permissions.")
            elif error_code == 231:  # ERROR_PIPE_BUSY
                logger.error(f"Pipe {PIPE_NAME} is busy. Another client might be connected.")
                raise ConnectionError(f"WinDBG extension pipe is busy. Another client might be connected.")
            else:
                logger.error(f"Failed to open pipe {PIPE_NAME}: [Error {error_code}] {error_message}")
                raise ConnectionError(f"Failed to connect to WinDBG extension: [Error {error_code}] {error_message}")
        
        # Set the pipe to wait for timeout_ms
        timeout = timeout_ms
        
        # Write the message to the pipe
        try:
            win32file.WriteFile(handle, message_bytes)
            logger.debug(f"Wrote {len(message_bytes)} bytes to pipe")
        except pywintypes.error as e:
            error_code = e.args[0]
            error_message = e.args[2] if len(e.args) > 2 else str(e)
            logger.error(f"Failed to write to pipe: [Error {error_code}] {error_message}")
            win32file.CloseHandle(handle)
            raise ConnectionError(f"Failed to send message to WinDBG extension: [Error {error_code}] {error_message}")
        
        # Read the response from the pipe
        response_data = b''
        read_attempts = 0
        max_read_attempts = 10  # Safeguard against infinite loops
        
        while read_attempts < max_read_attempts:
            try:
                # Use ReadFile with a timeout
                hr, data = win32file.ReadFile(handle, 4096)
                if not data:
                    logger.debug("No more data to read")
                    break
                response_data += data
                logger.debug(f"Read {len(data)} bytes from pipe")
                if response_data.endswith(b'\n'):
                    logger.debug("End of message detected (newline)")
                    break
                read_attempts += 1
            except pywintypes.error as e:
                error_code = e.args[0]
                error_message = e.args[2] if len(e.args) > 2 else str(e)
                
                if error_code == 232:  # Pipe is closed
                    logger.debug("Pipe was closed while reading")
                    break
                elif error_code == 109:  # ERROR_BROKEN_PIPE
                    logger.error("Pipe connection was broken")
                    raise ConnectionError("WinDBG extension pipe connection was broken")
                else:
                    logger.error(f"Error reading from pipe: [Error {error_code}] {error_message}")
                    raise ConnectionError(f"Error reading from WinDBG extension: [Error {error_code}] {error_message}")
                
        # Close the handle
        try:
            win32file.CloseHandle(handle)
            logger.debug("Closed pipe handle")
        except Exception as e:
            logger.warning(f"Error closing handle: {e}")
        
        # Convert the response to a dictionary
        if not response_data:
            logger.warning("Received empty response from WinDBG extension")
            return {"status": "error", "error_message": "Empty response from WinDBG extension. Make sure WinDBG is running and not paused."}
            
        try:
            response_str = response_data.decode('utf-8').strip()
            logger.debug(f"Decoded response: {response_str}")
            response = json.loads(response_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response: {e}")
            logger.error(f"Raw response: {response_data!r}")
            
            # Try to extract any readable text from the response
            try:
                readable_text = response_data.decode('utf-8', errors='replace')
                return {"status": "error", "error_message": f"Invalid JSON response from WinDBG extension: {readable_text[:100]}..."}
            except:
                return {"status": "error", "error_message": f"Invalid JSON response from WinDBG extension: {e}"}
        
        # Check for errors
        if response.get("type") == "error":
            error_message = response.get("error_message", "Unknown error")
            logger.error(f"WinDBG extension returned error: {error_message}")
            raise RuntimeError(f"WinDBG command failed: {error_message}")
        
        logger.debug(f"Received successful response: {response}")
        return response
    except pywintypes.error as e:
        error_code = e.args[0]
        error_message = e.args[2] if len(e.args) > 2 else str(e)
        
        if error_code == 258:  # ERROR_WAIT_TIMEOUT
            logger.error(f"Command timed out after {timeout_ms}ms")
            raise TimeoutError(f"WinDBG command timed out after {timeout_ms}ms. The debugging session might be paused.")
        elif error_code in (109, 233):  # ERROR_BROKEN_PIPE, ERROR_PIPE_NOT_CONNECTED
            logger.error("Pipe not connected")
            raise ConnectionError(f"Failed to connect to WinDBG extension: Pipe not connected or broken")
        else:
            logger.error(f"Pipe communication error: [Error {error_code}] {error_message}")
            raise ConnectionError(f"Failed to communicate with WinDBG extension: [Error {error_code}] {error_message}")
     
def execute_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Execute a WinDBG command via the extension.
    
    Args:
        command: The WinDBG command to execute
        timeout_ms: Timeout in milliseconds
        
    Returns:
        The output of the command as a string
    """
    logger.debug(f"Executing WinDBG command: {command}")
    
    try:
        # Use the command dispatcher from command_handlers
        from .command_handlers import dispatch_command
        return dispatch_command(command, timeout_ms)
    except ImportError:
        # Fallback to direct execution if command_handlers isn't available
        logger.warning("Command dispatcher not available, using direct execution")
        return execute_direct_command(command, timeout_ms)

def handle_for_each_module_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Handle the !for_each_module command by implementing it in Python
    instead of relying on the extension command.
    
    Args:
        command: The for_each_module command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        The combined output of running the command on each module
    """
    # Extract the inner command to run on each module
    parts = command.split(" ", 1)
    if len(parts) < 2:
        return "Error: Missing command to execute for each module"
    
    inner_command = parts[1].strip()
    
    # Get list of loaded modules
    modules_output = execute_command("lm", timeout_ms)
    
    # Parse module list
    modules = []
    for line in modules_output.splitlines():
        if line and "start" not in line and not line.startswith("Browse"):
            # Extract module address from the start of the line
            parts = line.split(None, 1)
            if parts:
                modules.append(parts[0])
    
    if not modules:
        return "No modules found in current context"
    
    # Execute the command for each module
    results = []
    for i, module in enumerate(modules):
        # Skip after processing 20 modules to avoid timeout
        if i >= 20:
            results.append("... output truncated, too many modules ...")
            break
            
        # Replace @#Base with the module address
        this_command = inner_command.replace("@#Base", module)
        
        # If the command contains '!modinfo', handle it specially
        if "!modinfo" in this_command:
            module_info = f"Module {module} info:"
            # Use lm command to get module details instead
            mod_name = this_command.split()[-1] if len(this_command.split()) > 1 else module
            module_detail = execute_command(f"lmv {mod_name}", timeout_ms)
            results.append(f"{module_info}\n{module_detail}")
        else:
            # Execute the command
            output = execute_command(this_command, timeout_ms//2)  # Reduce timeout per module
            if output and not output.startswith("Error:"):
                results.append(f"Module {module}:\n{output}")
    
    return "\n\n".join(results)

def handle_process_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Handle the !process command with special processing.
    
    Args:
        command: The process command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        The process information
    """
    # Execute the command directly first
    result = execute_direct_command(command, timeout_ms)
    
    # If it failed, try an alternative approach
    if not result or "NONE" in result or result.strip() == "None":
        # Extract process address
        parts = command.split()
        if len(parts) >= 2:
            process_addr = parts[1]
            # Try with .process command instead
            proc_result = execute_direct_command(f".process /r /p {process_addr}", timeout_ms)
            
            if proc_result:
                return f"Process context set to {process_addr}:\n{proc_result}\n\nProcess Details:\n" + \
                       execute_direct_command("!process", timeout_ms)
    
    return result

def handle_dlls_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Handle the !dlls command with special processing.
    
    Args:
        command: The dlls command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        The DLL information
    """
    # Direct execution first
    result = execute_direct_command(command, timeout_ms)
    
    # If we get usage info, the command syntax might be wrong
    if "Usage:" in result or not result:
        # Check if using -p flag for process
        if "-p" in command:
            # Extract the process address
            match = re.search(r'-p\s+(\S+)', command)
            if match:
                process_addr = match.group(1)
                # First set process context
                context_result = execute_direct_command(f".process /r /p {process_addr}", timeout_ms)
                if context_result:
                    # Then execute a simple !dlls
                    dll_result = execute_direct_command("!dlls", timeout_ms)
                    return f"Process context set to {process_addr}:\n{context_result}\n\nLoaded DLLs:\n{dll_result}"
        
        # If no -p flag or we couldn't extract the address
        return result
    
    return result

def handle_address_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Handle the !address command with special processing for flags.
    
    Args:
        command: The address command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        Memory region information
    """
    # Direct execution first
    result = execute_direct_command(command, timeout_ms)
    
    # If we get invalid arguments
    if "Invalid arguments" in result or not result:
        # For PAGE_EXECUTE_READWRITE flag
        if "-f:PAGE_EXECUTE_READWRITE" in command:
            # Try !vprot instead
            return "Using !vprot to find executable memory regions:\n" + \
                   execute_direct_command("!vprot", timeout_ms)
        
        # For ExecuteEnable flag
        elif "-f:ExecuteEnable" in command:
            # Get all memory regions and filter manually
            all_mem = execute_direct_command("!address", timeout_ms)
            if all_mem:
                # A very simplified filtering approach - in a real implementation
                # we would do more sophisticated parsing
                lines = all_mem.splitlines()
                exec_lines = [line for line in lines if "Execute" in line]
                
                if exec_lines:
                    return "Executable memory regions:\n" + "\n".join(exec_lines)
                else:
                    return "No executable memory regions found"
    
    return result

def execute_direct_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Execute a command directly without special handling.
    
    Args:
        command: The WinDBG command to execute
        timeout_ms: Timeout in milliseconds
    
    Returns:
        The output of the command
    """
    message = {
        "type": "command",
        "command": "execute_command",
        "id": int(time.time() * 1000),
        "args": {
            "command": command,
            "timeout_ms": timeout_ms
        }
    }
    
    try:
        response = _send_message(message, timeout_ms)
        return response.get("output", "")
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return f"Error: {str(e)}"

def display_type(type_name: str, address: str = "", timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Display information about a type or structure.
    This is a wrapper around the WinDbg "dt" command.
    
    Args:
        type_name: The name of the type or structure
        address: Optional address to display the structure at
        timeout_ms: Timeout in milliseconds
        
    Returns:
        The output of the dt command
    """
    logger.debug(f"Displaying type {type_name} at address {address}")
    
    message = {
        "type": "command",
        "command": "dt",
        "id": int(time.time() * 1000),
        "args": {
            "type_name": type_name,
            "address": address,
            "timeout_ms": timeout_ms
        }
    }
    
    try:
        response = _send_message(message, timeout_ms)
        result = response.get("output", "")
        logger.debug(f"Type displayed successfully, result length: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"Error displaying type: {e}")
        return f"Error: {str(e)}"
     
def display_memory(address: str, length: int = 32, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Display memory at the specified address.
    This is a wrapper around the WinDbg "dd" command.
    
    Args:
        address: The address to display memory at
        length: The number of dwords to display
        timeout_ms: Timeout in milliseconds
        
    Returns:
        The output of the dd command
    """
    logger.debug(f"Displaying memory at {address}, length {length}")
    
    message = {
        "type": "command",
        "command": "dd",
        "id": int(time.time() * 1000),
        "args": {
            "address": address,
            "length": length,
            "timeout_ms": timeout_ms
        }
    }
    
    try:
        response = _send_message(message, timeout_ms)
        result = response.get("output", "")
        logger.debug(f"Memory displayed successfully, result length: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"Error displaying memory: {e}")
        return f"Error: {str(e)}" 