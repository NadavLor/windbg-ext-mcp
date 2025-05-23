"""
Analysis tools for WinDbg MCP server.

This module contains tools for analyzing processes, threads, memory, and kernel objects.
"""
import logging
import re
from typing import Dict, Any, List, Optional, Union
from fastmcp import FastMCP, Context

from core.communication import send_command, TimeoutError, CommunicationError
from core.context import get_context_manager
from core.error_handler import enhance_error, error_enhancer, DebugContext, ErrorCategory
from core.hints import get_parameter_help, validate_tool_parameters

logger = logging.getLogger(__name__)

def register_analysis_tools(mcp: FastMCP):
    """Register all analysis tools."""
    
    @mcp.tool()
    async def analyze_process(ctx: Context, action: str, address: str = "", save_context: bool = True) -> Union[str, Dict[str, Any]]:
        """
        Analyze processes in the debugging session with enhanced parameter validation.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "list", "switch", "info", "peb", "restore"
            address: Process address (required for "switch", "info", "peb")
            save_context: Whether to save current context before switching (default: True)
            
        Returns:
            Process analysis results or enhanced error information
        """
        logger.debug(f"Analyze process action: {action}, address: {address}")
        
        # Parameter validation
        params = {"action": action}
        if address:
            params["address"] = address
        if save_context is not True:  # Only include if not default
            params["save_context"] = save_context
            
        is_valid, validation_errors = validate_tool_parameters("analyze_process", action, params)
        if not is_valid:
            if action not in ["list", "switch", "info", "peb", "restore"]:
                # Invalid action
                help_info = get_parameter_help("analyze_process")
                enhanced_error = enhance_error("parameter", 
                                             tool_name="analyze_process", 
                                             action="", 
                                             missing_param="action")
                error_dict = enhanced_error.to_dict()
                error_dict["available_actions"] = list(help_info.get("actions", {}).keys())
                error_dict["help"] = help_info.get("actions", {}).get(action, {})
                return error_dict
            else:
                # Missing required parameter (likely address)
                enhanced_error = enhance_error("parameter", 
                                             tool_name="analyze_process", 
                                             action=action, 
                                             missing_param="address")
                return enhanced_error.to_dict()
        
        try:
            context_mgr = get_context_manager()
            
            if action == "list":
                try:
                    result = send_command("!process 0 0", timeout_ms=60000)
                    
                    # Add next steps suggestions
                    help_info = get_parameter_help("analyze_process", "list")
                    next_steps = help_info.get("next_steps", [])
                    if next_steps:
                        return {
                            "output": result,
                            "next_steps": next_steps,
                            "tip": "Copy a process address from the output above to use with other actions"
                        }
                    
                    return result
                except TimeoutError as e:
                    enhanced_error = enhance_error("timeout", command="!process 0 0", timeout_ms=60000)
                    return enhanced_error.to_dict()
            
            elif action == "switch":
                # Save current context if requested
                if save_context:
                    saved = context_mgr.push_context(send_command)
                    logger.debug(f"Saved context before process switch")
                
                # Switch to the process
                try:
                    success = context_mgr.switch_to_process(address, send_command)
                    if success:
                        error_enhancer.update_context(DebugContext.PROCESS_CONTEXT, {"current_process": address})
                        
                        # Get next steps
                        help_info = get_parameter_help("analyze_process", "switch")
                        next_steps = help_info.get("next_steps", [])
                        
                        return {
                            "message": f"Successfully switched to process {address}",
                            "next_steps": next_steps,
                            "tip": "Use analyze_process(action='restore') to return to previous context"
                        }
                    else:
                        enhanced_error = enhance_error("context", 
                                                     operation="process switch", 
                                                     context_error=f"Failed to switch to process {address}")
                        return enhanced_error.to_dict()
                except CommunicationError as e:
                    enhanced_error = enhance_error("connection", original_error=str(e))
                    return enhanced_error.to_dict()
            
            elif action == "info":
                try:
                    result = send_command(f"!process {address} 7", timeout_ms=30000)
                    return result
                except TimeoutError as e:
                    enhanced_error = enhance_error("timeout", command=f"!process {address} 7", timeout_ms=30000)
                    return enhanced_error.to_dict()
            
            elif action == "peb":
                # Check if we're in user mode (PEB is user-mode only)
                if error_enhancer.current_context == DebugContext.KERNEL_MODE:
                    enhanced_error = enhance_error("workflow", 
                                                 message="PEB (Process Environment Block) is only available in user-mode debugging")
                    error_dict = enhanced_error.to_dict()
                    error_dict["suggestions"] = [
                        "PEB is a user-mode concept and not available in kernel debugging",
                        "Use analyze_process(action='info', address='...') for kernel-mode process information",
                        "Switch to user-mode debugging to access PEB information"
                    ]
                    return error_dict
                
                if address:
                    # Switch to process first, then get PEB
                    saved = context_mgr.push_context(send_command)
                    success = context_mgr.switch_to_process(address, send_command)
                    
                    if success:
                        try:
                            peb_result = send_command("!peb", timeout_ms=15000)
                            context_mgr.pop_context(send_command)  # Restore context
                            return peb_result
                        except TimeoutError as e:
                            context_mgr.pop_context(send_command)  # Restore context
                            enhanced_error = enhance_error("timeout", command="!peb", timeout_ms=15000)
                            return enhanced_error.to_dict()
                    else:
                        enhanced_error = enhance_error("context", 
                                                     operation="PEB analysis", 
                                                     context_error=f"Failed to switch to process {address}")
                        return enhanced_error.to_dict()
                else:
                    # Get PEB for current process
                    try:
                        result = send_command("!peb", timeout_ms=15000)
                        return result
                    except TimeoutError as e:
                        enhanced_error = enhance_error("timeout", command="!peb", timeout_ms=15000)
                        return enhanced_error.to_dict()
            
            elif action == "restore":
                # Restore previous context
                success = context_mgr.pop_context(send_command)
                if success:
                    error_enhancer.update_context(DebugContext.UNKNOWN)  # Reset context
                    return "Successfully restored previous process context"
                else:
                    enhanced_error = enhance_error("context", 
                                                 operation="context restore", 
                                                 context_error="No previous context to restore")
                    return enhanced_error.to_dict()
                
        except Exception as e:
            logger.error(f"Error in analyze_process: {e}")
            enhanced_error = enhance_error("workflow", message=f"Error in process analysis: {str(e)}")
            return enhanced_error.to_dict()

    @mcp.tool()
    async def analyze_thread(ctx: Context, action: str, address: str = "", count: int = 20) -> Union[str, Dict[str, Any]]:
        """
        Analyze threads in the debugging session.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "list", "switch", "info", "stack", "all_stacks", "teb"
            address: Thread address (required for "switch", "info", "stack", "teb")
            count: Number of stack frames or threads to show (default: 20)
            
        Returns:
            Thread analysis results
        """
        logger.debug(f"Analyze thread action: {action}, address: {address}")
        
        try:
            context_mgr = get_context_manager()
            
            if action == "list":
                # List all threads
                result = send_command("!thread", timeout_ms=30000)
                return result
            
            elif action == "switch":
                if not address:
                    return {"error": "Thread address required for switch action"}
                
                success = context_mgr.switch_to_thread(address, send_command)
                if success:
                    return f"Successfully switched to thread {address}"
                else:
                    return {"error": f"Failed to switch to thread {address}"}
            
            elif action == "info":
                if not address:
                    return {"error": "Thread address required for info action"}
                
                result = send_command(f"!thread {address}", timeout_ms=20000)
                return result
            
            elif action == "stack":
                if address:
                    # Switch to thread first, then get stack
                    saved = context_mgr.push_context(send_command)
                    success = context_mgr.switch_to_thread(address, send_command)
                    
                    if success:
                        stack_result = send_command(f"k {count}", timeout_ms=15000)
                        context_mgr.pop_context(send_command)  # Restore context
                        return stack_result
                    else:
                        return {"error": f"Failed to switch to thread {address} for stack trace"}
                else:
                    # Get stack for current thread
                    result = send_command(f"k {count}", timeout_ms=15000)
                    return result
            
            elif action == "all_stacks":
                # Get stacks for multiple threads (limited to avoid overwhelming output)
                max_threads = min(count, 10)  # Limit to 10 threads max
                
                # Get thread list
                thread_list = send_command("!thread", timeout_ms=30000)
                
                # Parse thread addresses (simplified)
                thread_addresses = re.findall(r'THREAD\s+([a-fA-F0-9`]+)', thread_list)
                
                if not thread_addresses:
                    return {"error": "No threads found"}
                
                results = []
                saved_context = context_mgr.push_context(send_command)
                
                try:
                    for i, thread_addr in enumerate(thread_addresses[:max_threads]):
                        success = context_mgr.switch_to_thread(thread_addr, send_command)
                        if success:
                            stack = send_command("k 10", timeout_ms=10000)  # Shorter stacks for multiple threads
                            results.append(f"Thread {thread_addr}:\n{stack}\n")
                        else:
                            results.append(f"Thread {thread_addr}: Failed to switch\n")
                
                finally:
                    if saved_context:
                        context_mgr.pop_context(send_command)
                
                return "\n".join(results)
            
            elif action == "teb":
                if address:
                    # Switch to thread first, then get TEB
                    saved = context_mgr.push_context(send_command)
                    success = context_mgr.switch_to_thread(address, send_command)
                    
                    if success:
                        teb_result = send_command("!teb", timeout_ms=15000)
                        context_mgr.pop_context(send_command)  # Restore context
                        return teb_result
                    else:
                        return {"error": f"Failed to switch to thread {address} for TEB analysis"}
                else:
                    # Get TEB for current thread
                    result = send_command("!teb", timeout_ms=15000)
                    return result
            
            else:
                return {"error": f"Unknown action: {action}. Use 'list', 'switch', 'info', 'stack', 'all_stacks', or 'teb'"}
                
        except Exception as e:
            logger.error(f"Error in analyze_thread: {e}")
            return {"error": str(e)}

    @mcp.tool()
    async def analyze_memory(ctx: Context, action: str, address: str = "", type_name: str = "", length: int = 32) -> Union[str, Dict[str, Any]]:
        """
        Analyze memory and data structures.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "display", "type", "search", "pte", "regions"
            address: Memory address (required for most actions)
            type_name: Type name for structure display (required for "type" action)
            length: Number of bytes/elements to display (default: 32)
            
        Returns:
            Memory analysis results
        """
        logger.debug(f"Analyze memory action: {action}, address: {address}, type: {type_name}")
        
        try:
            if action == "display":
                if not address:
                    return {"error": "Memory address required for display action"}
                
                # Display memory as DWORDs by default
                result = send_command(f"dd {address} L{length//4}", timeout_ms=15000)
                return result
            
            elif action == "type":
                if not type_name:
                    return {"error": "Type name required for type action"}
                
                if address:
                    result = send_command(f"dt {type_name} {address}", timeout_ms=15000)
                else:
                    result = send_command(f"dt {type_name}", timeout_ms=15000)
                return result
            
            elif action == "search":
                if not address:
                    return {"error": "Search pattern required in address field"}
                
                # Use the address field as search pattern
                result = send_command(f"s -a 0 L?80000000 \"{address}\"", timeout_ms=30000)
                return result
            
            elif action == "pte":
                if not address:
                    return {"error": "Address required for PTE analysis"}
                
                result = send_command(f"!pte {address}", timeout_ms=15000)
                return result
            
            elif action == "regions":
                # Show memory regions
                if address:
                    result = send_command(f"!address {address}", timeout_ms=20000)
                else:
                    result = send_command("!address -summary", timeout_ms=20000)
                return result
            
            else:
                return {"error": f"Unknown action: {action}. Use 'display', 'type', 'search', 'pte', or 'regions'"}
                
        except Exception as e:
            logger.error(f"Error in analyze_memory: {e}")
            return {"error": str(e)}

    @mcp.tool()
    async def analyze_kernel(ctx: Context, action: str, address: str = "") -> Union[str, Dict[str, Any]]:
        """
        Analyze kernel objects and structures.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "object", "idt", "handles", "interrupts", "modules"
            address: Object address (required for "object", "interrupts")
            
        Returns:
            Kernel analysis results
        """
        logger.debug(f"Analyze kernel action: {action}, address: {address}")
        
        try:
            if action == "object":
                if not address:
                    return {"error": "Object address required for object analysis"}
                
                result = send_command(f"!object {address}", timeout_ms=15000)
                return result
            
            elif action == "idt":
                # Show Interrupt Descriptor Table
                result = send_command("!idt", timeout_ms=20000)
                return result
            
            elif action == "handles":
                # Show system handles
                if address:
                    result = send_command(f"!handle {address}", timeout_ms=30000)
                else:
                    result = send_command("!handle 0 f", timeout_ms=60000)
                return result
            
            elif action == "interrupts":
                if not address:
                    return {"error": "Interrupt address required"}
                
                # Display interrupt structure
                result = send_command(f"dt nt!_KINTERRUPT {address}", timeout_ms=15000)
                return result
            
            elif action == "modules":
                # List loaded modules with details
                result = send_command("lm v", timeout_ms=30000)
                return result
            
            else:
                return {"error": f"Unknown action: {action}. Use 'object', 'idt', 'handles', 'interrupts', or 'modules'"}
                
        except Exception as e:
            logger.error(f"Error in analyze_kernel: {e}")
            return {"error": str(e)} 