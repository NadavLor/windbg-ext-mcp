"""
Parameter validation and help generation for WinDbg MCP tools.

This module provides the main ParameterHints class that handles parameter
validation, help generation, and tool information retrieval.
"""
import logging
from typing import Dict, Any, List, Optional, Tuple

from .data_structures import ParameterInfo, ActionInfo, ToolInfo
from .definitions import get_tool_definitions

logger = logging.getLogger(__name__)

class ParameterHints:
    """Provides parameter hints and validation for MCP tools."""
    
    def __init__(self):
        self.tools = get_tool_definitions()
    
    def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get complete information about a tool."""
        return self.tools.get(tool_name)
    
    def get_action_info(self, tool_name: str, action: str) -> Optional[ActionInfo]:
        """Get information about a specific tool action."""
        tool = self.get_tool_info(tool_name)
        if tool:
            return tool.actions.get(action)
        return None
    
    def validate_parameters(self, tool_name: str, action: str, parameters: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate parameters for a tool action.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        action_info = self.get_action_info(tool_name, action)
        if not action_info:
            return False, [f"Unknown action '{action}' for tool '{tool_name}'"]
        
        errors = []
        
        # Check required parameters
        for param_info in action_info.parameters:
            if param_info.required and param_info.name not in parameters:
                errors.append(f"Missing required parameter: {param_info.name}")
        
        # Validate parameter values
        for param_name, param_value in parameters.items():
            param_info = next((p for p in action_info.parameters if p.name == param_name), None)
            if param_info:
                # Type validation
                if param_info.type == "string" and not isinstance(param_value, str):
                    errors.append(f"Parameter '{param_name}' must be a string")
                elif param_info.type == "integer" and not isinstance(param_value, int):
                    errors.append(f"Parameter '{param_name}' must be an integer")
                elif param_info.type == "boolean" and not isinstance(param_value, bool):
                    errors.append(f"Parameter '{param_name}' must be a boolean")
                
                # Pattern validation for addresses
                if param_info.validation_pattern and isinstance(param_value, str):
                    import re
                    if not re.match(param_info.validation_pattern, param_value):
                        errors.append(f"Parameter '{param_name}' has invalid format. Expected pattern: {param_info.validation_pattern}")
        
        return len(errors) == 0, errors
    
    def get_parameter_suggestions(self, tool_name: str, action: str = "") -> Dict[str, Any]:
        """Get parameter suggestions and examples for a tool/action."""
        if action:
            action_info = self.get_action_info(tool_name, action)
            if action_info:
                return {
                    "description": action_info.description,
                    "parameters": [
                        {
                            "name": p.name,
                            "type": p.type,
                            "required": p.required,
                            "description": p.description,
                            "examples": p.examples,
                            "default": p.default_value
                        }
                        for p in action_info.parameters
                    ],
                    "examples": action_info.examples,
                    "next_steps": action_info.next_steps or []
                }
        else:
            tool_info = self.get_tool_info(tool_name)
            if tool_info:
                return {
                    "description": tool_info.description,
                    "actions": {
                        name: {
                            "description": action.description,
                            "examples": action.examples[:2]  # Just first 2 examples
                        }
                        for name, action in tool_info.actions.items()
                    },
                    "common_workflows": tool_info.common_workflows or []
                }
        
        return {}
    
    def get_quick_help(self, tool_name: str) -> str:
        """Get quick help text for a tool."""
        tool_info = self.get_tool_info(tool_name)
        if not tool_info:
            return f"Unknown tool: {tool_name}"
        
        help_text = [f"Tool: {tool_name}", f"Description: {tool_info.description}", ""]
        
        help_text.append("Available actions:")
        for action_name, action_info in tool_info.actions.items():
            if action_name:  # Skip empty action names
                help_text.append(f"  - {action_name}: {action_info.description}")
            else:
                help_text.append(f"  - {action_info.description}")
        
        if tool_info.common_workflows:
            help_text.extend(["", "Common workflows:"])
            for workflow in tool_info.common_workflows:
                help_text.append(f"  • {workflow}")
        
        return "\n".join(help_text) 