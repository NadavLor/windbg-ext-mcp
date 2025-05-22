import logging
import re
import time
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
from .windbg_api import execute_command, execute_direct_command, DEFAULT_TIMEOUT_MS, TimeoutTracker, check_debugging_mode
import threading
import traceback

logger = logging.getLogger(__name__)

# Maximum retry attempts for commands that time out
MAX_RETRY_ATTEMPTS = 2

# Commands that should not be retried on timeout
NON_RETRYABLE_COMMANDS = [
    "g", "t", "p", "gu",  # Execution commands - don't retry as they change state
    ".restart", ".detach", ".kill",  # Control commands
    "q", "qq", "qd"        # Quit commands
]

# Commands that change process context
CONTEXT_CHANGING_COMMANDS = [
    ".process",
    "!process",
    "!dlls",
    "!handle"
]

# Error types for categorizing command failures
class ErrorType:
    TIMEOUT = "timeout"
    SYNTAX = "syntax"
    CONTEXT = "context"
    MEMORY = "memory"
    SYMBOL = "symbol"
    PERMISSION = "permission"
    CONNECTION = "connection"
    UNKNOWN = "unknown"

# Error recovery strategies
class RecoveryStrategy:
    RETRY = "retry"                # Simple retry with same parameters
    RETRY_WITH_TIMEOUT = "timeout" # Retry with increased timeout
    ALTERNATIVE = "alternative"    # Try an alternative command
    SIMPLIFY = "simplify"          # Try a simpler version of the command
    PREPROCESS = "preprocess"      # Prepare the environment before retrying 
    FALLBACK = "fallback"          # Use a predefined fallback command
    NONE = "none"                  # No recovery possible

# Common error patterns to identify error types
ERROR_PATTERNS = {
    ErrorType.TIMEOUT: [
        "timed out", "timeout", "not responding"
    ],
    ErrorType.SYNTAX: [
        "syntax error", "invalid parameter", "invalid argument", "unknown command",
        "invalid address", "incorrect syntax", "Usage:"
    ],
    ErrorType.CONTEXT: [
        "no process context", "invalid process", "unable to switch", "not in user mode",
        "not available in kernel mode", "process not accessible", "Implicit process is now"
    ],
    ErrorType.MEMORY: [
        "access violation", "memory could not be read", "memory could not be written",
        "memory region not accessible", "invalid memory", "memory at address",
        "could not read memory"
    ],
    ErrorType.SYMBOL: [
        "symbol not found", "unable to resolve", "no symbols loaded", "symbols not loaded",
        "no type information", "unknown symbol", "symbol file could not be found"
    ],
    ErrorType.PERMISSION: [
        "access denied", "insufficient privileges", "permission denied"
    ],
    ErrorType.CONNECTION: [
        "pipe not connected", "connection lost", "not connected", "no connection"
    ]
}

# Mapping of error types to recovery strategies
DEFAULT_RECOVERY_STRATEGIES = {
    ErrorType.TIMEOUT: RecoveryStrategy.RETRY_WITH_TIMEOUT,
    ErrorType.SYNTAX: RecoveryStrategy.SIMPLIFY,
    ErrorType.CONTEXT: RecoveryStrategy.PREPROCESS,
    ErrorType.MEMORY: RecoveryStrategy.ALTERNATIVE,
    ErrorType.SYMBOL: RecoveryStrategy.FALLBACK,
    ErrorType.PERMISSION: RecoveryStrategy.NONE,
    ErrorType.CONNECTION: RecoveryStrategy.RETRY,
    ErrorType.UNKNOWN: RecoveryStrategy.RETRY
}

