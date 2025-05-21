import json
import time
import os
import re
import threading
from typing import Any, Dict, List, Optional, Union, Tuple
import win32pipe
import win32file
import win32api
import win32event
import pywintypes
import msvcrt
import logging
from datetime import datetime
import traceback

"""
WinDbg API module for the MCP Server.

This module provides functionality to communicate with the WinDBG extension via a named pipe
and execute commands in the debugger.

Key features:
- Command validation system to prevent errors and security issues
- Adaptive timeout tracking for commands
- Specialized command handlers for common debugging operations
- Process context management to maintain debugging state
- Error handling and reporting

The command validation system ensures that:
1. Dangerous commands are blocked (quit, kill, etc.)
2. Command parameters are properly formatted
3. Commands with special requirements are validated further
4. Helpful error messages are provided when validation fails

Implementation notes:
- Commands are categorized by type for specific validation
- Each category has its own validation function
- Some commands bypass validation (internal context management)
- Unit tests in tests/test_command_validation.py verify the system
"""

# Configure logging
logger = logging.getLogger(__name__)

# Default timeout for command execution in milliseconds
DEFAULT_TIMEOUT_MS = 30000  # Increased from 10s to 30s

# Pipe name for communication with the WinDBG extension
PIPE_NAME = r"\\.\pipe\windbgmcp"

# Command validation constants
MAX_COMMAND_LENGTH = 4096  # Maximum length for any command
RESTRICTED_COMMANDS = [
    "q", "qq", "qd",           # Quit commands (could close WinDbg)
    ".kill", ".detach",        # Commands that terminate debugging session
    ".dump", ".dumpexr",       # Dump file commands without proper parameters
    ".logopen", ".logclose",   # Logging commands without parameters
    ".cls",                    # Clear screen command
    ".connect",                # Connect to remote targets
    ".cmdtree",                # Command tree modifications
    ".load",                   # Loading extensions without proper validation
    ".unload",                 # Unloading extensions
    "!peb -full"               # High-volume output command
]

# Safe command prefixes that are always allowed
SAFE_COMMAND_PREFIXES = [
    ".echo",        # Echo/print text
    "lm",           # List modules
    "x",            # Examine symbols
    "dt",           # Display type
    "dd", "dw", "db", "dq",  # Display memory
    "!process",     # Process information
    "!dlls",        # DLL information
    "!handle",      # Handle information
    "k",            # Stack trace
    "!peb",         # Process Environment Block
    "!teb",         # Thread Environment Block
    "r",            # Registers
    "u",            # Disassembly
    "!address",     # Memory regions
]

# Command categories for validation
class CommandCategory:
    MEMORY = "memory"
    EXECUTION = "execution"
    PROCESS = "process"
    MODULE = "module"
    THREAD = "thread"
    BREAKPOINT = "breakpoint"
    SYSTEM = "system"
    EXTENSION = "extension"
    REGISTER = "register"
    UNKNOWN = "unknown"

