"""
Support and troubleshooting tools for WinDbg MCP server.

This module contains tools for troubleshooting issues and getting help.
"""
import logging
from typing import Dict, Any, List, Optional, Union
from fastmcp import FastMCP, Context

from core.communication import send_command, test_connection
from core.error_handler import enhance_error, error_enhancer, DebugContext
from core.hints import get_parameter_help

logger = logging.getLogger(__name__)

def register_support_tools(mcp: FastMCP):
    """Register all support and troubleshooting tools."""
    
    @mcp.tool()
    async def troubleshoot(ctx: Context, action: str) -> Union[str, Dict[str, Any]]:
        """
        Troubleshoot common debugging issues.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "symbols", "exception", "analyze", "connection"
            
        Returns:
            Troubleshooting results and recommendations
        """
        logger.debug(f"Troubleshoot action: {action}")
        
        try:
            if action == "symbols":
                results = []
                results.append("=== SYMBOL TROUBLESHOOTING ===")
                
                # Check symbol path
                sympath = send_command(".sympath", timeout_ms=10000)
                results.append(f"\nSymbol path:\n{sympath}")
                
                # Check critical modules
                for module in ["nt", "ntoskrnl", "ntdll"]:
                    try:
                        module_info = send_command(f"lmv m {module}", timeout_ms=10000)
                        results.append(f"\n{module} module:\n{module_info}")
                    except:
                        results.append(f"\n{module} module: Not found")
                
                # Try symbol reload
                results.append("\nAttempting symbol reload...")
                reload_result = send_command(".reload", timeout_ms=30000)
                results.append(reload_result)
                
                return "\n".join(results)
            
            elif action == "exception":
                # Analyze current exception
                result = send_command("!analyze -v", timeout_ms=60000)
                return f"=== EXCEPTION ANALYSIS ===\n{result}"
            
            elif action == "analyze":
                # General system analysis
                result = send_command("!analyze -v", timeout_ms=60000)
                return f"=== SYSTEM ANALYSIS ===\n{result}"
            
            elif action == "connection":
                # Test connection and provide status
                connected = test_connection()
                if connected:
                    version = send_command("version", timeout_ms=5000)
                    return f"✓ Connection OK\n\nWinDbg Version:\n{version}"
                else:
                    return "✗ Connection Failed\n\nEnsure:\n1. WinDbg extension is loaded\n2. Extension DLL is correct version\n3. Named pipe is available"
            
            else:
                return {"error": f"Unknown action: {action}. Use 'symbols', 'exception', 'analyze', or 'connection'"}
                
        except Exception as e:
            logger.error(f"Error in troubleshoot: {e}")
            return {"error": str(e)}

    @mcp.tool()
    async def get_help(ctx: Context, tool_name: str = "", action: str = "") -> Dict[str, Any]:
        """
        Get help, examples, and parameter information for MCP tools.
        
        Args:
            ctx: The MCP context
            tool_name: Name of the tool to get help for (empty for list of all tools)
            action: Specific action to get help for (empty for all actions)
            
        Returns:
            Help information, examples, and parameter details
        """
        logger.debug(f"Getting help for tool: {tool_name}, action: {action}")
        
        if not tool_name:
            # List all available tools
            available_tools = [
                "debug_session", "run_command", "run_sequence", "breakpoint_and_continue",
                "analyze_process", "analyze_thread", "analyze_memory", "analyze_kernel",
                "connection_manager", "session_manager", 
                "performance_manager", "async_manager",
                "troubleshoot", "get_help"
            ]
            
            return {
                "available_tools": available_tools,
                "description": "WinDbg MCP Server - Enhanced Debugging Edition with LLM Automation",
                "usage": "Use get_help(tool_name='tool_name') to get help for a specific tool",
                "examples": [
                    "get_help(tool_name='analyze_process')",
                    "get_help(tool_name='run_command')",
                    "get_help(tool_name='breakpoint_and_continue')",
                    "get_help(tool_name='analyze_process', action='switch')"
                ],
                "tool_categories": {
                    "session_management": ["debug_session", "connection_manager", "session_manager"],
                    "command_execution": ["run_command", "run_sequence", "breakpoint_and_continue"],
                    "analysis": ["analyze_process", "analyze_thread", "analyze_memory", "analyze_kernel"],
                    "performance": ["performance_manager", "async_manager"],
                    "support": ["troubleshoot", "get_help"]
                },
                "automation_features": {
                    "execution_control": "✅ Now enabled for LLM automation (g, p, t, gu, wt)",
                    "breakpoint_control": "✅ Now enabled for LLM automation (bp, bc, bd, be, etc.)",
                    "context_switching": "✅ Now enabled for LLM automation (.thread, .process)",
                    "combined_operations": "✅ Use breakpoint_and_continue for one-step breakpoint + execution"
                },
                "tip": "All tools now provide enhanced error messages with suggestions and examples when something goes wrong"
            }
        
        # Get help for specific tool
        help_info = get_parameter_help(tool_name, action)
        
        if not help_info:
            enhanced_error = enhance_error("parameter", 
                                         tool_name="get_help", 
                                         action="help", 
                                         missing_param="tool_name")
            error_dict = enhanced_error.to_dict()
            error_dict["available_tools"] = [
                "debug_session", "run_command", "run_sequence", "breakpoint_and_continue",
                "analyze_process", "analyze_thread", "analyze_memory", "analyze_kernel",
                "connection_manager", "session_manager",
                "performance_manager", "async_manager", 
                "troubleshoot", "get_help"
            ]
            return error_dict
        
        # Add debugging context information
        current_context = error_enhancer.current_context
        context_info = {
            "current_debugging_context": current_context.value,
            "context_specific_notes": []
        }
        
        if current_context == DebugContext.KERNEL_MODE:
            context_info["context_specific_notes"].append("You are in kernel-mode debugging - some user-mode tools (like PEB/TEB) won't work")
        elif current_context == DebugContext.USER_MODE:
            context_info["context_specific_notes"].append("You are in user-mode debugging - kernel-specific tools may have limited functionality")
        
        help_info["context"] = context_info
        
        # Add tool-specific tips based on the tool name
        if tool_name == "run_command":
            help_info["performance_tips"] = [
                "Use resilient=True (default) for unstable VM connections",
                "Use optimize=True (default) for better caching and performance", 
                "Commands are automatically categorized for optimal timeouts"
            ]
            help_info["execution_control_tips"] = [
                "✅ Execution control commands now enabled for LLM automation:",
                "  • 'g' - Continue execution",
                "  • 'p' - Step over (execute one instruction)",
                "  • 't' - Step into (trace one instruction)",
                "  • 'gu' - Go up (execute until function return)",
                "  • 'wt' - Watch and trace execution",
                "✅ Breakpoint commands now enabled for LLM automation:",
                "  • 'bp <address>' - Set breakpoint",
                "  • 'bc <id>' - Clear breakpoint",
                "  • 'bd <id>' - Disable breakpoint",
                "  • 'be <id>' - Enable breakpoint",
                "💡 Use breakpoint_and_continue() for combined operations"
            ]
        elif tool_name == "breakpoint_and_continue":
            help_info["usage_examples"] = [
                "breakpoint_and_continue(breakpoint='nt!NtCreateFile')",
                "breakpoint_and_continue(breakpoint='kernel32!CreateFileW', continue_execution=True)",
                "breakpoint_and_continue(breakpoint='0x12345678', clear_existing=True)",
                "breakpoint_and_continue(breakpoint='ntdll!NtOpenFile', continue_execution=False)"
            ]
            help_info["automation_benefits"] = [
                "🚀 Combines breakpoint setting + execution control in one operation",
                "🎯 Optimized for LLM debugging workflows",
                "🔄 Automatic context saving and error recovery",
                "📊 Detailed step-by-step execution reporting",
                "💡 Built-in guidance for next debugging steps"
            ]
        elif tool_name in ["analyze_process", "analyze_thread", "analyze_memory", "analyze_kernel"]:
            help_info["analysis_tips"] = [
                "Use save_context=True (default) when switching contexts",
                "Tools automatically detect kernel vs user mode",
                "Enhanced error messages guide you when operations fail"
            ]
        elif tool_name in ["performance_manager", "async_manager"]:
            help_info["performance_tips"] = [
                "Set optimization level to 'aggressive' for VM debugging",
                "Use async execution for multiple independent commands",
                "Monitor performance reports to optimize your workflow"
            ]
        
        return help_info 

    @mcp.tool()
    async def diagnose_hybrid_connection() -> str:
        """
        Perform comprehensive connection diagnostics for the hybrid architecture.
        
        This tool helps troubleshoot communication issues between:
        - Cursor ↔ Python MCP Server (stdio transport)
        - Python MCP Server ↔ WinDbg Extension (named pipe)
        - WinDbg ↔ Debugging Target (network/serial)
        
        Returns:
            Detailed diagnostic report with recommendations
        """
        try:
            from core.communication import (
                diagnose_connection_issues, get_connection_health,
                test_connection, test_target_connection
            )
            
            # Get comprehensive diagnostics
            diagnostics = diagnose_connection_issues()
            health = get_connection_health()
            
            # Build detailed report
            report = ["🔍 HYBRID ARCHITECTURE DIAGNOSTICS", "=" * 50, ""]
            
            # MCP Server Status
            report.extend([
                "📡 MCP Server Status:",
                f"  • Architecture: Hybrid (stdio + named pipe)",
                f"  • Timestamp: {diagnostics['timestamp']}",
                ""
            ])
            
            # Extension Connection Status
            report.extend([
                "🔌 WinDbg Extension Connection:",
                f"  • Available: {'✓' if diagnostics['extension_available'] else '✗'}",
                f"  • Consecutive failures: {health['consecutive_failures']}",
                ""
            ])
            
            # Target Connection Status
            report.extend([
                "🎯 Debugging Target Connection:",
                f"  • Connected: {'✓' if diagnostics['target_connected'] else '✗'}",
                f"  • Network debugging: {'✓' if diagnostics['network_debugging'] else '✗'}",
                f"  • Mode: {health['debugging_mode']}",
                ""
            ])
            
            if diagnostics.get('target_status'):
                report.extend([
                    f"  • Status: {diagnostics['target_status']}",
                    ""
                ])
            
            # Health Information
            if health.get('last_error'):
                report.extend([
                    "⚠ Last Error:",
                    f"  • {health['last_error']}",
                    ""
                ])
            
            # Recommendations
            if diagnostics.get('recommendations'):
                report.extend([
                    "💡 Recommendations:",
                ])
                for rec in diagnostics['recommendations']:
                    report.append(f"  • {rec}")
                report.append("")
            
            # Network Debugging Specific Advice
            if diagnostics['network_debugging']:
                report.extend([
                    "🌐 Network Debugging Tips:",
                    "  • Packet loss is common - retry logic is active",
                    "  • Use longer timeouts for complex commands", 
                    "  • Consider '.restart' if target becomes unresponsive",
                    "  • Check VM network settings if connection is unstable",
                    ""
                ])
            
            return "\n".join(report)
            
        except Exception as e:
            return f"❌ Diagnostic error: {str(e)}"

    @mcp.tool()
    async def test_windbg_communication() -> str:
        """
        Test communication with WinDbg extension and provide detailed results.
        
        This tool specifically tests the named pipe communication between
        the Python MCP server and the WinDbg extension.
        
        Returns:
            Communication test results and recommendations
        """
        try:
            from core.communication import (
                test_connection, test_target_connection, send_command,
                get_connection_health, NetworkDebuggingError
            )
            
            results = ["🧪 WINDBG COMMUNICATION TEST", "=" * 40, ""]
            
            # Test 1: Basic extension connection
            try:
                connected = test_connection()
                if connected:
                    results.append("✅ Test 1: Extension connection - PASSED")
                else:
                    results.append("❌ Test 1: Extension connection - FAILED")
            except Exception as e:
                results.append(f"❌ Test 1: Extension connection - ERROR: {e}")
            
            results.append("")
            
            # Test 2: Target connection
            try:
                target_connected, target_status = test_target_connection()
                if target_connected:
                    results.append(f"✅ Test 2: Target connection - PASSED ({target_status})")
                else:
                    results.append(f"❌ Test 2: Target connection - FAILED ({target_status})")
            except NetworkDebuggingError as e:
                results.append(f"⚠ Test 2: Network debugging issue - {e}")
            except Exception as e:
                results.append(f"❌ Test 2: Target connection - ERROR: {e}")
            
            results.append("")
            
            # Test 3: Simple command execution
            try:
                result = send_command("version", timeout_ms=5000)
                if result and not result.startswith("Error:"):
                    results.append("✅ Test 3: Command execution - PASSED")
                    results.append(f"    Response: {result[:100]}...")
                else:
                    results.append(f"❌ Test 3: Command execution - FAILED: {result}")
            except NetworkDebuggingError as e:
                results.append(f"⚠ Test 3: Network debugging issue - {e}")
            except Exception as e:
                results.append(f"❌ Test 3: Command execution - ERROR: {e}")
            
            results.append("")
            
            # Show basic summary without misleading status indicators
            health = get_connection_health()
            results.extend([
                "📊 Summary:",
                f"  • Debugging mode: {health['debugging_mode']}",
                f"  • Connection failures: {health['consecutive_failures']}",
            ])
            
            if health.get('last_successful_command'):
                results.append(f"  • Last success: {health['last_successful_command']}")
            
            return "\n".join(results)
            
        except Exception as e:
            return f"❌ Communication test error: {str(e)}"

    @mcp.tool()
    async def network_debugging_troubleshoot() -> str:
        """
        Specialized troubleshooting for network debugging connection issues.
        
        This tool provides specific guidance for VM-based kernel debugging
        scenarios where packet loss and connection instability are common.
        
        Returns:
            Network debugging troubleshooting guide and status
        """
        try:
            from core.communication import get_connection_health, send_command, NetworkDebuggingError
            
            guide = ["🌐 NETWORK DEBUGGING TROUBLESHOOT", "=" * 45, ""]
            
            # Check current status
            health = get_connection_health()
            
            guide.extend([
                "📋 Current Status:",
                f"  • Debugging mode: {health['debugging_mode']}",
                f"  • Connection failures: {health['consecutive_failures']}",
                ""
            ])
            
            # Try to detect network debugging issues
            network_issues_detected = False
            
            try:
                # Try a simple command to test responsiveness
                result = send_command("version", timeout_ms=3000)
            except NetworkDebuggingError as e:
                network_issues_detected = True
                guide.extend([
                    "⚠ NETWORK ISSUES DETECTED:",
                    f"  • {str(e)}",
                    ""
                ])
            except Exception as e:
                guide.extend([
                    "❌ Communication Error:",
                    f"  • {str(e)}",
                    ""
                ])
            
            # Provide troubleshooting steps
            guide.extend([
                "🛠 TROUBLESHOOTING STEPS:",
                "",
                "1. Verify WinDbg Connection:",
                "   • Check if WinDbg shows 'Connected to...' status",
                "   • Run 'vertarget' in WinDbg command window",
                "   • Ensure debugging session is active",
                "",
                "2. Network Connection:",
                "   • Verify VM network adapter is connected",
                "   • Check firewall settings on both host and VM",
                "   • Try '.restart' command if target is unresponsive",
                "",
                "3. WinDbg Extension:",
                "   • Verify extension is loaded: '.chain'",
                "   • Check extension status: 'mcpstatus'",
                "   • Reload if needed: '.unload extension; .load extension'",
                "",
                "4. Advanced Troubleshooting:",
                "   • Increase timeout values for network debugging",
                "   • Clear all breakpoints: 'bc *'",
                "   • Reboot target VM if completely unresponsive",
                "   • Check VM debugging settings (bcdedit)",
                ""
            ])
            
            if network_issues_detected:
                guide.extend([
                    "🎯 IMMEDIATE ACTIONS:",
                    "   • The MCP server will automatically retry failed commands",
                    "   • Timeout values are increased for network debugging",
                    "   • Connection monitoring is active",
                    "   • Consider running simpler commands first",
                    ""
                ])
            
            return "\n".join(guide)
            
        except Exception as e:
            return f"❌ Troubleshooting error: {str(e)}" 