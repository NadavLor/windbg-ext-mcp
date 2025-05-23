"""
Command execution tools for WinDbg MCP server.

This module contains tools for executing WinDbg commands and command sequences.
"""
import logging
from typing import Dict, Any, List, Optional, Union
from fastmcp import FastMCP, Context

from core.communication import send_command
from core.validation import validate_command, is_safe_for_automation
from core.context import get_context_manager, save_context, restore_context
from core.error_handler import enhance_error, error_enhancer, DebugContext, ErrorCategory
from core.hints import get_parameter_help, validate_tool_parameters
from core.connection_resilience import execute_resilient_command
from core.performance import execute_optimized_command

from .tool_utilities import (
    categorize_command_timeout, get_direct_timeout, detect_kernel_mode,
    get_command_suggestions
)

logger = logging.getLogger(__name__)

def register_execution_tools(mcp: FastMCP):
    """Register all command execution tools."""
    
    @mcp.tool()
    async def run_command(ctx: Context, action: str = "", command: str = "", validate: bool = True, resilient: bool = True, optimize: bool = True) -> Union[str, Dict[str, Any]]:
        """
        Execute a WinDbg command with enhanced validation, resilience, and performance optimization.
        
        Args:
            ctx: The MCP context
            action: Action type (empty string for execute - maintained for framework compatibility)
            command: The WinDbg command to execute
            validate: Whether to validate the command for safety (default: True)
            resilient: Whether to use resilient execution with retries (default: True)  
            optimize: Whether to use performance optimization (default: True)
            
        Returns:
            Command result or enhanced error information
        """
        logger.debug(f"Executing command: {command}, validate: {validate}, resilient: {resilient}, optimize: {optimize}")
        logger.error(f"DEBUG: command parameter received: '{command}', type: {type(command)}, action: '{action}'")
        
        # Validate parameters
        is_valid, validation_errors = validate_tool_parameters("run_command", action, {"command": command})
        logger.error(f"DEBUG: validation result: {is_valid}, errors: {validation_errors}")
        if not is_valid:
            enhanced_error = enhance_error("parameter", 
                                         tool_name="run_command", 
                                         command=command, 
                                         missing_param="command")
            return enhanced_error.to_dict()
        
        if not command.strip():
            enhanced_error = enhance_error("parameter", 
                                         tool_name="run_command", 
                                         command="", 
                                         missing_param="command")
            error_dict = enhanced_error.to_dict()
            error_dict["help"] = get_parameter_help("run_command")
            return error_dict
        
        # Update context for better error suggestions  
        error_enhancer.update_context(DebugContext.KERNEL_MODE if detect_kernel_mode() else DebugContext.USER_MODE)
        
        try:
            # Command validation if requested
            if validate:
                is_valid, validation_error = validate_command(command)
                if not is_valid:
                    enhanced_error = enhance_error("validation", 
                                                 command=command, 
                                                 validation_errors=[validation_error] if validation_error else ["Validation failed"])
                    return enhanced_error.to_dict()
                
                # Check if command is safe for automation
                if not is_safe_for_automation(command):
                    enhanced_error = enhance_error("safety", command=command)
                    return enhanced_error.to_dict()
            
            # Choose execution method based on parameters
            if optimize and resilient:
                # Use optimized execution with automatic timeout categorization
                timeout_category = categorize_command_timeout(command)
                success, result, metadata = execute_optimized_command(command, timeout_category)
                
                if success:
                    # Add performance information to result
                    return {
                        "success": True,
                        "result": result,
                        "execution_method": "optimized_resilient",
                        "performance_info": {
                            "cached": metadata.get("cached", False),
                            "response_time": metadata.get("response_time", 0),
                            "retries_used": metadata.get("retries_attempted", 0),
                            "timeout_category": timeout_category,
                            "optimization_level": metadata.get("optimization_level", "unknown")
                        },
                        "suggestions": get_command_suggestions(command, result)
                    }
                else:
                    enhanced_error = enhance_error("execution", 
                                                 command=command, 
                                                 timeout_category=timeout_category)
                    return enhanced_error.to_dict()
                    
            elif resilient:
                # Use resilient execution without optimization
                timeout_category = categorize_command_timeout(command)
                success, result, metadata = execute_resilient_command(command, timeout_category)
                
                if success:
                    return {
                        "success": True,
                        "result": result,
                        "execution_method": "resilient",
                        "resilience_info": {
                            "response_time": metadata.get("response_time", 0),
                            "retries_used": metadata.get("retries_attempted", 0),
                            "timeout_category": timeout_category
                        },
                        "suggestions": get_command_suggestions(command, result)
                    }
                else:
                    enhanced_error = enhance_error("execution", 
                                                 command=command, 
                                                 timeout_category=timeout_category)
                    return enhanced_error.to_dict()
                    
            else:
                # Direct execution
                timeout_ms = get_direct_timeout(command)
                result = send_command(command, timeout_ms)
                
                if result is not None:
                    return {
                        "success": True,
                        "result": result,
                        "execution_method": "direct",
                        "timeout_used": timeout_ms,
                        "suggestions": get_command_suggestions(command, result)
                    }
                else:
                    enhanced_error = enhance_error("timeout", 
                                                 command=command, 
                                                 timeout_ms=timeout_ms)
                    return enhanced_error.to_dict()
                    
        except Exception as e:
            enhanced_error = enhance_error("unexpected", 
                                         tool_name="run_command", 
                                         command=command, 
                                         original_error=str(e))
            return enhanced_error.to_dict()

    @mcp.tool()
    async def run_sequence(ctx: Context, commands: List[str], stop_on_error: bool = False) -> Dict[str, Any]:
        """
        Execute a sequence of WinDbg commands with enhanced error handling and performance optimization.
        
        Args:
            ctx: The MCP context
            commands: List of commands to execute in sequence
            stop_on_error: Whether to stop execution if a command fails (default: False)
            
        Returns:
            Results of all commands with execution summary and performance metrics
        """
        logger.debug(f"Executing command sequence: {len(commands)} commands, stop_on_error: {stop_on_error}")
        
        # Validate parameters
        is_valid, validation_errors = validate_tool_parameters("run_sequence", "", {"commands": commands})
        if not is_valid:
            enhanced_error = enhance_error("parameter", 
                                         tool_name="run_sequence", 
                                         missing_param="commands")
            return enhanced_error.to_dict()
        
        if not commands or not isinstance(commands, list):
            enhanced_error = enhance_error("parameter", 
                                         tool_name="run_sequence", 
                                         missing_param="commands")
            error_dict = enhanced_error.to_dict()
            error_dict["help"] = get_parameter_help("run_sequence")
            return error_dict
        
        # Update context for better error suggestions
        error_enhancer.update_context(DebugContext.KERNEL_MODE if detect_kernel_mode() else DebugContext.USER_MODE)
        
        # Save context before sequence execution for potential rollback
        context_manager = get_context_manager()
        context_saved = save_context(context_manager, f"run_sequence_{len(commands)}_commands")
        
        results = []
        successful_commands = 0
        failed_commands = 0
        total_execution_time = 0.0
        execution_stopped = False
        
        try:
            for i, command in enumerate(commands):
                if not command.strip():
                    # Skip empty commands
                    results.append({
                        "command": command,
                        "index": i,
                        "success": False,
                        "error": "Empty command",
                        "skipped": True
                    })
                    continue
                
                logger.debug(f"Executing command {i+1}/{len(commands)}: {command}")
                
                # Validate each command
                is_valid, validation_error = validate_command(command)
                if not is_valid:
                    result = {
                        "command": command,
                        "index": i,
                        "success": False,
                        "error": f"Validation failed: {validation_error}",
                        "validation_errors": [validation_error] if validation_error else ["Validation failed"]
                    }
                    results.append(result)
                    failed_commands += 1
                    
                    if stop_on_error:
                        execution_stopped = True
                        logger.warning(f"Stopping sequence execution at command {i+1} due to validation error")
                        break
                    continue
                
                # Check if command is safe for automation
                if not is_safe_for_automation(command):
                    result = {
                        "command": command,
                        "index": i,
                        "success": False,
                        "error": "Command not safe for automation",
                        "safety_concern": True
                    }
                    results.append(result)
                    failed_commands += 1
                    
                    if stop_on_error:
                        execution_stopped = True
                        logger.warning(f"Stopping sequence execution at command {i+1} due to safety concern")
                        break
                    continue
                
                # Execute command with optimization
                try:
                    timeout_category = categorize_command_timeout(command)
                    success, cmd_result, metadata = execute_optimized_command(command, timeout_category)
                    
                    execution_time = metadata.get("response_time", 0)
                    total_execution_time += execution_time
                    
                    if success:
                        result = {
                            "command": command,
                            "index": i,
                            "success": True,
                            "result": cmd_result,
                            "execution_time": execution_time,
                            "cached": metadata.get("cached", False),
                            "retries_used": metadata.get("retries_attempted", 0),
                            "timeout_category": timeout_category,
                            "suggestions": get_command_suggestions(command, cmd_result)
                        }
                        successful_commands += 1
                    else:
                        result = {
                            "command": command,
                            "index": i,
                            "success": False,
                            "error": "Command execution failed",
                            "execution_time": execution_time,
                            "retries_used": metadata.get("retries_attempted", 0),
                            "timeout_category": timeout_category
                        }
                        failed_commands += 1
                        
                        if stop_on_error:
                            execution_stopped = True
                            logger.warning(f"Stopping sequence execution at command {i+1} due to execution failure")
                            break
                    
                    results.append(result)
                    
                except Exception as e:
                    result = {
                        "command": command,
                        "index": i,
                        "success": False,
                        "error": f"Unexpected error: {str(e)}",
                        "exception": True
                    }
                    results.append(result)
                    failed_commands += 1
                    
                    if stop_on_error:
                        execution_stopped = True
                        logger.error(f"Stopping sequence execution at command {i+1} due to exception: {e}")
                        break
            
            # Prepare summary
            summary = {
                "total_commands": len(commands),
                "successful_commands": successful_commands,
                "failed_commands": failed_commands,
                "execution_stopped": execution_stopped,
                "total_execution_time": total_execution_time,
                "average_execution_time": total_execution_time / len(commands) if commands else 0,
                "context_saved": context_saved,
                "sequence_performance": "excellent" if failed_commands == 0 else "good" if failed_commands < len(commands) * 0.2 else "poor"
            }
            
            # Add recommendations
            recommendations = []
            if failed_commands > 0:
                recommendations.append(f"⚠️ {failed_commands} commands failed - review individual results")
                if not stop_on_error:
                    recommendations.append("💡 Consider using stop_on_error=true for critical sequences")
            
            if total_execution_time > 30.0:
                recommendations.append("⏱️ Long execution time - consider breaking into smaller sequences")
                recommendations.append("🚀 Use async_manager for parallel execution of independent commands")
            
            cached_commands = sum(1 for r in results if r.get("cached", False))
            if cached_commands > 0:
                recommendations.append(f"🎯 {cached_commands} commands served from cache - optimization working")
            
            if successful_commands == len(commands):
                recommendations.append("✅ All commands executed successfully")
            
            return {
                "sequence_results": results,
                "summary": summary,
                "recommendations": recommendations,
                "context_recovery": {
                    "context_saved": context_saved,
                    "recovery_hint": "Use restore_context if sequence caused issues" if context_saved else None
                }
            }
            
        except Exception as e:
            enhanced_error = enhance_error("unexpected", 
                                         tool_name="run_sequence", 
                                         original_error=str(e))
            error_dict = enhanced_error.to_dict()
            error_dict["partial_results"] = results
            error_dict["commands_processed"] = len(results)
            return error_dict 