import logging
import re
from typing import Dict, Any, List, Optional
from .windbg_api import execute_command, execute_direct_command, DEFAULT_TIMEOUT_MS

logger = logging.getLogger(__name__)

class CommandRegistry:
    """Registry for specialized command handlers."""
    
    _handlers = {}
    
    @classmethod
    def register(cls, prefix):
        """
        Decorator to register a handler for commands with a specific prefix.
        
        Args:
            prefix: The command prefix (e.g., '!process')
        """
        def decorator(func):
            cls._handlers[prefix] = func
            return func
        return decorator
    
    @classmethod
    def get_handler(cls, command):
        """
        Get the handler for a command based on its prefix.
        
        Args:
            command: The full command string
        
        Returns:
            The handler function if registered, None otherwise
        """
        for prefix, handler in cls._handlers.items():
            if command.startswith(prefix):
                return handler
        return None


@CommandRegistry.register("!process")
def handle_process_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Enhanced handler for the !process command.
    
    Args:
        command: The process command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        Process information
    """
    # Direct execution with proper validation
    parts = command.split()
    
    # Check if we have both an address and flags
    if len(parts) >= 3:
        process_addr = parts[1]
        flags = parts[2]
        
        # Make sure the address looks valid (has hex digits)
        if not re.match(r'^[0-9a-fA-F`]+$', process_addr):
            return "Error: Invalid process address format. Use hexadecimal address."
        
        # Validate flags
        try:
            flag_val = int(flags, 16) if flags.startswith("0x") else int(flags)
            if flag_val < 0:
                return "Error: Process flags must be positive."
        except ValueError:
            return "Error: Invalid flags value. Use numeric value like '0x1f' or '7'."
    
    # Try to execute the command
    result = execute_direct_command(command, timeout_ms)
    
    # If empty or error, try alternative approaches
    if not result or "NONE" in result or result.strip() == "None":
        # Extract process address if it exists
        if len(parts) >= 2:
            process_addr = parts[1]
            
            # First try setting the process context
            proc_result = execute_direct_command(f".process /r /p {process_addr}", timeout_ms)
            
            if proc_result:
                # Then get process details
                details = execute_direct_command("!process", timeout_ms)
                return f"Process context set to {process_addr}:\n{proc_result}\n\nProcess Details:\n{details}"
            else:
                return f"Error: Could not set process context to {process_addr}. Check if the address is valid."
        else:
            # No address specified, list all processes
            return execute_direct_command("!process 0 0", timeout_ms)
    
    return result


@CommandRegistry.register("!dlls")
def handle_dlls_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Enhanced handler for the !dlls command.
    
    Args:
        command: The dlls command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        DLL information
    """
    # Try direct execution first
    result = execute_direct_command(command, timeout_ms)
    
    # Check for usage/errors
    if "Usage:" in result or not result:
        # Check if using -p flag
        if "-p" in command:
            # Extract the process address
            match = re.search(r'-p\s+(\S+)', command)
            if match:
                process_addr = match.group(1)
                
                # First set process context
                context_result = execute_direct_command(f".process /r /p {process_addr}", timeout_ms)
                
                # Then try regular !dlls command
                if context_result:
                    dll_result = execute_direct_command("!dlls", timeout_ms)
                    return f"Process context set to {process_addr}:\n{context_result}\n\nLoaded DLLs:\n{dll_result}"
                else:
                    return f"Error: Could not set process context to {process_addr}. Check if the address is valid."
        
        # Check if using -l flag
        if "-l" in command:
            # List modules using lm instead
            return "Using 'lm' command to list modules:\n" + execute_direct_command("lm", timeout_ms)
    
    return result


@CommandRegistry.register("!address")
def handle_address_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Enhanced handler for the !address command.
    
    Args:
        command: The address command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        Memory region information
    """
    # Direct execution first
    result = execute_direct_command(command, timeout_ms)
    
    # Check for errors
    if "Invalid arguments" in result or not result:
        # Handle different flags
        
        # For PAGE_EXECUTE_READWRITE flag
        if "-f:PAGE_EXECUTE_READWRITE" in command:
            # Try !vprot which gives memory protection info
            vprot_result = execute_direct_command("!vprot", timeout_ms)
            
            if vprot_result:
                # Filter the output for RWX regions (simplified)
                lines = vprot_result.splitlines()
                rwx_lines = [line for line in lines if "PAGE_EXECUTE_READWRITE" in line or "RWX" in line]
                
                if rwx_lines:
                    return "Memory regions with PAGE_EXECUTE_READWRITE:\n" + "\n".join(rwx_lines)
                else:
                    return "No PAGE_EXECUTE_READWRITE memory regions found."
            else:
                return "Could not get memory protection information."
        
        # For ExecuteEnable flag
        elif "-f:ExecuteEnable" in command:
            # Try with !address without flags first
            base_result = execute_direct_command("!address", timeout_ms)
            
            if base_result:
                # Filter for executable regions
                lines = base_result.splitlines()
                exec_lines = [line for line in lines if any(x in line for x in ["Execute", "IMAGE", "CODE"])]
                
                if exec_lines:
                    return "Executable memory regions:\n" + "\n".join(exec_lines)
                else:
                    return "No executable memory regions found."
            else:
                return "Could not get memory address information."
        
        # Provide usage help
        return """