# Alternative commands to try when the primary command fails
ALTERNATIVE_COMMANDS = {
    "!process": [
        # Format: (original_pattern, alternative_pattern, description)
        (r"!process\s+([a-fA-F0-9`]+)\s+[0-9]+", r".process /r /p \1", "Setting process context"),
        (r"!process\s+([a-fA-F0-9`]+)", r"!process \1 f", "Using full process details"),
        (r"!process", r"!process 0 0", "Listing all processes")
    ],
    "!dlls": [
        (r"!dlls\s+-p\s+([a-fA-F0-9`]+)", r".process /r /p \1; !dlls", "Setting process context first"),
        (r"!dlls", r"lm", "Listing loaded modules instead")
    ],
    "!thread": [
        (r"!thread\s+([a-fA-F0-9`]+)", r".thread \1; !thread", "Setting thread context first"),
        (r"!thread", r"~", "Listing all threads instead")
    ],
    "lm": [
        (r"lm\s+([a-z]+)\s+(.*)", r"lm", "Simplifying module listing"),
        (r"lm", r".chain", "Listing module load order")
    ],
    "dt": [
        (r"dt\s+(\S+)\s+([a-fA-F0-9`]+)", r"dt /v \1 \2", "Using verbose type display"),
        (r"dt\s+(\S+)", r"dt /t \1", "Displaying type information")
    ],
    "!peb": [
        (r"!peb", r"dt ntdll!_PEB @$peb", "Using direct PEB structure display")
    ],
    "!teb": [
        (r"!teb", r"dt ntdll!_TEB @$teb", "Using direct TEB structure display")
    ]
}

# Fallback messages for common errors
FALLBACK_MESSAGES = {
    ErrorType.TIMEOUT: "The command timed out. Try simplifying the command or increasing the timeout.",
    ErrorType.SYNTAX: "The command has incorrect syntax. Check the documentation for correct usage.",
    ErrorType.CONTEXT: "The command requires a specific process or thread context that is not available.",
    ErrorType.MEMORY: "Memory access error. The requested memory may not be accessible or valid.",
    ErrorType.SYMBOL: "Symbol resolution error. Check that symbols are loaded with '.reload' or '.sympath'.",
    ErrorType.PERMISSION: "Permission denied. The operation requires higher privileges.",
    ErrorType.CONNECTION: "Connection to the debugger was lost. Check that WinDbg is still running.",
    ErrorType.UNKNOWN: "An unknown error occurred. Check the debugger state and try again."
}

# Current process context tracking
_current_process_context = None
_context_lock = threading.Lock()

def get_current_process_context(timeout_ms: int = DEFAULT_TIMEOUT_MS) -> Optional[str]:
    """
    Get the current process context information from WinDbg.
    
    Args:
        timeout_ms: Timeout in milliseconds
    
    Returns:
        Process context string if available, None otherwise
    """
    result = execute_direct_command(".process", timeout_ms)
    if result and "Implicit process is" in result:
        # Extract the process address
        match = re.search(r'Implicit process is ([0-9a-fA-F`]+)', result)
        if match:
            return match.group(1)
    return None

def save_process_context(timeout_ms: int = DEFAULT_TIMEOUT_MS) -> Optional[str]:
    """
    Save the current process context for later restoration.
    
    Args:
        timeout_ms: Timeout in milliseconds
    
    Returns:
        The saved process context or None if it couldn't be determined
    """
    global _current_process_context
    with _context_lock:
        context = get_current_process_context(timeout_ms)
        if context:
            _current_process_context = context
            logger.debug(f"Saved process context: {_current_process_context}")
        return context

def restore_process_context(timeout_ms: int = DEFAULT_TIMEOUT_MS) -> bool:
    """
    Restore the previously saved process context.
    
    Args:
        timeout_ms: Timeout in milliseconds
    
    Returns:
        True if the context was restored successfully, False otherwise
    """
    global _current_process_context
    with _context_lock:
        if _current_process_context:
            logger.debug(f"Restoring process context to: {_current_process_context}")
            result = execute_direct_command(f".process /r /p {_current_process_context}", timeout_ms)
            return bool(result and "Implicit process is now" in result)
        return False

