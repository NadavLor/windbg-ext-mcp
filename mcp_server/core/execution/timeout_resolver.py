"""
Centralized timeout resolution for unified execution system.

This module consolidates all timeout logic and eliminates duplication across
the resilient, optimization, and streaming systems.
"""
import logging
from typing import Dict, Optional
from enum import Enum

from config import get_timeout_for_command, DebuggingMode

logger = logging.getLogger(__name__)

class TimeoutCategory(Enum):
    """Standardized timeout categories."""
    QUICK = "quick"           # version, help, etc.
    NORMAL = "normal"         # standard commands  
    ANALYSIS = "analysis"     # !analyze, !thread, etc.
    MEMORY = "memory"         # memory operations
    EXECUTION = "execution"   # execution control
    BULK = "bulk"            # module lists, etc.
    LARGE_ANALYSIS = "large_analysis"  # large analysis ops
    PROCESS_LIST = "process_list"      # full process enumeration
    STREAMING = "streaming"   # streaming operations
    SYMBOLS = "symbols"       # symbol operations
    EXTENDED = "extended"     # extended operations

# Mapping from legacy category names to standardized categories
LEGACY_CATEGORY_MAP = {
    "slow": TimeoutCategory.ANALYSIS,
    "fast": TimeoutCategory.QUICK,
    "very_slow": TimeoutCategory.LARGE_ANALYSIS
}