def validate_command(command: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a WinDbg command for safety and correctness.
    
    Args:
        command: The command to validate
        
    Returns:
        A tuple of (is_valid, error_message)
        where is_valid is True if the command is valid, False otherwise
        and error_message is None if valid, or an error message if invalid
    """
    # Check for empty command
    if not command or not command.strip():
        return False, "Empty command"
        
    # Trim the command
    command = command.strip()
    
    # Check command length
    if len(command) > MAX_COMMAND_LENGTH:
        return False, f"Command too long ({len(command)} chars, max {MAX_COMMAND_LENGTH})"
    
    # Check for restricted commands
    for restricted in RESTRICTED_COMMANDS:
        if command == restricted or command.startswith(restricted + " "):
            return False, f"Command '{restricted}' is restricted for security reasons"
    
    # Pass-through for safe commands
    for safe_prefix in SAFE_COMMAND_PREFIXES:
        if command == safe_prefix or command.startswith(safe_prefix + " "):
            return True, None
    
    # Special validation for specific command categories
    command_type = get_command_category(command)
    
    # Validate based on command category
    if command_type == CommandCategory.MEMORY:
        return validate_memory_command(command)
    elif command_type == CommandCategory.EXECUTION:
        return validate_execution_command(command)
    elif command_type == CommandCategory.BREAKPOINT:
        return validate_breakpoint_command(command)
    elif command_type == CommandCategory.EXTENSION:
        return validate_extension_command(command)
    
    # For uncategorized commands, perform basic syntax validation
    if command.startswith(".") and not any(command.startswith(safe) for safe in SAFE_COMMAND_PREFIXES):
        # Meta commands need extra scrutiny
        return validate_meta_command(command)
    
    # By default, allow the command but log it
    logger.info(f"Allowing command with default validation: {command}")
    return True, None

def get_command_category(command: str) -> str:
    """Determine the category of a WinDbg command."""
    command = command.strip().lower()
    
    # Memory access commands
    if command.startswith(("d", "e", "f", "s")):
        return CommandCategory.MEMORY
    
    # Execution control
    elif command.startswith(("g", "p", "t", "gu", "wt")):
        return CommandCategory.EXECUTION
    
    # Breakpoints
    elif command.startswith(("bp", "ba", "bu", "bm", "bc", "bd", "be", "bl")):
        return CommandCategory.BREAKPOINT
    
    # Process related
    elif command.startswith((".process", "!process")):
        return CommandCategory.PROCESS
    
    # Thread related
    elif command.startswith((".thread", "!thread")):
        return CommandCategory.THREAD
    
    # Module related
    elif command.startswith(("lm", "!dlls", "!lmi")):
        return CommandCategory.MODULE
    
    # Register operations
    elif command.startswith("r"):
        return CommandCategory.REGISTER
    
    # Extension commands
    elif command.startswith("!"):
        return CommandCategory.EXTENSION
    
    # Meta commands
    elif command.startswith("."):
        return CommandCategory.SYSTEM
    
    return CommandCategory.UNKNOWN

def validate_memory_command(command: str) -> Tuple[bool, Optional[str]]:
    """Validate memory-related commands."""
    # Check for common memory command patterns
    if re.match(r'^d[bdwqpcfu](\s+[a-fA-F0-9`x]+)(\s+L[a-fA-F0-9`x]+)?$', command):
        return True, None
    
    # Simple address pattern
    if re.match(r'^d[bdwqpcfu]\s+[a-fA-F0-9`x]+$', command):
        return True, None
    
    # Allow memory search
    if re.match(r'^s\s+-[a-z]\s+', command):
        return True, None
    
    # If not matching expected patterns, log but allow
    logger.warning(f"Memory command with non-standard format: {command}")
    return True, None

def validate_execution_command(command: str) -> Tuple[bool, Optional[str]]:
    """Validate execution control commands."""
    # Validate step/trace commands
    if command in ['p', 't', 'g', 'gu']:
        return True, None
    
    # Validate commands with addresses
    if re.match(r'^g(\s+[a-fA-F0-9`x]+)?$', command):
        return True, None
    
    # For 'wt' command, require specific pattern
    if command.startswith('wt'):
        if len(command) > 3 and not re.match(r'^wt(\s+[a-fA-F0-9`x]+)?\s+', command):
            return False, "Invalid syntax for 'wt' command"
        return True, None
    
    # Log but allow other execution commands
    logger.warning(f"Execution command with non-standard format: {command}")
    return True, None

def validate_breakpoint_command(command: str) -> Tuple[bool, Optional[str]]:
    """Validate breakpoint commands."""
    # Breakpoint listing is always safe
    if command == 'bl':
        return True, None
    
    # Basic breakpoint commands
    if re.match(r'^bp\s+[a-fA-F0-9`x]+$', command) or re.match(r'^bp\s+\w+![\w:]+$', command):
        return True, None
    
    # Clear breakpoints
    if re.match(r'^bc\s+\*?$', command) or re.match(r'^bc\s+[0-9]+$', command):
        return True, None
    
    # Enable/disable breakpoints
    if re.match(r'^(be|bd)\s+[0-9]+$', command):
        return True, None
    
    # Log but allow other breakpoint commands
    logger.warning(f"Breakpoint command with non-standard format: {command}")
    return True, None

def validate_extension_command(command: str) -> Tuple[bool, Optional[str]]:
    """Validate extension commands."""
    # Extract extension name
    parts = command.split(None, 1)
    extension_name = parts[0].lstrip('!')
    
    # Check for potentially dangerous extensions
    dangerous_extensions = ['!ioctrl', '!wmitrace', '!wdfkd', '!ndiskd']
    if any(extension_name.startswith(dangerous) for dangerous in dangerous_extensions):
        return False, f"Extension command '{extension_name}' is potentially dangerous and requires manual validation"
    
    # Allow other extension commands
    return True, None

def validate_meta_command(command: str) -> Tuple[bool, Optional[str]]:
    """Validate meta commands."""
    # Extract meta command name
    parts = command.split(None, 1)
    meta_command = parts[0].lower()
    
    # These commands have potential for system impact
    dangerous_meta_commands = ['.dump', '.dumpcab', '.dumpexr', '.logopen', '.logappend', 
                               '.load', '.unload', '.connect', '.server', '.kill', '.detach']
    
    if any(meta_command == dangerous for dangerous in dangerous_meta_commands):
        return False, f"Meta command '{meta_command}' is potentially dangerous and requires manual validation"
    
    # For specific meta commands that are generally safe but need parameter validation
    if meta_command == '.printf':
        return True, None
        
    if meta_command == '.logclose':
        return True, None
        
    if meta_command == '.echo':
        return True, None
        
    # Allow other safe meta commands, but log them
    logger.info(f"Allowing meta command: {command}")
    return True, None

# Command timeout tracking for adaptive timeouts
class TimeoutTracker:
    """Track command execution times to adaptively adjust timeouts"""
    
    _command_stats = {}  # Track average time per command type
    _lock = threading.Lock()
    
    @classmethod
    def record_execution(cls, command_type, execution_time_ms):
        """Record the execution time for a command type"""
        with cls._lock:
            if command_type not in cls._command_stats:
                cls._command_stats[command_type] = {
                    'count': 1,
                    'avg_time': execution_time_ms,
                    'max_time': execution_time_ms
                }
            else:
                stats = cls._command_stats[command_type]
                # Update moving average
                stats['avg_time'] = (stats['avg_time'] * stats['count'] + execution_time_ms) / (stats['count'] + 1)
                stats['count'] += 1
                stats['max_time'] = max(stats['max_time'], execution_time_ms)
    
    @classmethod
    def get_suggested_timeout(cls, command):
        """Get a suggested timeout for a command based on historical performance"""
        # Extract the command type (first word)
        command_parts = command.strip().split()
        if not command_parts:
            return DEFAULT_TIMEOUT_MS
            
        command_type = command_parts[0]
        
        with cls._lock:
            if command_type in cls._command_stats:
                stats = cls._command_stats[command_type]
                
                # Use a combination of average and max time with buffer
                suggested_timeout = int(max(
                    stats['avg_time'] * 2,  # Double the average time
                    min(stats['max_time'] * 1.5, 120000)  # 1.5x max time with cap at 2 minutes
                ))
                
                # Ensure reasonable bounds
                return max(DEFAULT_TIMEOUT_MS, min(suggested_timeout, 300000))  # Between 30s and 5min
            
            # For specific known long-running commands, use preset timeout values
            if command_type == "!handle":
                return 120000  # 2 minutes
            elif command_type == "!process" and "0 0" in command:
                return 60000   # 1 minute
            elif command_type == "lm" or command_type == ".chain":
                return 60000   # 1 minute
                
            return DEFAULT_TIMEOUT_MS

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
    command = message.get("args", {}).get("command", "<unknown>")
    command_type = command.split()[0] if command and " " in command else command
    handle = None
    
    # Record start time for tracking
    start_time = datetime.now()
    
    try:
        # Convert the message to a JSON string
        message_str = json.dumps(message) + "\n"
        message_bytes = message_str.encode('utf-8')
        
        logger.debug(f"Sending message to WinDBG extension: {message_str}")
        
        # Set a client-side timeout slightly longer than the command timeout to account for transmission delays
        client_timeout_ms = timeout_ms + 10000
        
        # Adjust timeout for known long-running commands
        if command and (command.startswith("!process 0 0") or 
                        command.startswith("!handle 0 0") or 
                        command.startswith("!dlls")):
            logger.info(f"Increasing client-side timeout for long-running command: {command}")
            client_timeout_ms = max(client_timeout_ms, 180000)  # 3 minutes for long-running commands
        
        # Create the pipe name
        pipe_name = PIPE_NAME
        
        # Try to open the pipe with a shorter timeout first
        try:
            handle = win32file.CreateFile(
                pipe_name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                win32file.FILE_FLAG_OVERLAPPED,
                None
            )
            
            logger.debug(f"Connected to WinDBG extension pipe: {pipe_name}")
        except pywintypes.error as e:
            error_code = e.args[0]
            
            if error_code == 2:  # ERROR_FILE_NOT_FOUND
                logger.error(f"Pipe {pipe_name} not found. WinDBG extension might not be running.")
                raise ConnectionError(f"WinDBG extension not connected. Pipe {pipe_name} not found.")
            elif error_code == 231:  # ERROR_PIPE_BUSY
                logger.warning(f"Pipe {pipe_name} busy, waiting for availability...")
                
                # Wait for pipe to become available
                if not win32pipe.WaitNamedPipe(pipe_name, 5000):  # 5 second timeout
                    logger.error("Timed out waiting for pipe availability")
                    raise ConnectionError("Timed out waiting for pipe availability. WinDBG extension might be busy or disconnected.")
                
                # Try again to open the pipe
                handle = win32file.CreateFile(
                    pipe_name,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    win32file.FILE_FLAG_OVERLAPPED,
                    None
                )
                
                logger.debug(f"Connected to WinDBG extension pipe after wait: {pipe_name}")
            else:
                logger.error(f"Failed to connect to pipe: [Error {error_code}] {e.args[2] if len(e.args) > 2 else str(e)}")
                raise ConnectionError(f"Failed to connect to WinDBG extension: {str(e)}")
        
        # Create events for overlapped I/O
        overlapped_write = pywintypes.OVERLAPPED()
        overlapped_write.hEvent = win32event.CreateEvent(None, True, False, None)
        
        overlapped_read = pywintypes.OVERLAPPED()
        overlapped_read.hEvent = win32event.CreateEvent(None, True, False, None)
        
        # Write the message to the pipe
        try:
            logger.debug(f"Writing {len(message_bytes)} bytes to pipe")
            # Using WriteFile in a way that handles possible exceptions
            try:
                win32file.WriteFile(handle, message_bytes, overlapped_write)
            except Exception as e:
                logger.error(f"Exception during WriteFile: {e}")
                if handle:
                    win32file.CancelIo(handle)
                    win32file.CloseHandle(handle)
                raise ConnectionError(f"Failed to write to WinDBG extension pipe: {e}")
            
            # Wait for write to complete with timeout
            result = win32event.WaitForSingleObject(overlapped_write.hEvent, 10000)  # 10 second timeout for writes
            if result != win32event.WAIT_OBJECT_0:
                # Write timed out or failed
                if handle:
                    win32file.CancelIo(handle)
                    win32file.CloseHandle(handle)
                logger.error(f"Write to pipe timed out or failed. Result: {result}")
                raise ConnectionError(f"Failed to send message to WinDBG extension: Write timed out")
                
            # Get number of bytes written
            try:
                logger.debug("Getting overlapped result for write")
                result = win32file.GetOverlappedResult(handle, overlapped_write, False)
                logger.debug(f"GetOverlappedResult for write returned: {result!r}")
                
                # Handle different return types from GetOverlappedResult
                if isinstance(result, tuple):
                    if len(result) >= 2:
                        _, bytes_written = result
                    else:
                        logger.warning(f"Unexpected tuple format from GetOverlappedResult: {result!r}")
                        bytes_written = len(message_bytes)  # Assume success
                else:
                    bytes_written = result
                
                logger.debug(f"Wrote {bytes_written} bytes to pipe")
                
                if bytes_written != len(message_bytes):
                    logger.error(f"Incomplete write: wrote {bytes_written}/{len(message_bytes)} bytes")
                    raise ConnectionError(f"Failed to send full message to WinDBG extension")
            except TypeError as e:
                logger.error(f"TypeError handling GetOverlappedResult: {e}")
                # If we can't determine bytes written, log but continue
                logger.warning("Could not determine number of bytes written, continuing anyway")
            except Exception as e:
                logger.error(f"Unexpected error getting overlapped result: {e}")
                logger.error(traceback.format_exc())
                # Continue anyway, we'll see if we get a response
                
        except pywintypes.error as e:
            error_code = e.args[0]
            error_message = e.args[2] if len(e.args) > 2 else str(e)
            logger.error(f"Failed to write to pipe: [Error {error_code}] {error_message}")
            if handle:
                win32file.CloseHandle(handle)
            raise ConnectionError(f"Failed to send message to WinDBG extension: [Error {error_code}] {error_message}")
        
        # Read the response from the pipe
        response_data = b''
        buffer_size = 8192  # Increased buffer size for larger responses
        
        # Start time for response reading
        read_start_time = datetime.now()
        
        # Keep reading until we get a complete JSON object or timeout
        while True:
            try:
                # Check if we've exceeded our timeout
                elapsed_ms = int((datetime.now() - read_start_time).total_seconds() * 1000)
                if elapsed_ms > client_timeout_ms:
                    if handle:
                        win32file.CancelIo(handle)
                        win32file.CloseHandle(handle)
                    logger.error(f"Read operation timed out after {elapsed_ms}ms")
                    raise TimeoutError(f"WinDBG command '{command_type}' timed out after {elapsed_ms}ms. The command might be taking too long or the debugging session might be paused.")
                
                # Compute remaining timeout
                remaining_timeout = max(1000, client_timeout_ms - elapsed_ms)
                
                # Read data from the pipe (with remaining timeout)
                logger.debug("Calling ReadFile")
                try:
                    hr, data = win32file.ReadFile(handle, buffer_size, overlapped_read)
                    logger.debug(f"ReadFile returned: hr={hr}, data length={len(data) if data else 0}")
                except Exception as e:
                    logger.error(f"Exception during ReadFile: {e}")
                    if "The pipe has been ended" in str(e):
                        # This can happen if the pipe was closed right after a successful write
                        # It might indicate that the command executed quickly with no output
                        logger.warning("Pipe ended during read, possible normal termination")
                        break
                    raise
                
                # Wait for read to complete with timeout
                logger.debug(f"Waiting for read to complete with timeout {remaining_timeout}ms")
                result = win32event.WaitForSingleObject(overlapped_read.hEvent, remaining_timeout)
                logger.debug(f"WaitForSingleObject returned: {result}")
                
                if result == win32event.WAIT_OBJECT_0:
                    # Read completed successfully
                    try:
                        # Store the data we might have already received from ReadFile
                        read_data = data if data else b''
                        logger.debug("Getting overlapped result for read")
                        
                        try:
                            result = win32file.GetOverlappedResult(handle, overlapped_read, False)
                            logger.debug(f"GetOverlappedResult for read returned: {result!r}")
                        
                            # Handle different return types from GetOverlappedResult
                            if isinstance(result, tuple) and len(result) >= 3:
                                err, bytes_read, read_data = result
                                logger.debug(f"Unpacked tuple result: err={err}, bytes_read={bytes_read}, data length={len(read_data) if read_data else 0}")
                            else:
                                # If result is just bytes_read or tuple with less than 3 elements
                                if isinstance(result, tuple):
                                    if len(result) >= 2:
                                        err, bytes_read = result
                                    else:
                                        logger.warning(f"Unexpected tuple format from GetOverlappedResult: {result!r}")
                                        bytes_read = 0
                                else:
                                    bytes_read = result
                                logger.debug(f"Using data from ReadFile with bytes_read={bytes_read}")
                                # Use the data we already have from ReadFile
                        except Exception as e:
                            logger.error(f"Error getting overlapped result: {e}")
                            logger.error(traceback.format_exc())
                            # Try to recover
                            bytes_read = len(read_data) if read_data else 0
                            logger.debug(f"Using estimated bytes_read={bytes_read}")
                        
                        if bytes_read > 0:
                            logger.debug(f"Read {bytes_read} bytes from pipe")
                            response_data += read_data[:bytes_read]
                            
                            # Check if the response is complete (ends with newline)
                            if response_data.endswith(b'\n'):
                                logger.debug("Complete response received")
                                break
                        else:
                            # Zero bytes read usually means pipe was closed
                            logger.warning("Zero bytes read from pipe, connection might be closed")
                            if handle:
                                win32file.CloseHandle(handle)
                                handle = None
                            # If we already have some data, consider it complete
                            if response_data:
                                logger.debug("Using partial response data")
                                break
                            raise ConnectionError("Pipe connection closed by WinDBG extension")
                    except pywintypes.error as e:
                        error_code = e.args[0]
                        if error_code == 109:  # ERROR_BROKEN_PIPE
                            logger.warning("Pipe connection broken")
                            if handle:
                                win32file.CloseHandle(handle)
                                handle = None
                            # If we already have some data, consider it complete
                            if response_data:
                                logger.debug("Using partial response data despite broken pipe")
                                break
                            raise ConnectionError("Pipe connection broken")
                        else:
                            raise
                
                elif result == win32event.WAIT_TIMEOUT:
                    # Read operation timed out
                    if handle:
                        win32file.CancelIo(handle)
                        win32file.CloseHandle(handle)
                        handle = None
                    elapsed_ms = int((datetime.now() - read_start_time).total_seconds() * 1000)
                    logger.error(f"Read operation timed out after {elapsed_ms}ms")
                    raise TimeoutError(f"Timed out waiting for response from WinDBG extension after {elapsed_ms}ms")
                
                else:
                    # Other error
                    if handle:
                        win32file.CancelIo(handle)
                        win32file.CloseHandle(handle)
                        handle = None
                    logger.error(f"Wait for read failed. Result: {result}")
                    raise ConnectionError(f"Failed to read response from WinDBG extension: Wait failed with result {result}")
                
            except pywintypes.error as e:
                error_code = e.args[0]
                error_message = e.args[2] if len(e.args) > 2 else str(e)
                
                # Check for common pipe errors
                if error_code == 109:  # ERROR_BROKEN_PIPE
                    logger.warning("Pipe connection broken")
                    if handle:
                        win32file.CloseHandle(handle)
                        handle = None
                    # If we already have some data, consider it complete
                    if response_data:
                        logger.debug("Using partial response data despite broken pipe")
                        break
                    raise ConnectionError("Pipe connection broken")
                elif error_code == 232:  # ERROR_NO_DATA
                    # No data available, wait a bit and retry
                    logger.debug("No data available, waiting before retry")
                    time.sleep(0.1)
                    continue
                else:
                    logger.error(f"Failed to read from pipe: [Error {error_code}] {error_message}")
                    if handle:
                        win32file.CloseHandle(handle)
                        handle = None
                    raise ConnectionError(f"Failed to read response from WinDBG extension: [Error {error_code}] {error_message}")
        
        # Close the pipe handle
        if handle:
            win32file.CloseHandle(handle)
            handle = None
        
        # Record end time and calculate total duration
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        logger.debug(f"Command '{command_type}' took {duration_ms}ms to execute")
        
        # Record this timing for future timeout suggestions
        TimeoutTracker.record_execution(command_type, duration_ms)
        
        # Decode and parse the response
        try:
            response_str = response_data.decode('utf-8').strip()
            logger.debug(f"Received response: {response_str}")
            response = json.loads(response_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse response as JSON: {e}")
            logger.debug(f"Raw response: {response_data!r}")
            raise RuntimeError(f"Invalid response from WinDBG extension: {str(e)}")
        
        # Check for errors
        if response.get("status") == "error":
            error_message = response.get("error", "Unknown error")
            error_category = response.get("error_category", "unknown")
            error_code = response.get("error_code", 0)
            suggestion = response.get("suggestion", "")
            
            # Build a detailed error message
            detailed_error = f"WinDBG command failed: {error_message}"
            
            if error_category != "unknown":
                detailed_error += f"\nError category: {error_category}"
                
            if error_code != 0:
                detailed_error += f"\nError code: 0x{error_code:08X}"
                
            if suggestion:
                detailed_error += f"\nSuggestion: {suggestion}"
            
            logger.error(detailed_error)
            raise RuntimeError(detailed_error)
        
        logger.debug(f"Received successful response: {response}")
        return response
        
    except pywintypes.error as e:
        error_code = e.args[0]
        error_message = e.args[2] if len(e.args) > 2 else str(e)
        
        if error_code == 258:  # ERROR_WAIT_TIMEOUT
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Command '{command_type}' timed out after {elapsed_ms}ms")
            raise TimeoutError(f"WinDBG command '{command_type}' timed out after {elapsed_ms}ms. The debugging session might be paused.")
        elif error_code in (109, 233):  # ERROR_BROKEN_PIPE, ERROR_PIPE_NOT_CONNECTED
            logger.error("Pipe not connected")
            raise ConnectionError(f"Failed to connect to WinDBG extension: Pipe not connected or broken")
        else:
            logger.error(f"Pipe communication error: [Error {error_code}] {error_message}")
            raise ConnectionError(f"Failed to communicate with WinDBG extension: [Error {error_code}] {error_message}")
    except TimeoutError:
        elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        logger.error(f"Command '{command_type}' timed out after {elapsed_ms}ms")
        raise
    except Exception as e:
        elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        logger.error(f"Unexpected error executing command '{command_type}' ({elapsed_ms}ms): {e}")
        logger.error(traceback.format_exc())
        raise RuntimeError(f"Error executing WinDBG command: {str(e)}")
    finally:
        # Ensure handle is closed
        if handle:
            try:
                win32file.CloseHandle(handle)
            except Exception as e:
                logger.warning(f"Error closing handle: {e}")

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
    
    # Validate the command before execution
    is_valid, error_message = validate_command(command)
    if not is_valid:
        logger.warning(f"Invalid command rejected: {command} - Reason: {error_message}")
        return f"Error: Command validation failed - {error_message}"
    
    # Use adaptive timeout based on command type and history
    adjusted_timeout = TimeoutTracker.get_suggested_timeout(command)
    if adjusted_timeout > timeout_ms:
        logger.debug(f"Adjusted timeout for command '{command}' from {timeout_ms}ms to {adjusted_timeout}ms based on historical performance")
        timeout_ms = adjusted_timeout
    
    try:
        # Try to use the command dispatcher from command_handlers
        try:
            from .command_handlers import dispatch_command
            result = dispatch_command(command, timeout_ms)
            
            # Ensure we have a string result
            if result is None:
                return "No output received from command"
            elif isinstance(result, dict):
                # Handle dictionary result (error case)
                if "error" in result:
                    return f"Error: {result['error']}"
                return str(result)
            
            return result
        except ImportError as e:
            # Fallback to direct execution if command_handlers isn't available
            logger.warning(f"Command dispatcher not available, using direct execution: {e}")
            return execute_direct_command(command, timeout_ms)
    except Exception as e:
        logger.error(f"Error in execute_command for '{command}': {e}")
        logger.error(traceback.format_exc())
        return f"Error: {str(e)}"

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
    # Validate the command format
    if not command.startswith("!process"):
        return "Error: Invalid process command format. Expected '!process' prefix."
    
    # Extract and validate process address if present
    parts = command.split()
    if len(parts) >= 2:
        process_addr = parts[1]
        # Validate address format (hex)
        if not re.match(r'^[0-9a-fA-F`x]+$', process_addr):
            return "Error: Invalid process address format. Expected hexadecimal value."
    
    # If flags are present, validate them
    if len(parts) >= 3:
        flags = parts[2]
        try:
            if flags.startswith("0x"):
                flag_val = int(flags, 16)
            else:
                flag_val = int(flags)
                
            # Check for reasonable flag values
            if flag_val < 0 or flag_val > 0xFF:
                return "Error: Process flag value out of range (0-0xFF)."
        except ValueError:
            return "Error: Invalid process flag format. Expected numeric value."
            
    # Save the original process context
    original_context = None
    current_context_result = execute_direct_command(".process", timeout_ms)
    if current_context_result and "Implicit process is" in current_context_result:
        match = re.search(r'Implicit process is ([0-9a-fA-F`]+)', current_context_result)
        if match:
            original_context = match.group(1)
            logger.debug(f"Saved original process context: {original_context}")
    
    try:
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
    finally:
        # Restore the original process context if we changed it
        if original_context:
            logger.debug(f"Restoring original process context: {original_context}")
            restore_result = execute_direct_command(f".process /r /p {original_context}", timeout_ms)
            if not restore_result:
                logger.warning(f"Failed to restore original process context to {original_context}")

def handle_dlls_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Handle the !dlls command with special processing.
    
    Args:
        command: The dlls command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        The DLL information
    """
    # Validate the command format
    if not command.startswith("!dlls"):
        return "Error: Invalid DLLs command format. Expected '!dlls' prefix."
    
    # Validate specific flags
    if "-p" in command:
        # Extract and validate process address
        match = re.search(r'-p\s+([0-9a-fA-F`x]+)', command)
        if not match:
            return "Error: Invalid process address format with -p flag. Expected hexadecimal value."
    
    # Save the original process context
    original_context = None
    current_context_result = execute_direct_command(".process", timeout_ms)
    if current_context_result and "Implicit process is" in current_context_result:
        match = re.search(r'Implicit process is ([0-9a-fA-F`]+)', current_context_result)
        if match:
            original_context = match.group(1)
            logger.debug(f"Saved original process context: {original_context}")
            
    try:
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
    finally:
        # Restore the original process context if we changed it
        if original_context:
            logger.debug(f"Restoring original process context: {original_context}")
            restore_result = execute_direct_command(f".process /r /p {original_context}", timeout_ms)
            if not restore_result:
                logger.warning(f"Failed to restore original process context to {original_context}")

def handle_address_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Handle the !address command with special processing for flags.
    
    Args:
        command: The address command string
        timeout_ms: Timeout in milliseconds
    
    Returns:
        Memory region information
    """
    # Save the original process context if we might change it
    original_context = None
    if "-p" in command:
        current_context_result = execute_direct_command(".process", timeout_ms)
        if current_context_result and "Implicit process is" in current_context_result:
            match = re.search(r'Implicit process is ([0-9a-fA-F`]+)', current_context_result)
            if match:
                original_context = match.group(1)
                logger.debug(f"Saved original process context: {original_context}")
    
    try:
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
    finally:
        # Restore the original process context if we changed it
        if original_context:
            logger.debug(f"Restoring original process context: {original_context}")
            restore_result = execute_direct_command(f".process /r /p {original_context}", timeout_ms)
            if not restore_result:
                logger.warning(f"Failed to restore original process context to {original_context}")

def execute_direct_command(command: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """
    Execute a command directly without special handling.
    
    Args:
        command: The WinDBG command to execute
        timeout_ms: Timeout in milliseconds
    
    Returns:
        The output of the command
    """
    # Validate the command before execution
    # Note: Skip validation for internal commands used by special handlers
    if not (command.startswith(".process") or command == "!process" or command == ".thread"):
        is_valid, error_message = validate_command(command)
        if not is_valid:
            logger.warning(f"Invalid command rejected in direct execution: {command} - Reason: {error_message}")
            return f"Error: Command validation failed - {error_message}"
    
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
        
        # Handle case where response is None (severe error or timeout)
        if response is None:
            logger.warning(f"Command '{command}' received no response (potential timeout)")
            return f"Error: No response received for command after {timeout_ms}ms (timeout or connection issue)"
        
        # Check for structured error response
        if response.get("status") == "error":
            error_message = response.get("error", "Unknown error")
            error_category = response.get("error_category", "unknown")
            suggestion = response.get("suggestion", "")
            
            # Format the error message for better readability
            formatted_error = f"Error: {error_message}"
            
            if error_category != "unknown":
                formatted_error += f" (Category: {error_category})"
                
            if suggestion:
                formatted_error += f"\nSuggestion: {suggestion}"
                
            return formatted_error
            
        # Handle empty or missing output
        output = response.get("output", "")
        if output is None:
            return "No output returned from command"
            
        return output
    except TimeoutError as e:
        logger.error(f"Timeout executing command '{command}' after {timeout_ms}ms: {e}")
        return f"Error: Command timed out after {timeout_ms}ms"
    except ConnectionError as e:
        logger.error(f"Connection error executing command '{command}': {e}")
        return f"Error: Connection problem - {str(e)}"
    except RuntimeError as e:
        logger.error(f"Runtime error executing command '{command}': {e}")
        return f"Error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error executing command '{command}': {e}")
        logger.error(traceback.format_exc())
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
    
    # Validate address format
    if not re.match(r'^[0-9a-fA-F`x]+$', address):
        error = "Invalid memory address format. Expected hexadecimal value."
        logger.error(error)
        return f"Error: {error}"
    
    # Validate length
    if length <= 0 or length > 1000:
        error = f"Invalid memory length: {length}. Must be between 1 and 1000."
        logger.error(error)
        return f"Error: {error}"
    
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