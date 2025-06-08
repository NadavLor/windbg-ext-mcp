"""
Command execution tools for WinDbg MCP server.

This module contains tools for executing WinDbg commands and command sequences.
"""
import logging
import time
from typing import Dict, Any, List, Optional, Union
from fastmcp import FastMCP, Context

from core.validation import validate_command, is_safe_for_automation
from core.context import get_context_manager, save_context, restore_context
from core.error_handler import enhance_error, error_enhancer, DebugContext, ErrorCategory
from core.hints import get_parameter_help, validate_tool_parameters
from core.communication import send_command, CommunicationError, TimeoutError, ConnectionError
from core.execution import get_executor, execute_command as execute_unified

from .tool_utilities import (
    detect_kernel_mode, get_command_suggestions
)

logger = logging.getLogger(__name__)

def register_execution_tools(mcp: FastMCP):
    """Register all command execution tools."""
    
    @mcp.tool()
    async def run_command(ctx: Context, action: str = "", command: str = "", validate: bool = True, resilient: bool = True, optimize: bool = True) -> Union[str, Dict[str, Any]]:
        """
        Execute a WinDbg command with validation, resilience, and performance optimization.
        
        Args:
            ctx: The MCP context
            action: Action type (empty string for execute - maintained for framework compatibility)
            command: The WinDbg command to execute
            validate: Whether to validate the command for safety (default: True)
            resilient: Whether to use resilient execution with retries (default: True)  
            optimize: Whether to use performance optimization (default: True)
            
        Returns:
            Command result or error information
        """
        logger.debug(f"Executing command: {command}, validate: {validate}, resilient: {resilient}, optimize: {optimize}")
        
        # Validate parameters
        is_valid, validation_errors = validate_tool_parameters("run_command", action, {"command": command})
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
            
            # Use unified execution system
            execution_result = execute_unified(
                command=command,
                resilient=resilient,
                optimize=optimize,
                async_mode=False  # Keep synchronous for tool compatibility
            )
            
            if execution_result.success:
                # Convert to legacy format for backward compatibility
                return execution_result.to_legacy_format()
            else:
                # Convert execution error to enhanced error format
                enhanced_error = enhance_error("execution", 
                                             command=command, 
                                             timeout_category=execution_result.timeout_category,
                                             original_error=execution_result.error)
                error_dict = enhanced_error.to_dict()
                
                # Add execution metadata
                error_dict.update({
                    "execution_method": execution_result.execution_mode.value,
                    "execution_time": execution_result.execution_time,
                    "retries_attempted": execution_result.retries_attempted,
                    "timeout_ms": execution_result.timeout_ms,
                    "timed_out": execution_result.timed_out
                })
                
                return error_dict
                    
        except Exception as e:
            enhanced_error = enhance_error("unexpected", 
                                         tool_name="run_command", 
                                         command=command, 
                                         original_error=str(e))
            return enhanced_error.to_dict()

    @mcp.tool()
    async def run_sequence(ctx: Context, commands: List[str], stop_on_error: bool = False) -> Dict[str, Any]:
        """
        Execute a sequence of WinDbg commands with error handling and performance optimization.
        
        Args:
            ctx: The MCP context
            commands: List of commands to execute in sequence
            stop_on_error: Whether to stop execution if a command fails (default: False)
            
        Returns:
            Results of all commands with execution summary and performance metrics
        """
        logger.debug(f"Executing command sequence: {len(commands)} commands, stop_on_error: {stop_on_error}")
        
        # Validate parameters - Fixed parameter validation
        if not commands:
            enhanced_error = enhance_error("parameter", 
                                         tool_name="run_sequence", 
                                         missing_param="commands")
            error_dict = enhanced_error.to_dict()
            error_dict["help"] = get_parameter_help("run_sequence")
            error_dict["error_details"] = "Parameter 'commands' is required for this operation"
            return error_dict
        
        if not isinstance(commands, list):
            enhanced_error = enhance_error("parameter", 
                                         tool_name="run_sequence", 
                                         missing_param="commands")
            error_dict = enhanced_error.to_dict()
            error_dict["help"] = get_parameter_help("run_sequence")
            error_dict["error_details"] = "Parameter 'commands' must be a list of strings"
            return error_dict
        
        # Update context for better error suggestions
        error_enhancer.update_context(DebugContext.KERNEL_MODE if detect_kernel_mode() else DebugContext.USER_MODE)
        
        # Save context before sequence execution for potential rollback
        context_manager = get_context_manager()
        context_saved = save_context(send_command)
        
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
                
                # Execute command with unified execution system
                try:
                    execution_result = execute_unified(
                        command=command,
                        resilient=True,
                        optimize=True,
                        async_mode=False
                    )
                    
                    execution_time = execution_result.execution_time
                    total_execution_time += execution_time
                    
                    if execution_result.success:
                        result = {
                            "command": command,
                            "index": i,
                            "success": True,
                            "result": execution_result.result,
                            "execution_time": execution_time,
                            "cached": execution_result.cached,
                            "retries_used": execution_result.retries_attempted,
                            "timeout_category": execution_result.timeout_category,
                            "execution_mode": execution_result.execution_mode.value,
                            "suggestions": get_command_suggestions(command, execution_result.result)
                        }
                        successful_commands += 1
                    else:
                        result = {
                            "command": command,
                            "index": i,
                            "success": False,
                            "error": execution_result.error or "Command execution failed",
                            "execution_time": execution_time,
                            "retries_used": execution_result.retries_attempted,
                            "timeout_category": execution_result.timeout_category,
                            "execution_mode": execution_result.execution_mode.value,
                            "timed_out": execution_result.timed_out
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

    @mcp.tool()
    async def breakpoint_and_continue(ctx: Context, breakpoint: str, continue_execution: bool = True, clear_existing: bool = False) -> Dict[str, Any]:
        """
        Set a breakpoint and optionally continue execution.
        
        Args:
            ctx: The MCP context
            breakpoint: Breakpoint specification (e.g., "nt!NtCreateFile", "0x12345678", "kernel32!CreateFileW")
            continue_execution: Whether to continue execution after setting breakpoint (default: True)
            clear_existing: Whether to clear existing breakpoints first (default: False)
            
        Returns:
            Results of breakpoint setting and execution control with debugging guidance
        """
        logger.debug(f"Setting breakpoint: {breakpoint}, continue: {continue_execution}, clear_existing: {clear_existing}")
        
        # Validate parameters
        if not breakpoint or not breakpoint.strip():
            enhanced_error = enhance_error("parameter", 
                                         tool_name="breakpoint_and_continue", 
                                         missing_param="breakpoint")
            return enhanced_error.to_dict()
        
        # Update context for better error suggestions
        error_enhancer.update_context(DebugContext.KERNEL_MODE if detect_kernel_mode() else DebugContext.USER_MODE)
        
        # Save context before breakpoint operations
        context_manager = get_context_manager()
        context_saved = save_context(send_command)
        
        results = []
        
        try:
            # Step 1: Clear existing breakpoints if requested
            if clear_existing:
                logger.debug("Clearing existing breakpoints")
                try:
                    clear_result = execute_unified("bc *", resilient=True, optimize=True)
                    results.append({
                        "step": "clear_existing_breakpoints",
                        "command": "bc *",
                        "success": clear_result.success,
                        "result": clear_result.result if clear_result.success else clear_result.error,
                        "execution_time": clear_result.execution_time,
                        "execution_mode": clear_result.execution_mode.value
                    })
                    if not clear_result.success:
                        logger.warning(f"Failed to clear existing breakpoints: {clear_result.error}")
                except Exception as e:
                    results.append({
                        "step": "clear_existing_breakpoints",
                        "command": "bc *",
                        "success": False,
                        "error": str(e)
                    })
            
            # Step 2: Set the new breakpoint
            bp_command = f"bp {breakpoint}"
            logger.debug(f"Setting breakpoint with command: {bp_command}")
            
            bp_result = execute_unified(bp_command, resilient=True, optimize=True)
            results.append({
                "step": "set_breakpoint",
                "command": bp_command,
                "success": bp_result.success,
                "result": bp_result.result if bp_result.success else bp_result.error,
                "execution_time": bp_result.execution_time,
                "cached": bp_result.cached,
                "execution_mode": bp_result.execution_mode.value
            })
            
            if not bp_result.success:
                return {
                    "success": False,
                    "error": f"Failed to set breakpoint: {bp_result.error}",
                    "breakpoint": breakpoint,
                    "steps_completed": results,
                    "suggestions": [
                        "Check that the symbol/address is valid",
                        "Ensure symbols are loaded (.reload)",
                        "Verify the module is loaded (lm)",
                        "Try a different breakpoint format"
                    ]
                }
            
            # Step 3: List breakpoints to confirm
            try:
                list_result = execute_unified("bl", resilient=True, optimize=True)
                results.append({
                    "step": "list_breakpoints",
                    "command": "bl",
                    "success": list_result.success,
                    "result": list_result.result if list_result.success else list_result.error,
                    "execution_time": list_result.execution_time,
                    "execution_mode": list_result.execution_mode.value
                })
            except Exception as e:
                results.append({
                    "step": "list_breakpoints",
                    "command": "bl",
                    "success": False,
                    "error": str(e)
                })
            
            # Step 4: Continue execution if requested
            execution_result = None
            if continue_execution:
                logger.debug("Continuing execution")
                try:
                    exec_result = execute_unified("g", resilient=True, optimize=True)
                    execution_result = {
                        "step": "continue_execution",
                        "command": "g",
                        "success": exec_result.success,
                        "result": exec_result.result if exec_result.success else exec_result.error,
                        "execution_time": exec_result.execution_time,
                        "execution_mode": exec_result.execution_mode.value
                    }
                    results.append(execution_result)
                    
                    if not exec_result.success:
                        logger.warning(f"Failed to continue execution: {exec_result.error}")
                        
                except Exception as e:
                    execution_result = {
                        "step": "continue_execution",
                        "command": "g",
                        "success": False,
                        "error": str(e)
                    }
                    results.append(execution_result)
            
            # Prepare comprehensive response
            total_time = sum(r.get("execution_time", 0) for r in results)
            successful_steps = sum(1 for r in results if r.get("success", False))
            
            response = {
                "success": True,
                "breakpoint": breakpoint,
                "breakpoint_set": results[1 if clear_existing else 0].get("success", False),
                "execution_continued": execution_result.get("success", False) if execution_result else False,
                "steps_completed": results,
                "summary": {
                    "total_steps": len(results),
                    "successful_steps": successful_steps,
                    "total_execution_time": total_time,
                    "context_saved": context_saved
                }
            }
            
            # Add debugging guidance
            guidance = []
            if execution_result and execution_result.get("success"):
                guidance.extend([
                    "✅ Breakpoint set and execution continued",
                    "🎯 Target will break when the specified location is hit",
                    "📊 Use 'k' to examine call stack when breakpoint hits",
                    "🔍 Use 'r' to examine registers when breakpoint hits",
                    "➡️ Use 'p' to step over or 'g' to continue after breakpoint"
                ])
            elif results[1 if clear_existing else 0].get("success", False):
                guidance.extend([
                    "✅ Breakpoint set successfully",
                    "⏸️ Use 'g' to continue execution and hit the breakpoint",
                    "🎯 Target will break when the specified location is hit"
                ])
            
            if clear_existing and results[0].get("success", False):
                guidance.append("🧹 Previous breakpoints cleared successfully")
            
            response["guidance"] = guidance
            
            # Add troubleshooting tips if something failed
            if successful_steps < len(results):
                response["troubleshooting"] = [
                    "Some steps failed - check individual step results",
                    "Verify target is connected and responsive",
                    "Check that symbols are properly loaded",
                    "Ensure the breakpoint location is valid"
                ]
            
            return response
            
        except Exception as e:
            enhanced_error = enhance_error("unexpected", 
                                         tool_name="breakpoint_and_continue", 
                                         original_error=str(e))
            error_dict = enhanced_error.to_dict()
            error_dict["partial_results"] = results
            error_dict["breakpoint"] = breakpoint
            return error_dict 