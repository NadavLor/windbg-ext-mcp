"""
Parameter hints and validation package for WinDbg MCP tools.

This package provides intelligent parameter validation, hints, and examples
to improve the user experience and tool discoverability.

The package is organized into focused modules:
- data_structures.py: Core data classes (ParameterInfo, ActionInfo, ToolInfo)
- definitions.py: Complete tool definitions and metadata
- validator.py: Parameter validation and help generation
"""

# Import core data structures
from .data_structures import ParameterInfo, ActionInfo, ToolInfo

# Import the validator and global instance
from .validator import ParameterHints

# Global instance for use across the application
parameter_hints = ParameterHints()

# Convenience functions that delegate to the global instance
def get_parameter_help(tool_name: str, action: str = ""):
    """Get parameter help for a tool and action."""
    return parameter_hints.get_parameter_suggestions(tool_name, action)

def validate_tool_parameters(tool_name: str, action: str, parameters: dict):
    """Validate tool parameters."""
    return parameter_hints.validate_parameters(tool_name, action, parameters)

def get_tool_info(tool_name: str):
    """Get complete information about a tool."""
    return parameter_hints.get_tool_info(tool_name)

def get_action_info(tool_name: str, action: str):
    """Get information about a specific tool action."""
    return parameter_hints.get_action_info(tool_name, action)

def get_quick_help(tool_name: str):
    """Get quick help summary for a tool."""
    return parameter_hints.get_quick_help(tool_name)

__all__ = [
    # Core data structures
    "ParameterInfo",
    "ActionInfo", 
    "ToolInfo",
    
    # Main class
    "ParameterHints",
    
    # Global instance
    "parameter_hints",
    
    # Convenience functions
    "get_parameter_help",
    "validate_tool_parameters",
    "get_tool_info",
    "get_action_info",
    "get_quick_help"
] 