class ErrorRecoveryManager:
    """
    Manages error recovery for failed commands, providing alternative approaches
    and retry strategies based on the error type.
    """
    
    @staticmethod
    def identify_error_type(error_message: str) -> str:
        """
        Identify the type of error based on the error message.
        
        Args:
            error_message: The error message string
            
        Returns:
            The error type
        """
        if not error_message:
            return ErrorType.UNKNOWN
            
        error_message = error_message.lower()
        
        for error_type, patterns in ERROR_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in error_message:
                    return error_type
                    
        return ErrorType.UNKNOWN
        
    @staticmethod
    def get_recovery_strategy(error_type: str) -> str:
        """
        Get the appropriate recovery strategy for an error type.
        
        Args:
            error_type: The type of error
            
        Returns:
            The recovery strategy to use
        """
        return DEFAULT_RECOVERY_STRATEGIES.get(error_type, RecoveryStrategy.NONE)
        
    @staticmethod
    def get_alternative_commands(command: str) -> List[Tuple[str, str]]:
        """
        Get alternative commands to try when the primary command fails.
        
        Args:
            command: The original command string
            
        Returns:
            A list of tuples (alternative_command, description)
        """
        command_type = command.split()[0] if command else ""
        alternatives = []
        
        # Check for specific alternatives for this command type
        if command_type in ALTERNATIVE_COMMANDS:
            for pattern, alternative, description in ALTERNATIVE_COMMANDS[command_type]:
                # Check if the command matches the pattern
                match = re.match(pattern, command)
                if match:
                    # Replace backreferences in the alternative command
                    alt_cmd = alternative
                    for i, group in enumerate(match.groups(), 1):
                        alt_cmd = alt_cmd.replace(f"\\{i}", group)
                    
                    alternatives.append((alt_cmd, description))
        
        # Add generic alternatives for any command
        if command.startswith("!"):
            # For extension commands, try the help command
            help_cmd = f"{command_type} -?"
            alternatives.append((help_cmd, "Getting help for the command"))
            
        return alternatives
        
    @staticmethod
    def get_fallback_message(error_type: str) -> str:
        """
        Get a fallback message for an error type.
        
        Args:
            error_type: The type of error
            
        Returns:
            A fallback message
        """
        return FALLBACK_MESSAGES.get(error_type, FALLBACK_MESSAGES[ErrorType.UNKNOWN])
        
    @classmethod
    def execute_with_recovery(cls, command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS, 
                             max_retries: int = MAX_RETRY_ATTEMPTS) -> str:
        """
        Execute a command with error recovery strategies.
        
        Args:
            command: The command to execute
            timeout_ms: Timeout in milliseconds
            max_retries: Maximum number of retry attempts
            
        Returns:
            The command output or error message
        """
        original_command = command
        original_timeout = timeout_ms
        retry_count = 0
        tried_alternatives = set()
        error_type = ErrorType.UNKNOWN
        last_error = None
        
        # Track start time for performance monitoring
        start_time = time.time()
        
        while retry_count <= max_retries:
            try:
                # Execute the command with increased timeout for potentially long-running commands
                if command.startswith("!process") or command.startswith("!handle"):
                    # These commands can take longer, so increase the timeout
                    timeout_ms = max(timeout_ms, 60000)  # Minimum 60 seconds
                    logger.info(f"Using extended timeout of {timeout_ms}ms for command: {command}")
                
                # For commands that list a lot of data, we need to be patient
                if "0 0" in command and (command.startswith("!process") or command.startswith("!handle")):
                    logger.info(f"Command may return large dataset, setting timeout to 120 seconds: {command}")
                    timeout_ms = 120000  # 2 minutes for full listing commands
                
                # Execute the command
                result = execute_direct_command(command, timeout_ms)
                
                # Ensure result is not None to avoid unpacking errors
                if result is None:
                    logger.warning(f"Command '{command}' returned None, treating as timeout")
                    result = f"Error: Command timed out after {timeout_ms}ms"
                
                # Check for error in the result
                if isinstance(result, str) and result.startswith("Error:"):
                    # Identify the error type
                    error_type = cls.identify_error_type(result)
                    last_error = result
                    
                    # Get the recovery strategy
                    strategy = cls.get_recovery_strategy(error_type)
                    
                    # Apply the strategy
                    if strategy == RecoveryStrategy.RETRY and retry_count < max_retries:
                        logger.info(f"Retrying command '{command}' (attempt {retry_count+1}/{max_retries})")
                        retry_count += 1
                        continue
                        
                    elif strategy == RecoveryStrategy.RETRY_WITH_TIMEOUT and retry_count < max_retries:
                        # Increase timeout by 50% for next attempt
                        timeout_ms = int(timeout_ms * 1.5)
                        logger.info(f"Retrying command '{command}' with increased timeout {timeout_ms}ms (attempt {retry_count+1}/{max_retries})")
                        retry_count += 1
                        continue
                        
                    elif strategy == RecoveryStrategy.ALTERNATIVE:
                        # Try alternative commands
                        alternatives = cls.get_alternative_commands(original_command)
                        
                        for alt_cmd, description in alternatives:
                            if alt_cmd in tried_alternatives:
                                continue
                                
                            logger.info(f"Trying alternative command: {alt_cmd} ({description})")
                            tried_alternatives.add(alt_cmd)
                            
                            # Execute the alternative command
                            alt_result = execute_direct_command(alt_cmd, timeout_ms)
                            
                            # If the alternative succeeds, return its result
                            if alt_result and not alt_result.startswith("Error:"):
                                return f"Original command failed, using alternative approach: {description}\n\n{alt_result}"
                        
                        # If all alternatives fail, continue with other strategies
                        if retry_count < max_retries:
                            retry_count += 1
                            continue
                    
                    elif strategy == RecoveryStrategy.SIMPLIFY:
                        # Simplify the command and try again
                        command_parts = command.split()
                        if len(command_parts) > 1:
                            # Remove the last parameter
                            simplified = " ".join(command_parts[:-1])
                            if simplified not in tried_alternatives:
                                logger.info(f"Trying simplified command: {simplified}")
                                tried_alternatives.add(simplified)
                                command = simplified
                                
                                if retry_count < max_retries:
                                    retry_count += 1
                                    continue
                    
                    elif strategy == RecoveryStrategy.PREPROCESS:
                        # Specific preprocessing for different command types
                        if command.startswith("!process") or command.startswith("!dlls"):
                            # Try to get a valid process context first
                            process_list = execute_direct_command("!process 0 0", timeout_ms)
                            if process_list and not process_list.startswith("Error:"):
                                # Extract the first process address
                                match = re.search(r'PROCESS\s+([a-fA-F0-9`]+)', process_list)
                                if match and retry_count < max_retries:
                                    process_addr = match.group(1)
                                    logger.info(f"Setting process context to {process_addr} before retrying")
                                    execute_direct_command(f".process /r /p {process_addr}", timeout_ms)
                                    retry_count += 1
                                    continue
                    
                    # If we reach here, all recovery strategies have failed, or we've run out of retries
                    # Return a fallback message with the original error
                    fallback = cls.get_fallback_message(error_type)
                    return f"Error: {result.replace('Error: ', '')}\n\nSuggestion: {fallback}"
                
                # No error detected
                return result
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Exception while executing command '{command}': {e}")
                logger.debug(traceback.format_exc())
                
                # Identify error type from the exception
                error_type = cls.identify_error_type(last_error)
                
                # For connection errors, retry immediately
                if error_type == ErrorType.CONNECTION and retry_count < max_retries:
                    logger.info(f"Connection error, retrying immediately (attempt {retry_count+1}/{max_retries})")
                    retry_count += 1
                    continue
                
                # For timeout errors, retry with increased timeout
                if "timed out" in last_error.lower() and retry_count < max_retries:
                    timeout_ms = int(timeout_ms * 1.5)
                    logger.info(f"Timeout error, retrying with increased timeout {timeout_ms}ms (attempt {retry_count+1}/{max_retries})")
                    retry_count += 1
                    continue
                
                # If no specific recovery for this exception, try the default strategy
                strategy = cls.get_recovery_strategy(error_type)
                
                if strategy != RecoveryStrategy.NONE and retry_count < max_retries:
                    logger.info(f"Retrying after exception (strategy: {strategy}, attempt {retry_count+1}/{max_retries})")
                    retry_count += 1
                    continue
                
                # If all retries exhausted or no recovery strategy available
                elapsed_sec = time.time() - start_time
                fallback = cls.get_fallback_message(error_type)
                return f"Error: {last_error}\nCommand attempted {retry_count + 1} times over {elapsed_sec:.1f} seconds.\n\nSuggestion: {fallback}"
        
        # This should not be reached, but just in case
        return f"Error: Command failed after {max_retries} retry attempts."

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
    # Import check_debugging_mode from windbg_api
    from .windbg_api import check_debugging_mode
    
    # Check if we're in kernel-mode debugging
    is_kernel_mode = check_debugging_mode(timeout_ms)
    
    # Check for command line retrieval attempts in kernel mode
    if is_kernel_mode and ("-cmdline" in command or "-cl" in command):
        return "Error: Command line retrieval is not supported in kernel-mode debugging. User-mode process command lines are not accessible from kernel-mode. Use alternative commands like '!process' without -cmdline flag for basic process information."

    # Save current process context before changing it
    saved_context = save_process_context(timeout_ms)
    
    try:
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
        
        # Try to execute the command with error recovery
        result = ErrorRecoveryManager.execute_with_recovery(command, timeout_ms)
        
        # If empty or error, try alternative approaches
        if not result or "NONE" in result or result.strip() == "None":
            # Extract process address if it exists
            if len(parts) >= 2:
                process_addr = parts[1]
                
                # First try setting the process context
                proc_result = ErrorRecoveryManager.execute_with_recovery(f".process /r /p {process_addr}", timeout_ms)
                
                if proc_result and not proc_result.startswith("Error:"):
                    # Then get process details
                    details = ErrorRecoveryManager.execute_with_recovery("!process", timeout_ms)
                    return f"Process context set to {process_addr}:\n{proc_result}\n\nProcess Details:\n{details}"
                else:
                    return f"Error: Could not set process context to {process_addr}. Check if the address is valid."
            else:
                # No address specified, list all processes
                return ErrorRecoveryManager.execute_with_recovery("!process 0 0", timeout_ms)
        
        # For kernel-mode, append a note about limitations if appropriate
        if is_kernel_mode and result and not result.startswith("Error:"):
            result += "\n\nNOTE: In kernel-mode debugging, some user-mode process information (like command lines) is not accessible. Use user-mode debugging for complete process details."
        
        return result
    finally:
        # Restore the original process context if one was saved
        if saved_context:
            restore_process_context(timeout_ms)


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
    # Save current process context before changing it
    saved_context = save_process_context(timeout_ms)
    
    try:
        # Try direct execution first with error recovery
        result = ErrorRecoveryManager.execute_with_recovery(command, timeout_ms)
        
        # Check for usage/errors
        if "Usage:" in result or not result or result.startswith("Error:"):
            # Check if using -p flag
            if "-p" in command:
                # Extract the process address
                match = re.search(r'-p\s+(\S+)', command)
                if match:
                    process_addr = match.group(1)
                    
                    # First set process context with error recovery
                    context_result = ErrorRecoveryManager.execute_with_recovery(f".process /r /p {process_addr}", timeout_ms)
                    
                    # Then try regular !dlls command
                    if context_result and not context_result.startswith("Error:"):
                        dll_result = ErrorRecoveryManager.execute_with_recovery("!dlls", timeout_ms)
                        return f"Process context set to {process_addr}:\n{context_result}\n\nLoaded DLLs:\n{dll_result}"
                    else:
                        return f"Error: Could not set process context to {process_addr}. Check if the address is valid."
            
            # Check if using -l flag
            if "-l" in command:
                # List modules using lm instead
                return "Using 'lm' command to list modules:\n" + ErrorRecoveryManager.execute_with_recovery("lm", timeout_ms)
            
            # If still no result, try to list modules a different way
            if result.startswith("Error:") or not result:
                logger.info("!dlls command failed, trying 'lm' as alternative")
                modules_result = ErrorRecoveryManager.execute_with_recovery("lm", timeout_ms)
                if modules_result and not modules_result.startswith("Error:"):
                    return f"Using module listing instead of DLLs:\n{modules_result}"
        
        return result
    finally:
        # Restore the original process context if one was saved
        if saved_context:
            restore_process_context(timeout_ms)


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
    # Save current process context before changing it
    saved_context = save_process_context(timeout_ms)
    
    try:
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
    finally:
        # Restore the original process context if one was saved
        if saved_context:
            restore_process_context(timeout_ms)


