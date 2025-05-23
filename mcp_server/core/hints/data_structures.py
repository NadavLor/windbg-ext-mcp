"""
Core data structures for parameter hints and tool definitions.

This module defines the data classes used to represent tool parameters,
actions, and complete tool information for the MCP system.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class ParameterInfo:
    """Information about a tool parameter."""
    name: str
    type: str
    required: bool
    description: str
    examples: List[str]
    validation_pattern: Optional[str] = None
    default_value: Any = None
    depends_on: Optional[str] = None  # This parameter is only relevant when another parameter has specific value

@dataclass
class ActionInfo:
    """Information about a tool action."""
    name: str
    description: str
    parameters: List[ParameterInfo]
    examples: List[str]
    kernel_mode_only: bool = False
    user_mode_only: bool = False
    next_steps: List[str] = None

@dataclass
class ToolInfo:
    """Complete information about an MCP tool."""
    name: str
    description: str
    actions: Dict[str, ActionInfo]
    common_workflows: List[str] = None 