Invalid !address arguments. Usage:
!address [options]

Common options:
  -summary        - display summary information
  -f:protect      - filter by protection (e.g. PAGE_EXECUTE_READWRITE)
  -p              - display per-process address info

Try using '!address -summary' for overview or '!address' without flags for detailed information.
"""
    
    return result


@CommandRegistry.register("!for_each_module")
def handle_for_each_module_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Enhanced handler for the !for_each_module command.
    
    Args:
        command: The for_each_module command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        Combined output from running the command on each module
    """
    # Extract the inner command
    parts = command.split(" ", 1)
    if len(parts) < 2:
        return "Error: Missing command to execute for each module"
    
    inner_command = parts[1].strip()
    
    # Get list of loaded modules
    modules_output = execute_direct_command("lm", timeout_ms)
    
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
        # Limit to first 20 modules to avoid excessive output
        if i >= 20:
            results.append("... output truncated, too many modules ...")
            break
            
        # Replace @#Base with the module address
        this_command = inner_command.replace("@#Base", module)
        
        # Handle special commands
        if "!modinfo" in this_command:
            # Use lmv command instead which provides detailed module info
            mod_name = module.split("`")[-1] if "`" in module else module
            module_detail = execute_direct_command(f"lmv {mod_name}", timeout_ms)
            
            if module_detail:
                results.append(f"Module {module} info:\n{module_detail}")
        else:
            # Execute the regular command
            output = execute_direct_command(this_command, timeout_ms//2)  # Reduce timeout per module
            
            if output and not output.startswith("Error:"):
                results.append(f"Module {module}:\n{output}")
    
    return "\n\n".join(results) if results else "No results returned from module commands"


@CommandRegistry.register("!handle")
def handle_handle_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Enhanced handler for the !handle command which can produce very large output.
    
    Args:
        command: The handle command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        Handle information with pagination if needed
    """
    # Increase timeout for this long-running command
    timeout_ms = max(timeout_ms, 60000)  # 60 seconds minimum
    
    # Check if we need to limit output
    parts = command.split()
    if len(parts) >= 3 and parts[2].lower() == "f":
        # This is a full dump which can be huge, add paging
        # Extract the process address if specified
        proc_addr = parts[3] if len(parts) > 3 else ""
        
        # Try a more targeted approach
        if proc_addr:
            # First set process context
            execute_direct_command(f".process /r /p {proc_addr}", timeout_ms)
            
            # Then get handle count first
            handle_count = execute_direct_command("!handle 0 0", timeout_ms)
            
            # Extract handle count from output
            count_match = re.search(r'(\d+) handles', handle_count)
            count = int(count_match.group(1)) if count_match else 0
            
            if count > 1000:
                # If too many handles, limit and warn
                result = execute_direct_command(f"!handle 0 1 {proc_addr}", timeout_ms)
                return f"Handle count: {count} (large number of handles)\n\nFirst 100 handles only:\n{result}\n\n(Truncated output to avoid excessive data)"
    
    # Direct execution
    result = execute_direct_command(command, timeout_ms)
    
    # Check for timeout or empty result
    if not result:
        return "Command timed out or returned no output. Try using '!handle 0 0' first to get handle count."
    
    # If result is too large, truncate
    if len(result) > 50000:  # ~50KB limit
        lines = result.splitlines()
        return "\n".join(lines[:500]) + "\n\n[Output truncated, too large to display completely]"
    
    return result


def dispatch_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Dispatch a command to the appropriate handler based on its prefix.
    
    Args:
        command: The command to execute
        timeout_ms: Timeout in milliseconds
    
    Returns:
        The command output
    """
    # Get a specialized handler if available
    handler = CommandRegistry.get_handler(command)
    
    if handler:
        logger.debug(f"Using specialized handler for command: {command}")
        return handler(command, timeout_ms)
    
    # Otherwise execute directly
    logger.debug(f"No specialized handler for command: {command}")
    return execute_direct_command(command, timeout_ms) 