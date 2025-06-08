"""
Error handling and user experience module for WinDbg MCP Extension.

This module provides context-aware error messages, debugging suggestions,
and workflow guidance specifically tailored for kernel debugging scenarios.
"""
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

class DebugContext(Enum):
    """Current debugging context for better error suggestions."""
    KERNEL_MODE = "kernel"
    USER_MODE = "user"
    UNKNOWN = "unknown"
    BREAKPOINT_HIT = "breakpoint"
    EXCEPTION_OCCURRED = "exception"
    PROCESS_CONTEXT = "process"
    THREAD_CONTEXT = "thread"

class ErrorCategory(Enum):
    """Categories of errors for tailored responses."""
    CONNECTION = "connection"
    VALIDATION = "validation"
    PARAMETER = "parameter"
    CONTEXT = "context"
    TIMEOUT = "timeout"
    PERMISSION = "permission"
    SYMBOL = "symbol"
    MEMORY = "memory"
    WORKFLOW = "workflow"

class EnhancedError:
    """Error with context-aware suggestions."""
    
    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        suggestions: List[str] = None,
        examples: List[str] = None,
        next_steps: List[str] = None,
        related_tools: List[str] = None,
        debug_context: DebugContext = DebugContext.UNKNOWN
    ):
        self.category = category
        self.message = message
        self.suggestions = suggestions or []
        self.examples = examples or []
        self.next_steps = next_steps or []
        self.related_tools = related_tools or []
        self.debug_context = debug_context
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MCP response."""
        result = {
            "error": self.message,
            "category": self.category.value,
            "context": self.debug_context.value
        }
        
        if self.suggestions:
            result["suggestions"] = self.suggestions
        
        if self.examples:
            result["examples"] = self.examples
            
        if self.next_steps:
            result["next_steps"] = self.next_steps
            
        if self.related_tools:
            result["related_tools"] = self.related_tools
            
        return result

class ErrorEnhancer:
    """Main class for creating errors with context and suggestions."""
    
    def __init__(self):
        self.current_context = DebugContext.UNKNOWN
        self.last_successful_commands = []
        self.debugging_state = {}
    
    def update_context(self, context: DebugContext, state_info: Dict[str, Any] = None):
        """Update the current debugging context."""
        self.current_context = context
        if state_info:
            self.debugging_state.update(state_info)
        logger.debug(f"Updated debug context to: {context.value}")
    
    def enhance_parameter_error(self, tool_name: str, action: str, missing_param: str) -> EnhancedError:
        """Create error for missing/invalid parameters."""
        examples = self._get_parameter_examples(tool_name, action, missing_param)
        suggestions = self._get_parameter_suggestions(tool_name, action, missing_param)
        next_steps = self._get_parameter_next_steps(tool_name, action)
        
        message = f"Missing or invalid parameter '{missing_param}' for {tool_name}.{action}"
        
        return EnhancedError(
            category=ErrorCategory.PARAMETER,
            message=message,
            suggestions=suggestions,
            examples=examples,
            next_steps=next_steps,
            related_tools=self._get_related_tools(tool_name),
            debug_context=self.current_context
        )
    
    def enhance_connection_error(self, original_error: str) -> EnhancedError:
        """Create error for connection issues."""
        suggestions = [
            "Check that WinDbg is running and the target is connected",
            "Verify the extension DLL is loaded: .load path\\to\\windbgmcpExt.dll",
            "Ensure the target VM is accessible over the network debugging connection",
            "Try reconnecting to the target: .reconnect or restart the debugging session"
        ]
        
        next_steps = [
            "1. Verify WinDbg connection status with the debug_session tool",
            "2. Check network connectivity to the target VM",
            "3. Reload the extension if needed",
            "4. Restart the debugging session if connection is completely lost"
        ]
        
        if "pipe" in original_error.lower():
            suggestions.insert(0, "The named pipe connection failed - extension may not be running")
        
        return EnhancedError(
            category=ErrorCategory.CONNECTION,
            message=f"Connection to WinDbg extension failed: {original_error}",
            suggestions=suggestions,
            next_steps=next_steps,
            related_tools=["debug_session", "troubleshoot"],
            debug_context=self.current_context
        )
    
    def enhance_validation_error(self, command: str, validation_error: str) -> EnhancedError:
        """Create error for command validation failures."""
        suggestions = []
        examples = []
        
        if "restricted" in validation_error.lower():
            suggestions = [
                f"The command '{command}' is restricted for safety",
                "Use alternative commands that provide similar information",
                "For debugging, use read-only commands that don't change system state"
            ]
            examples = self._get_safe_alternatives(command)
        
        elif "too long" in validation_error.lower():
            suggestions = [
                "Break the command into smaller parts",
                "Use the run_sequence tool for multiple related commands",
                "Simplify the command parameters"
            ]
            examples = ["Use run_sequence with commands: ['cmd1', 'cmd2', 'cmd3']"]
        
        return EnhancedError(
            category=ErrorCategory.VALIDATION,
            message=f"Command validation failed: {validation_error}",
            suggestions=suggestions,
            examples=examples,
            related_tools=["run_command", "run_sequence"],
            debug_context=self.current_context
        )
    
    def enhance_context_error(self, operation: str, context_error: str) -> EnhancedError:
        """Create error for context-related issues."""
        suggestions = []
        next_steps = []
        
        if "process" in context_error.lower():
            suggestions = [
                "Ensure you're in the correct process context",
                "Use analyze_process to list and switch to the target process",
                "Save current context before switching with save_context=True"
            ]
            examples = [
                "analyze_process(action='list') - to see all processes",
                "analyze_process(action='switch', address='0xffff...') - to switch context"
            ]
            next_steps = [
                "1. List all processes to find the target",
                "2. Switch to the correct process context",
                "3. Retry the original operation"
            ]
        
        elif "thread" in context_error.lower():
            suggestions = [
                "Ensure you're in the correct thread context",
                "Use analyze_thread to list and switch to the target thread",
                "Some operations require specific thread context"
            ]
            examples = [
                "analyze_thread(action='list') - to see all threads",
                "analyze_thread(action='switch', address='0xffff...') - to switch context"
            ]
        
        return EnhancedError(
            category=ErrorCategory.CONTEXT,
            message=f"Context error during {operation}: {context_error}",
            suggestions=suggestions,
            examples=examples,
            next_steps=next_steps,
            related_tools=["analyze_process", "analyze_thread"],
            debug_context=self.current_context
        )
    
    def enhance_timeout_error(self, command: str, timeout_ms: int) -> EnhancedError:
        """Create error for timeout issues."""
        suggestions = []
        next_steps = []
        
        if self.current_context == DebugContext.KERNEL_MODE:
            suggestions = [
                f"Kernel debugging over network can be slow - command timed out after {timeout_ms}ms",
                "The target VM might be busy or unresponsive",
                "Network debugging has higher latency than local debugging",
                "Large operations (like listing all processes) can take significant time"
            ]
            next_steps = [
                "1. Check if the target VM is responsive",
                "2. Try breaking into the debugger if target seems hung",
                "3. Use more specific commands to reduce data volume",
                "4. Consider increasing timeout for large operations"
            ]
        else:
            suggestions = [
                f"Command timed out after {timeout_ms}ms",
                "The debuggee process might be busy or unresponsive",
                "Try breaking into the debugger first"
            ]
        
        # Suggest alternatives for specific commands
        if "!process 0 0" in command:
            suggestions.append("Try 'analyze_process(action='list')' which handles large output better")
        elif "!handle" in command:
            suggestions.append("Try limiting handle enumeration with specific process context")
        
        return EnhancedError(
            category=ErrorCategory.TIMEOUT,
            message=f"Command '{command}' timed out after {timeout_ms}ms",
            suggestions=suggestions,
            next_steps=next_steps,
            related_tools=["debug_session", "troubleshoot"],
            debug_context=self.current_context
        )
    
    def get_workflow_suggestions(self, current_tool: str, current_action: str) -> List[str]:
        """Get workflow suggestions based on current operation."""
        workflows = {
            "debug_session": [
                "After checking connection, try listing processes with analyze_process(action='list')",
                "Use troubleshoot(action='symbols') to verify symbol loading",
                "Check debugging mode - kernel mode has different available operations"
            ],
            "analyze_process": {
                "list": [
                    "Found interesting process? Use analyze_process(action='info', address='...') for details",
                    "Switch to process context with analyze_process(action='switch', address='...')",
                    "Get process PEB with analyze_process(action='peb', address='...')"
                ],
                "switch": [
                    "After switching, you can examine process memory and threads",
                    "Use analyze_thread(action='list') to see threads in this process",
                    "Use analyze_memory to examine process memory regions"
                ]
            },
            "analyze_memory": {
                "display": [
                    "Found interesting data? Use analyze_memory(action='type', ...) to interpret as structure",
                    "Search for patterns with analyze_memory(action='search', ...)",
                    "Check memory protection with analyze_memory(action='regions')"
                ]
            }
        }
        
        if current_tool in workflows:
            if isinstance(workflows[current_tool], dict) and current_action in workflows[current_tool]:
                return workflows[current_tool][current_action]
            elif isinstance(workflows[current_tool], list):
                return workflows[current_tool]
        
        return []
    
    def _get_parameter_examples(self, tool_name: str, action: str, param: str) -> List[str]:
        """Get examples for specific tool/action/parameter combinations."""
        examples_map = {
            "analyze_process": {
                "switch": {
                    "address": ["address='0xffff8e0e481d7080'", "address='ffffc001e1234567'"]
                },
                "info": {
                    "address": ["address='0xffff8e0e481d7080' (from process list)"]
                }
            },
            "analyze_thread": {
                "switch": {
                    "address": ["address='0xffff8e0e12345678'", "address='ffffc001e9876543'"]
                },
                "stack": {
                    "count": ["count=20 (default)", "count=50 (deeper stack)"]
                }
            },
            "analyze_memory": {
                "display": {
                    "address": ["address='0x1000'", "address='@$peb'", "address='kernel32+0x1000'"],
                    "length": ["length=32 (default)", "length=64", "length=128"]
                },
                "type": {
                    "type_name": ["type_name='nt!_EPROCESS'", "type_name='nt!_KTHREAD'"],
                    "address": ["address='0xffff8e0e481d7080'"]
                }
            },
            "run_command": {
                "": {
                    "command": [
                        "command='lm' (list modules)",
                        "command='k' (stack trace)",
                        "command='r' (registers)"
                    ]
                }
            }
        }
        
        return examples_map.get(tool_name, {}).get(action, {}).get(param, [])
    
    def _get_parameter_suggestions(self, tool_name: str, action: str, param: str) -> List[str]:
        """Get suggestions for missing parameters."""
        suggestions_map = {
            "address": [
                "Get process addresses from analyze_process(action='list')",
                "Get thread addresses from analyze_thread(action='list')",
                "Use hexadecimal format: '0xffff8e0e481d7080'",
                "Addresses are from previous tool outputs or WinDbg commands"
            ],
            "action": [
                f"Specify what action to perform with {tool_name}",
                "Use tab completion or check tool documentation for available actions",
                "Common actions: 'list', 'info', 'switch', depending on the tool"
            ],
            "command": [
                "Specify the WinDbg command to execute",
                "Examples: 'lm', 'k', 'r', '!process 0 0'",
                "Use WinDbg command syntax - see WinDbg documentation"
            ]
        }
        
        return suggestions_map.get(param, [f"Parameter '{param}' is required for this operation"])
    
    def _get_parameter_next_steps(self, tool_name: str, action: str) -> List[str]:
        """Get next steps for parameter errors."""
        if tool_name == "analyze_process" and action in ["switch", "info", "peb"]:
            return [
                "1. First run analyze_process(action='list') to get process addresses",
                "2. Copy the address from the output",
                "3. Use that address in your command"
            ]
        elif tool_name == "analyze_thread" and action in ["switch", "info", "stack", "teb"]:
            return [
                "1. First run analyze_thread(action='list') to get thread addresses",
                "2. Copy the thread address from the output",
                "3. Use that address in your command"
            ]
        
        return []
    
    def _get_related_tools(self, tool_name: str) -> List[str]:
        """Get related tools that might help."""
        related_map = {
            "analyze_process": ["analyze_thread", "analyze_memory", "run_command"],
            "analyze_thread": ["analyze_process", "analyze_memory", "run_command"],
            "analyze_memory": ["analyze_process", "analyze_kernel", "run_command"],
            "analyze_kernel": ["analyze_memory", "analyze_process", "run_command"],
            "run_command": ["debug_session", "troubleshoot"],
            "troubleshoot": ["debug_session", "run_command"]
        }
        
        return related_map.get(tool_name, [])
    
    def _get_safe_alternatives(self, restricted_command: str) -> List[str]:
        """Get safe alternatives for restricted commands."""
        alternatives = {
            "q": ["Use Ctrl+C or close the MCP client to stop"],
            ".kill": ["Use .detach to disconnect safely", "Restart debugging session manually"],
            ".dump": ["Use run_command with specific .dump parameters"],
            ".load": ["Specify the full path: run_command('.load C:\\path\\to\\extension.dll')"]
        }
        
        base_cmd = restricted_command.split()[0] if restricted_command else ""
        return alternatives.get(base_cmd, ["Use equivalent read-only commands"])

# Global instance for use across the application
error_enhancer = ErrorEnhancer()

def enhance_error(error_type: str, **kwargs) -> EnhancedError:
    """Convenience function to create contextual errors."""
    if error_type == "parameter":
        return error_enhancer.enhance_parameter_error(
            kwargs.get("tool_name", ""),
            kwargs.get("action", ""),
            kwargs.get("missing_param", "")
        )
    elif error_type == "connection":
        return error_enhancer.enhance_connection_error(kwargs.get("original_error", ""))
    elif error_type == "validation":
        return error_enhancer.enhance_validation_error(
            kwargs.get("command", ""),
            kwargs.get("validation_error", "")
        )
    elif error_type == "context":
        return error_enhancer.enhance_context_error(
            kwargs.get("operation", ""),
            kwargs.get("context_error", "")
        )
    elif error_type == "timeout":
        return error_enhancer.enhance_timeout_error(
            kwargs.get("command", ""),
            kwargs.get("timeout_ms", 30000)
        )
    else:
        return EnhancedError(
            category=ErrorCategory.WORKFLOW,
            message=kwargs.get("message", "Unknown error"),
            debug_context=error_enhancer.current_context
        ) 