@CommandRegistry.register(".reload")
def handle_reload_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Enhanced handler for the .reload command, which improves symbol loading in kernel mode.
    
    Args:
        command: The reload command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        Result of the symbol reload operation
    """
    from .windbg_api import check_debugging_mode
    
    # Check if we're in kernel-mode debugging
    is_kernel_mode = check_debugging_mode(timeout_ms)
    
    # Basic command without parameters - try to improve it
    if command == ".reload":
        logger.info("Enhancing basic .reload command with module-specific information")
        
        # Get module list first
        modules = execute_direct_command("lm", timeout_ms)
        if modules and not modules.startswith("Error:"):
            # Extract loaded modules and build better reload command
            # For kernel-mode, we need full module names with base addresses
            if is_kernel_mode:
                logger.info("Kernel-mode detected, using full module names and addresses for reload")
                # Parse module list for base addresses and names
                module_matches = []
                
                # Different module format patterns
                patterns = [
                    # Pattern for standard module listing with addr name format
                    r'([a-fA-F0-9`]+)\s+([a-zA-Z0-9_]+)',
                    # Pattern for alternate format with name addr format
                    r'([a-zA-Z0-9_]+)\s+([a-fA-F0-9`]+)'
                ]
                
                for line in modules.splitlines():
                    for pattern in patterns:
                        matches = re.findall(pattern, line)
                        if matches:
                            for match in matches:
                                # Check if it's addr,name or name,addr
                                if all(c in "0123456789abcdefABCDEF`" for c in match[0]):
                                    # addr,name format
                                    module_matches.append((match[1], match[0]))
                                else:
                                    # name,addr format
                                    module_matches.append((match[0], match[1]))
                
                if module_matches:
                    # Construct enhanced reload command with critical modules first
                    enhanced_cmd = ".reload"
                    
                    # Critical modules to prioritize
                    critical_modules = ["nt", "ntoskrnl", "hal", "win32k", "ndis", "tcpip"]
                    
                    # Add critical modules first (up to 5)
                    critical_found = 0
                    for name, addr in module_matches:
                        if name.lower() in critical_modules and critical_found < 5:
                            enhanced_cmd += f" /f {name}={addr}"
                            critical_found += 1
                    
                    # Then add some additional modules (up to 10 total)
                    additional = 0
                    for name, addr in module_matches:
                        if name.lower() not in critical_modules and additional < (10 - critical_found):
                            enhanced_cmd += f" /f {name}={addr}"
                            additional += 1
                    
                    result = execute_direct_command(enhanced_cmd, timeout_ms * 2)  # Double timeout for reload
                    if result:
                        return f"Enhanced reload command executed: {enhanced_cmd}\n\n{result}"
        
        # If improved approach didn't work or wasn't applicable, try original command
        return execute_direct_command(command, timeout_ms)
    
    # If there are specific parameters already, use the command as is
    return ErrorRecoveryManager.execute_with_recovery(command, timeout_ms)

def dispatch_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Dispatch a command to the appropriate handler based on its prefix.
    
    Args:
        command: The command to execute
        timeout_ms: Timeout in milliseconds
    
    Returns:
        The command output
    """
    # Extract command type for retry and timeout decisions
    command_parts = command.strip().split()
    command_type = command_parts[0] if command_parts else ""
    
    # Check if this command changes process context but isn't handled by a specialized handler
    needs_context_restoration = any(command.startswith(ctx_cmd) for ctx_cmd in CONTEXT_CHANGING_COMMANDS)
    specialized_handler = CommandRegistry.get_handler(command)
    
    # Only save context if it's a context-changing command without specialized handler
    # (specialized handlers already handle context restoration)
    saved_context = None
    if needs_context_restoration and not specialized_handler:
        saved_context = save_process_context(timeout_ms)
    
    try:
        # Check if command should be retried on timeout
        can_retry = not any(command_type == c for c in NON_RETRYABLE_COMMANDS)
        
        # Use adaptive timeout based on historical performance
        adjusted_timeout = TimeoutTracker.get_suggested_timeout(command)
        if adjusted_timeout > timeout_ms:
            logger.debug(f"Adjusted timeout for command '{command}' from {timeout_ms}ms to {adjusted_timeout}ms")
            timeout_ms = adjusted_timeout
        
        # Use specialized handler if available
        if specialized_handler:
            logger.debug(f"Using specialized handler for command: {command}")
            return specialized_handler(command, timeout_ms)
        
        # Otherwise execute with error recovery
        return ErrorRecoveryManager.execute_with_recovery(command, timeout_ms)
    finally:
        # Restore context if we saved it earlier and it's not a specialized handler
        # (which would handle its own context restoration)
        if saved_context and not specialized_handler:
            restore_process_context(timeout_ms) 