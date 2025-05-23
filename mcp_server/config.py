"""
Centralized configuration for WinDbg MCP Server.

This module contains all configuration constants, timeouts, and settings
used throughout the application to ensure consistency and easy maintenance.
"""
from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass

# ====================================================================
# COMMUNICATION SETTINGS
# ====================================================================

# Named pipe configuration
PIPE_NAME = r"\\.\pipe\windbgmcp"
BUFFER_SIZE = 8192

# Basic timeout settings (in milliseconds)
DEFAULT_TIMEOUT_MS = 30000
QUICK_COMMAND_TIMEOUT_MS = 5000
LONG_COMMAND_TIMEOUT_MS = 60000

# Retry configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_MS = 1000
NETWORK_DEBUGGING_TIMEOUT_MULTIPLIER = 2.0

# ====================================================================
# MONITORING SETTINGS
# ====================================================================

# Health monitoring intervals (in seconds)
CONNECTION_HEALTH_CHECK_INTERVAL = 30
ASYNC_MONITORING_INTERVAL = 30
SESSION_RECOVERY_CHECK_INTERVAL = 60

# Monitoring thresholds
LOW_SUCCESS_RATE_THRESHOLD = 0.5
WARNING_SUCCESS_RATE_THRESHOLD = 0.8
HIGH_EXECUTION_TIME_THRESHOLD = 10.0
HIGH_PENDING_TASKS_THRESHOLD = 10

# ====================================================================
# PERFORMANCE SETTINGS
# ====================================================================

# Cache configuration
DEFAULT_CACHE_SIZE = 100
MAX_CACHE_AGE_HOURS = 1
CACHE_CLEANUP_INTERVAL = 300  # 5 minutes

# Async operation limits
MAX_CONCURRENT_OPERATIONS = 5
TASK_CLEANUP_INTERVAL_HOURS = 1
MAX_ASYNC_HISTORY_SIZE = 100

# ====================================================================
# SESSION RECOVERY SETTINGS
# ====================================================================

# Recovery configuration
MAX_RECOVERY_ATTEMPTS = 3
SESSION_SNAPSHOT_INTERVAL = 300  # 5 minutes
SESSION_STATE_FILE = "windbg_session_state.json"

# ====================================================================
# DEBUGGING MODE CONFIGURATION
# ====================================================================

class DebuggingMode(Enum):
    """Debugging mode enumeration."""
    LOCAL = "local"
    VM_NETWORK = "vm_network"
    VM_SERIAL = "vm_serial"
    REMOTE = "remote"

class OptimizationLevel(Enum):
    """Performance optimization level."""
    DISABLED = "disabled"
    BASIC = "basic"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

# ====================================================================
# TIMEOUT CONFIGURATIONS
# ====================================================================

@dataclass
class TimeoutConfig:
    """Timeout configuration for different command types."""
    quick: int = 5000      # Quick commands (version, help, etc.)
    normal: int = 30000    # Normal commands
    analysis: int = 60000  # Analysis commands
    memory: int = 45000    # Memory operations
    execution: int = 30000 # Execution control

@dataclass
class RetryConfig:
    """Retry configuration for resilient operations."""
    max_attempts: int = 3
    base_delay_ms: int = 1000
    timeout_multiplier: float = 2.0
    exponential_backoff: bool = True

# Default configurations
DEFAULT_TIMEOUTS = TimeoutConfig()
DEFAULT_RETRY_CONFIG = RetryConfig()

# Mode-specific timeout multipliers
TIMEOUT_MULTIPLIERS = {
    DebuggingMode.LOCAL: 1.0,
    DebuggingMode.VM_NETWORK: 2.0,
    DebuggingMode.VM_SERIAL: 1.5,
    DebuggingMode.REMOTE: 2.5
}

# ====================================================================
# COMMAND CATEGORIES
# ====================================================================

# Commands by timeout category
QUICK_COMMANDS = {"version", "help", "?", "r"}
NORMAL_COMMANDS = {"lm", "k", "dv", "dt"}
ANALYSIS_COMMANDS = {"!analyze", "!thread", "!process"}
MEMORY_COMMANDS = {"dd", "dq", "dp", "da", "du"}
EXECUTION_COMMANDS = {"g", "p", "t", "bp", "bc"}

# Kernel-mode compatible commands for health checks
KERNEL_HEALTH_COMMANDS = ["version", "!pcr", ".effmach"]

# ====================================================================
# LOGGING CONFIGURATION
# ====================================================================

LOG_LEVEL = "INFO"
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Debug mode settings
DEBUG_ENABLED = False
VERBOSE_LOGGING = False

# ====================================================================
# UTILITY FUNCTIONS
# ====================================================================

def get_timeout_for_command(command: str, mode: DebuggingMode = DebuggingMode.LOCAL) -> int:
    """
    Get appropriate timeout for a command based on its type and debugging mode.
    
    Args:
        command: The command to check
        mode: Current debugging mode
        
    Returns:
        Timeout in milliseconds
    """
    # Determine base timeout by command type
    cmd_lower = command.lower()
    
    if any(quick_cmd in cmd_lower for quick_cmd in QUICK_COMMANDS):
        base_timeout = DEFAULT_TIMEOUTS.quick
    elif any(analysis_cmd in cmd_lower for analysis_cmd in ANALYSIS_COMMANDS):
        base_timeout = DEFAULT_TIMEOUTS.analysis
    elif any(memory_cmd in cmd_lower for memory_cmd in MEMORY_COMMANDS):
        base_timeout = DEFAULT_TIMEOUTS.memory
    elif any(exec_cmd in cmd_lower for exec_cmd in EXECUTION_COMMANDS):
        base_timeout = DEFAULT_TIMEOUTS.execution
    else:
        base_timeout = DEFAULT_TIMEOUTS.normal
    
    # Apply mode-specific multiplier
    multiplier = TIMEOUT_MULTIPLIERS.get(mode, 1.0)
    return int(base_timeout * multiplier)

def get_retry_delay(attempt: int, base_delay: int = None, exponential: bool = None) -> float:
    """
    Calculate retry delay based on attempt number.
    
    Args:
        attempt: Current attempt number (0-based)
        base_delay: Base delay in milliseconds (uses config default if None)
        exponential: Use exponential backoff (uses config default if None)
        
    Returns:
        Delay in seconds
    """
    if base_delay is None:
        base_delay = DEFAULT_RETRY_CONFIG.base_delay_ms
    if exponential is None:
        exponential = DEFAULT_RETRY_CONFIG.exponential_backoff
    
    if exponential:
        delay_ms = base_delay * (2 ** attempt)
    else:
        delay_ms = base_delay * (attempt + 1)
    
    return min(delay_ms / 1000.0, 30.0)  # Cap at 30 seconds

def is_kernel_health_command(command: str) -> bool:
    """Check if command is suitable for kernel-mode health checking."""
    return command.lower() in KERNEL_HEALTH_COMMANDS

# ====================================================================
# ENVIRONMENT DETECTION
# ====================================================================

def load_environment_config():
    """Load configuration from environment variables."""
    import os
    
    global DEBUG_ENABLED, VERBOSE_LOGGING, LOG_LEVEL
    
    DEBUG_ENABLED = os.environ.get("DEBUG", "false").lower() == "true"
    VERBOSE_LOGGING = os.environ.get("VERBOSE", "false").lower() == "true"
    
    if DEBUG_ENABLED:
        LOG_LEVEL = "DEBUG"
    elif VERBOSE_LOGGING:
        LOG_LEVEL = "INFO" 