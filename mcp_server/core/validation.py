"""
Simplified command validation for WinDbg MCP Extension.

This module provides basic security validation for WinDbg commands,
focusing only on preventing genuinely dangerous operations.
"""
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Maximum allowed command length
MAX_COMMAND_LENGTH = 4096

# Commands that could terminate the debugging session or cause damage
DANGEROUS_COMMANDS = {
    # Quit commands
    "q", "qq", "qd",
    # Session termination
    ".kill", ".detach", ".restart",
    # File operations without proper paths
    ".dump", ".dumpexr", ".dumpcab",
    # Potentially dangerous loads
    ".load", ".unload",
    # Connection changes
    ".connect", ".server",
    # Log operations without paths
    ".logopen", ".logappend"
}

# Commands that are always safe for kernel debugging
ALWAYS_SAFE_PREFIXES = {
    # Information commands
    "lm", "x", "dt", "dd", "dw", "db", "dq", "da", "du",
    # Process/thread info
    "!process", "!thread", "!dlls", "!handle", "!peb", "!teb",
    # Kernel objects
    "!object", "!idt", "!gdt", "!pcr", "!address",
    # Stack and registers
    "k", "kb", "kp", "kv", "r",
    # Disassembly
    "u", "uf",
    # Memory search
    "s",
    # Symbol operations
    ".reload", ".sympath", ".symfix",
    # Echo and help
    ".echo", ".help", "?", "??",
    # Breakpoints (read-only)
    "bl",
    # Version and target information
    "version", "vertarget",
    # Machine and architecture info
    ".effmach", ".formats",
    # Module and driver info
    "!drivers", "!devobj", "!irp",
    # PE header analysis
    "!dh",
    # Memory and address info
    "!vprot", "!pte"
}

def validate_command(command: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a WinDbg command for basic safety.
    
    Args:
        command: The command to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        where is_valid is True if safe, False if dangerous
        and error_message is None if valid, or explanation if dangerous
    """
    if not command or not command.strip():
        return False, "Empty command"
    
    command = command.strip()
    
    # Check command length
    if len(command) > MAX_COMMAND_LENGTH:
        return False, f"Command too long ({len(command)} chars, max {MAX_COMMAND_LENGTH})"
    
    # Extract the base command (first word)
    command_parts = command.split()
    if not command_parts:
        return False, "Invalid command format"
    
    base_command = command_parts[0].lower()
    
    # Check if it's a dangerous command
    if base_command in DANGEROUS_COMMANDS:
        return False, f"Command '{base_command}' is restricted for safety. It could terminate the debugging session or cause system damage."
    
    # Check if it starts with a safe prefix
    for safe_prefix in ALWAYS_SAFE_PREFIXES:
        if command.lower().startswith(safe_prefix.lower()):
            return True, None
    
    # Special validation for specific command types
    
    # Allow breakpoint setting/clearing (but not dangerous operations)
    if base_command in ["bp", "ba", "bu", "bm", "bc", "bd", "be"]:
        return True, None
    
    # Allow execution control commands (these are needed for debugging)
    if base_command in ["g", "p", "t", "gu", "wt"]:
        return True, None
    
    # Allow thread/process context switching
    if base_command in [".thread", ".process"]:
        return True, None
    
    # Allow meta commands that are generally safe
    if base_command.startswith(".") and base_command not in DANGEROUS_COMMANDS:
        # Log the meta command for awareness but allow it
        logger.info(f"Allowing meta command: {base_command}")
        return True, None
    
    # Allow extension commands (!)
    if base_command.startswith("!"):
        return True, None
    
    # For any other command, log it but allow it
    # In kernel debugging, users often need specialized commands
    logger.info(f"Allowing unrecognized command: {base_command}")
    return True, None

def is_safe_for_automation(command: str) -> bool:
    """
    Check if a command is safe for automated execution by LLMs.
    
    This function now allows execution control and breakpoint commands for LLM automation,
    enabling automated debugging workflows while still blocking genuinely dangerous operations.
    
    Args:
        command: The command to check
        
    Returns:
        True if safe for automation, False otherwise
    """
    if not command or not command.strip():
        return False
    
    command = command.strip().lower()
    
    # Never allow dangerous commands that could terminate sessions or cause damage
    base_command = command.split()[0] if command.split() else ""
    if base_command in DANGEROUS_COMMANDS:
        return False
    
    # CHANGED: Now allow execution control commands for LLM automation
    # These are essential for interactive debugging workflows
    execution_commands = {"g", "p", "t", "gu", "wt"}
    if base_command in execution_commands:
        logger.info(f"Allowing execution control command for automation: {base_command}")
        return True
    
    # CHANGED: Now allow breakpoint commands for LLM automation  
    # These are needed for setting up debugging scenarios
    breakpoint_commands = {"bp", "ba", "bu", "bm", "bc", "bd", "be"}
    if base_command in breakpoint_commands:
        logger.info(f"Allowing breakpoint command for automation: {base_command}")
        return True
    
    # CHANGED: Now allow context switches for LLM automation
    # These are often needed for comprehensive debugging
    context_commands = {".thread", ".process"}
    if base_command in context_commands:
        logger.info(f"Allowing context switch command for automation: {base_command}")
        return True
    
    # Everything else that passes basic validation is safe for automation
    is_valid, _ = validate_command(command)
    return is_valid 