class TimeoutResolver:
    """
    Centralized timeout resolution system.
    
    Eliminates duplication between categorize_command_timeout, 
    get_timeout_for_command, and hardcoded streaming timeouts.
    """
    
    def __init__(self, default_mode: DebuggingMode = DebuggingMode.VM_NETWORK):
        self.default_mode = default_mode
        self._category_cache: Dict[str, TimeoutCategory] = {}
        
    def get_timeout(
        self, 
        command: str, 
        mode: DebuggingMode = None, 
        category_override: str = None
    ) -> int:
        """
        Get timeout for a command in milliseconds.
        
        Args:
            command: WinDbg command
            mode: Debugging mode (uses default if None)
            category_override: Override timeout category
            
        Returns:
            Timeout in milliseconds
        """
        if mode is None:
            mode = self.default_mode
            
        # Use override category if provided
        if category_override:
            category = self._normalize_category(category_override)
            if category:
                # Convert category back to command-like string for config lookup
                category_command = self._category_to_command_pattern(category)
                return get_timeout_for_command(category_command, mode)
        
        # Use centralized config system
        return get_timeout_for_command(command, mode)
    
    def get_category(self, command: str) -> TimeoutCategory:
        """
        Get standardized timeout category for a command.
        
        Args:
            command: WinDbg command
            
        Returns:
            TimeoutCategory enum value
        """
        # Check cache first
        if command in self._category_cache:
            return self._category_cache[command]
        
        category = self._categorize_command(command)
        
        # Cache the result
        self._category_cache[command] = category
        
        logger.debug(f"Command '{command}' categorized as '{category.value}'")
        return category
    
    def get_category_name(self, command: str) -> str:
        """
        Get timeout category name as string.
        
        Args:
            command: WinDbg command
            
        Returns:
            Category name string
        """
        return self.get_category(command).value
    
    def resolve_timeout_and_category(
        self, 
        command: str, 
        mode: DebuggingMode = None,
        category_override: str = None
    ) -> tuple[int, str]:
        """
        Resolve both timeout and category for a command.
        
        Args:
            command: WinDbg command
            mode: Debugging mode
            category_override: Override timeout category
            
        Returns:
            Tuple of (timeout_ms, category_name)
        """
        if category_override:
            category = self._normalize_category(category_override)
            if category:
                timeout_ms = self.get_timeout(command, mode, category_override)
                return timeout_ms, category.value
        
        # Get category and timeout together
        category = self.get_category(command)
        timeout_ms = self.get_timeout(command, mode)
        
        return timeout_ms, category.value
    
    def _categorize_command(self, command: str) -> TimeoutCategory:
        """
        Categorize a command into timeout category.
        
        This replaces the old categorize_command_timeout function.
        """
        command_lower = command.lower().strip()
        
        # Extended timeout commands (check these first)
        if ".reload" in command_lower and ("/f" in command_lower or "-f" in command_lower):
            return TimeoutCategory.EXTENDED
        
        # Symbol operations (general)
        elif any(cmd in command_lower for cmd in [".reload", ".sympath", ".symfix"]):
            return TimeoutCategory.SYMBOLS
        
        # Process list commands
        elif any(cmd in command_lower for cmd in ["!process 0 0", "!process 0 7", "!process 0 1f"]):
            return TimeoutCategory.PROCESS_LIST
        
        # Streaming commands
        elif any(cmd in command_lower for cmd in ["!for_each_process", "!for_each_thread", "!for_each_module"]):
            return TimeoutCategory.STREAMING
        
        # Large analysis commands
        elif any(cmd in command_lower for cmd in ["!analyze -v", "!thread -1", "!process -1"]):
            return TimeoutCategory.LARGE_ANALYSIS
        
        # Bulk operations
        elif any(cmd in command_lower for cmd in ["!process 0 0", "!handle 0 f", "lm", "!dlls", "!vm", "!address"]):
            return TimeoutCategory.BULK
        
        # Analysis operations
        elif any(cmd in command_lower for cmd in ["!analyze", "!poolfind", "!poolused", "!thread", "!process"]):
            return TimeoutCategory.ANALYSIS
        
        # Memory operations
        elif any(cmd in command_lower for cmd in ["dd", "dq", "dp", "da", "du", "ed", "ew", "eb", "eq"]):
            return TimeoutCategory.MEMORY
        
        # Execution control
        elif any(cmd in command_lower for cmd in ["g", "p", "t", "bp", "bc", "bd", "be"]):
            return TimeoutCategory.EXECUTION
        
        # Quick commands
        elif any(cmd in command_lower for cmd in ["version", "r", "?", ".effmach", "help"]):
            return TimeoutCategory.QUICK
        
        else:
            return TimeoutCategory.NORMAL
    
    def _normalize_category(self, category_str: str) -> Optional[TimeoutCategory]:
        """
        Normalize a category string to TimeoutCategory enum.
        
        Args:
            category_str: Category string (may be legacy format)
            
        Returns:
            TimeoutCategory enum value or None if invalid
        """
        if not category_str:
            return None
            
        # Try direct enum lookup
        try:
            return TimeoutCategory(category_str.lower())
        except ValueError:
            pass
        
        # Check legacy mappings
        legacy_category = LEGACY_CATEGORY_MAP.get(category_str.lower())
        if legacy_category:
            return legacy_category
        
        logger.warning(f"Unknown timeout category: {category_str}")
        return None
    
    def _category_to_command_pattern(self, category: TimeoutCategory) -> str:
        """
        Convert category to a representative command pattern for config lookup.
        
        This is used when we have a category override but need to use
        the centralized config system.
        """
        patterns = {
            TimeoutCategory.QUICK: "version",
            TimeoutCategory.NORMAL: "k",
            TimeoutCategory.ANALYSIS: "!analyze",
            TimeoutCategory.MEMORY: "dd",
            TimeoutCategory.EXECUTION: "g",
            TimeoutCategory.BULK: "lm",
            TimeoutCategory.LARGE_ANALYSIS: "!analyze -v",
            TimeoutCategory.PROCESS_LIST: "!process 0 0",
            TimeoutCategory.STREAMING: "!for_each_process",
            TimeoutCategory.SYMBOLS: ".reload",
            TimeoutCategory.EXTENDED: ".reload /f"
        }
        
        return patterns.get(category, "k")  # Default to normal command
    
    def clear_cache(self):
        """Clear the category cache."""
        self._category_cache.clear()
        logger.debug("Timeout category cache cleared")

# Global timeout resolver instance
_global_resolver = None

def get_timeout_resolver() -> TimeoutResolver:
    """Get the global timeout resolver instance."""
    global _global_resolver
    if _global_resolver is None:
        _global_resolver = TimeoutResolver()
    return _global_resolver

def resolve_timeout(
    command: str, 
    mode: DebuggingMode = None, 
    category_override: str = None
) -> int:
    """
    Convenience function to resolve timeout for a command.
    
    Args:
        command: WinDbg command
        mode: Debugging mode
        category_override: Override timeout category
        
    Returns:
        Timeout in milliseconds
    """
    resolver = get_timeout_resolver()
    return resolver.get_timeout(command, mode, category_override)

def resolve_category(command: str) -> str:
    """
    Convenience function to resolve timeout category for a command.
    
    Args:
        command: WinDbg command
        
    Returns:
        Category name string
    """
    resolver = get_timeout_resolver()
    return resolver.get_category_name(command) 