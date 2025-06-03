"""
Session management tools for WinDbg MCP server.

This module contains tools for managing debugging sessions, connections, and session recovery.
"""
import logging
from typing import Dict, Any, List, Optional, Union
from fastmcp import FastMCP, Context

from core.communication import test_connection
from core.performance import execute_optimized_command
from core.context import get_context_manager, save_context, restore_context
from core.error_handler import enhance_error, error_enhancer, DebugContext, ErrorCategory
from core.hints import get_parameter_help, validate_tool_parameters
from core.connection_resilience import (
    execute_resilient_command, get_connection_health, set_network_debugging_mode,
    start_connection_monitoring, stop_connection_monitoring, connection_resilience
)
from core.session_recovery import (
    capture_current_session, check_session_health, recover_session,
    get_recovery_recommendations, save_current_session, SessionState, RecoveryStrategy,
    clear_session_cache
)
from core.performance import get_performance_report
from core.async_ops import get_async_stats
from core.unified_cache import get_cache_stats

from .tool_utilities import detect_kernel_mode

logger = logging.getLogger(__name__)

def register_session_tools(mcp: FastMCP):
    """Register all session management tools."""
    
    @mcp.tool()
    async def debug_session(ctx: Context, action: str = "status") -> Dict[str, Any]:
        """
        Manage and get information about the debugging session with enhanced resilience and performance optimization.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "status", "connection", "metadata", "version", "health", "capture_state", "performance"
            
        Returns:
            Session information or status with enhanced error details if needed
        """
        logger.debug(f"Debug session action: {action}")
        
        # Validate parameters
        is_valid, validation_errors = validate_tool_parameters("debug_session", action, {"action": action})
        if not is_valid:
            enhanced_error = enhance_error("parameter", 
                                         tool_name="debug_session", 
                                         action=action, 
                                         missing_param="action")
            return enhanced_error.to_dict()
        
        try:
            if action == "connection":
                connected = test_connection()
                result = {
                    "connected": connected,
                    "status": "Connected to WinDbg extension" if connected else "Not connected to WinDbg extension"
                }
                
                if connected:
                    # Update context for better error suggestions
                    error_enhancer.update_context(DebugContext.KERNEL_MODE if detect_kernel_mode() else DebugContext.USER_MODE)
                    
                    # Add workflow suggestions
                    suggestions = error_enhancer.get_workflow_suggestions("debug_session", "connection")
                    if suggestions:
                        result["next_steps"] = suggestions
                
                return result
            
            elif action == "health":
                # Get comprehensive connection health information
                health_info = get_connection_health()
                return {
                    "debug_session_health": health_info,
                    "connection_resilience": "enabled",
                    "background_monitoring": "active" if connection_resilience.monitoring_enabled else "inactive"
                }
            
            elif action == "performance":
                # Get performance optimization status
                perf_report = get_performance_report()
                async_stats = get_async_stats()
                
                return {
                    "performance_optimization": perf_report,
                    "async_operations": async_stats,
                    "optimization_features": [
                        "Result caching with TTL",
                        "Data compression for large outputs", 
                        "Adaptive timeout management",
                        "Async command execution",
                        "Background task monitoring"
                    ]
                }
            
            elif action == "capture_state":
                # Capture current session state for recovery
                session_snapshot = capture_current_session()
                if session_snapshot:
                    saved = save_current_session()
                    return {
                        "session_captured": True,
                        "session_id": session_snapshot.session_id,
                        "debugging_mode": session_snapshot.debugging_mode,
                        "timestamp": session_snapshot.timestamp,
                        "state_saved_to_disk": saved,
                        "tip": "Session state captured - can be recovered if debugging session is interrupted"
                    }
                else:
                    enhanced_error = enhance_error("workflow", message="Failed to capture session state")
                    return enhanced_error.to_dict()
            
            elif action == "metadata" or action == "status":
                # Use optimized command execution for better reliability and performance
                try:
                    success, version_info, version_meta = execute_optimized_command("version", "quick")
                    if not success:
                        enhanced_error = enhance_error("timeout", command="version", timeout_ms=10000)
                        return enhanced_error.to_dict()
                                        
                    success, modules_info, modules_meta = execute_optimized_command("lm", "normal")
                    if not success:
                        modules_info = "Module information unavailable"
                    
                    # Check debugging mode
                    is_kernel_mode = detect_kernel_mode()
                    error_enhancer.update_context(DebugContext.KERNEL_MODE if is_kernel_mode else DebugContext.USER_MODE)
                    
                    result = {
                        "connected": True,
                        "version": version_info,
                        "modules_summary": modules_info[:500] + "..." if len(modules_info) > 500 else modules_info,
                        "debugging_mode": "kernel" if is_kernel_mode else "user",
                        "session_active": True,
                        "performance_metrics": {
                            "version_cached": version_meta.get("cached", False),
                            "version_response_time": version_meta.get("response_time", 0),
                            "modules_cached": modules_meta.get("cached", False),
                            "modules_response_time": modules_meta.get("response_time", 0),
                            "connection_health": get_connection_health()["health_score"]
                        }
                    }
                    
                    # Add workflow suggestions
                    suggestions = error_enhancer.get_workflow_suggestions("debug_session", action)
                    if suggestions:
                        result["next_steps"] = suggestions
                    
                    return result
                    
                except Exception as e:
                    enhanced_error = enhance_error("connection", original_error=str(e))
                    return enhanced_error.to_dict()
            
            elif action == "version":
                try:
                    success, version_result, metadata = execute_optimized_command("version", "quick")
                    if success:
                        return {
                            "version": version_result,
                            "performance_info": {
                                "cached": metadata.get("cached", False),
                                "response_time": metadata.get("response_time", 0),
                                "retries_used": metadata.get("retries_attempted", 0),
                                "optimization_level": metadata.get("optimization_level", "unknown")
                            }
                        }
                    else:
                        enhanced_error = enhance_error("timeout", command="version", timeout_ms=10000)
                        return enhanced_error.to_dict()
                except Exception as e:
                    enhanced_error = enhance_error("connection", original_error=str(e))
                    return enhanced_error.to_dict()
            
            else:
                # Invalid action - provide help
                help_info = get_parameter_help("debug_session")
                enhanced_error = enhance_error("parameter", 
                                             tool_name="debug_session", 
                                             action="", 
                                             missing_param="action")
                error_dict = enhanced_error.to_dict()
                error_dict["available_actions"] = ["status", "connection", "metadata", "version", "health", "capture_state", "performance"]
                error_dict["help"] = help_info
                return error_dict
                
        except Exception as e:
            enhanced_error = enhance_error("unexpected", tool_name="debug_session", original_error=str(e))
            return enhanced_error.to_dict()

    @mcp.tool()
    async def connection_manager(ctx: Context, action: str, mode: str = "", timeout_category: str = "") -> Dict[str, Any]:
        """
        Manage connection resilience, health monitoring, and network debugging modes.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "status", "health", "monitor", "stop_monitor", "set_mode", "test", "resilience"
            mode: Mode for set_mode action - "stable", "unstable", "ultra_stable"
            timeout_category: Category for timeout testing - "quick", "normal", "slow", "bulk", "analysis"
            
        Returns:
            Connection management results and recommendations
        """
        logger.debug(f"Connection manager action: {action}, mode: {mode}, timeout_category: {timeout_category}")
        
        try:
            if action == "status" or action == "health":
                health_info = get_connection_health()
                monitoring_status = "active" if connection_resilience.monitoring_enabled else "inactive"
                
                result = {
                    "connection_health": health_info,
                    "background_monitoring": monitoring_status,
                    "network_debugging_mode": connection_resilience.network_debugging_mode,
                    "last_health_check": connection_resilience.last_health_check,
                    "resilience_features": [
                        "Automatic retry with exponential backoff",
                        "Network latency compensation",
                        "Background connection monitoring",
                        "Adaptive timeout management"
                    ]
                }
                
                # Add recommendations based on health
                if health_info["health_score"] < 70:
                    result["recommendations"] = [
                        "⚠️ Connection health is suboptimal",
                        "Consider using 'set_mode' with 'unstable' or 'ultra_stable'",
                        "Check network connectivity to target VM",
                        "Enable background monitoring if not active"
                    ]
                elif health_info["health_score"] > 90:
                    result["recommendations"] = [
                        "🎯 Excellent connection health",
                        "Current settings are optimal for your environment"
                    ]
                
                return result
            
            elif action == "monitor":
                success = start_connection_monitoring()
                return {
                    "monitoring_started": success,
                    "status": "Background connection monitoring is now active" if success else "Failed to start monitoring",
                    "monitoring_interval": "30 seconds",
                    "benefits": [
                        "Proactive connection issue detection",
                        "Automatic health metrics collection",
                        "Early warning for network issues"
                    ]
                }
            
            elif action == "stop_monitor":
                success = stop_connection_monitoring()
                return {
                    "monitoring_stopped": success,
                    "status": "Background connection monitoring stopped" if success else "Failed to stop monitoring",
                    "note": "Manual health checks can still be performed"
                }
            
            elif action == "set_mode":
                if not mode:
                    return {
                        "error": "Mode parameter required",
                        "available_modes": ["stable", "unstable", "ultra_stable"],
                        "mode_descriptions": {
                            "stable": "Standard timeouts and retry patterns - good for reliable networks",
                            "unstable": "Extended timeouts and aggressive retries - for unreliable networks",
                            "ultra_stable": "Maximum timeouts and retry attempts - for very poor connections"
                        }
                    }
                
                success = set_network_debugging_mode(mode)
                if success:
                    return {
                        "mode_set": mode,
                        "status": f"Network debugging mode set to '{mode}'",
                        "applied_settings": _get_mode_settings(mode),
                        "recommendation": "Monitor connection performance to verify improvements"
                    }
                else:
                    return {
                        "error": f"Failed to set mode to '{mode}'",
                        "available_modes": ["stable", "unstable", "ultra_stable"]
                    }
            
            elif action == "test":
                # Test connection with specified timeout category
                test_category = timeout_category or "normal"
                
                try:
                    success, result, metadata = execute_resilient_command("version", test_category)
                    
                    return {
                        "connection_test": "passed" if success else "failed",
                        "test_command": "version",
                        "timeout_category": test_category,
                        "response_time": metadata.get("response_time", 0),
                        "retries_used": metadata.get("retries_attempted", 0),
                        "result_preview": result[:200] + "..." if len(result) > 200 else result,
                        "performance_rating": _rate_performance(metadata.get("response_time", 0))
                    }
                except Exception as e:
                    return {
                        "connection_test": "failed",
                        "error": str(e),
                        "recommendations": [
                            "Check WinDbg extension is loaded and responsive",
                            "Verify network connectivity to target VM",
                            "Consider using 'set_mode' with 'unstable' mode"
                        ]
                    }
            
            elif action == "resilience":
                # Get detailed resilience information
                return {
                    "resilience_status": "active",
                    "features": {
                        "automatic_retries": "enabled",
                        "exponential_backoff": "enabled",
                        "network_latency_compensation": "enabled",
                        "adaptive_timeouts": "enabled"
                    },
                    "current_settings": {
                        "network_mode": connection_resilience.network_debugging_mode,
                        "monitoring": "active" if connection_resilience.monitoring_enabled else "inactive",
                        "health_score": get_connection_health()["health_score"]
                    },
                    "usage_tips": [
                        "Use 'test' action to verify connection performance",
                        "Use 'set_mode' to optimize for your network conditions",
                        "Enable monitoring for proactive issue detection"
                    ]
                }
            
            else:
                return {
                    "error": f"Unknown action '{action}'",
                    "available_actions": ["status", "health", "monitor", "stop_monitor", "set_mode", "test", "resilience"],
                    "help": get_parameter_help("connection_manager")
                }
                
        except Exception as e:
            enhanced_error = enhance_error("unexpected", tool_name="connection_manager", original_error=str(e))
            return enhanced_error.to_dict()

    @mcp.tool()
    async def session_manager(ctx: Context, action: str, strategy: str = "") -> Dict[str, Any]:
        """
        Manage session recovery, health monitoring, and session state persistence.
        
        Args:
            ctx: The MCP context
            action: Action to perform - "status", "capture", "recover", "health", "save", "list_strategies", "cache_stats"
            strategy: Recovery strategy for recover action - "automatic", "manual", "conservative"
            
        Returns:
            Session management results and recovery information
        """
        logger.debug(f"Session manager action: {action}, strategy: {strategy}")
        
        try:
            if action == "status":
                session_health = check_session_health()
                current_session = capture_current_session()
                
                result = {
                    "session_health": session_health,
                    "current_session": {
                        "session_id": current_session.session_id if current_session else "none",
                        "debugging_mode": current_session.debugging_mode if current_session else "unknown",
                        "timestamp": current_session.timestamp if current_session else "none",
                        "status": "active" if current_session else "inactive"
                    },
                    "recovery_available": current_session is not None,
                    "session_features": [
                        "Automatic session state capture",
                        "Intelligent recovery strategies",
                        "Session health monitoring",
                        "Persistent session storage"
                    ]
                }
                
                # Add recommendations based on session health
                if session_health and session_health.get("health_score", 0) < 70:
                    result["recommendations"] = [
                        "⚠️ Session health is suboptimal",
                        "Consider capturing current state with 'capture' action",
                        "Check connection stability",
                        "Verify debugging target is responsive"
                    ]
                
                return result
            
            elif action == "capture":
                session_snapshot = capture_current_session()
                if session_snapshot:
                    saved = save_current_session()
                    return {
                        "capture_successful": True,
                        "session_id": session_snapshot.session_id,
                        "debugging_mode": session_snapshot.debugging_mode,
                        "timestamp": session_snapshot.timestamp,
                        "saved_to_disk": saved,
                        "captured_data": [
                            "Current debugging context",
                            "Active breakpoints",
                            "Process/thread information",
                            "Module load state",
                            "Performance metrics"
                        ],
                        "next_steps": "Session can now be recovered using 'recover' action if needed"
                    }
                else:
                    return {
                        "capture_successful": False,
                        "error": "Failed to capture current session state",
                        "possible_causes": [
                            "No active debugging session",
                            "Connection to WinDbg extension unavailable",
                            "Insufficient privileges for state capture"
                        ]
                    }
            
            elif action == "recover":
                if not strategy:
                    return {
                        "error": "Strategy parameter required for recovery",
                        "available_strategies": ["automatic", "manual", "conservative"],
                        "strategy_descriptions": {
                            "automatic": "Fully automated recovery with best practices",
                            "manual": "Step-by-step recovery with user confirmation",
                            "conservative": "Safe recovery focusing on essential state only"
                        }
                    }
                
                try:
                    recovery_strategy = RecoveryStrategy(strategy)
                    success, recovery_result = recover_session(recovery_strategy)
                    
                    if success:
                        return {
                            "recovery_successful": True,
                            "strategy_used": strategy,
                            "recovery_details": recovery_result,
                            "restored_state": [
                                "Debugging context",
                                "Connection parameters",
                                "Session preferences"
                            ],
                            "verification": "Run debug_session status to verify recovery"
                        }
                    else:
                        recommendations = get_recovery_recommendations()
                        return {
                            "recovery_successful": False,
                            "strategy_attempted": strategy,
                            "error": recovery_result,
                            "recommendations": recommendations,
                            "alternative_strategies": [s for s in ["automatic", "manual", "conservative"] if s != strategy]
                        }
                        
                except ValueError:
                    return {
                        "error": f"Invalid recovery strategy '{strategy}'",
                        "available_strategies": ["automatic", "manual", "conservative"]
                    }
            
            elif action == "health":
                session_health = check_session_health()
                
                if session_health:
                    return {
                        "session_health": session_health,
                        "health_assessment": _assess_session_health(session_health),
                        "monitoring_active": True,
                        "health_tips": _get_health_tips(session_health)
                    }
                else:
                    return {
                        "session_health": "unavailable",
                        "health_assessment": "Cannot assess - no active session or connection issues",
                        "monitoring_active": False,
                        "recommendations": [
                            "Check connection with debug_session",
                            "Ensure WinDbg extension is loaded",
                            "Verify debugging target is accessible"
                        ]
                    }
            
            elif action == "save":
                saved = save_current_session()
                return {
                    "save_successful": saved,
                    "status": "Session state saved to persistent storage" if saved else "Failed to save session state",
                    "storage_location": "Local session recovery files",
                    "retention": "Session data retained until next save operation"
                }
            
            elif action == "list_strategies":
                return {
                    "available_strategies": ["automatic", "manual", "conservative"],
                    "strategy_details": {
                        "automatic": {
                            "description": "Fully automated recovery with best practices",
                            "use_when": "Standard recovery scenarios",
                            "features": ["Auto-detection of recovery needs", "Intelligent state restoration", "Minimal user intervention"]
                        },
                        "manual": {
                            "description": "Step-by-step recovery with user confirmation",
                            "use_when": "Complex or unusual recovery scenarios",
                            "features": ["User-guided recovery", "Detailed step confirmation", "Maximum control"]
                        },
                        "conservative": {
                            "description": "Safe recovery focusing on essential state only",
                            "use_when": "When stability is critical",
                            "features": ["Minimal state changes", "Essential recovery only", "High stability"]
                        }
                    },
                    "recommendation": "Use 'automatic' for most scenarios, 'conservative' for critical environments"
                }
            
            elif action == "clear_cache":
                clear_session_cache()
                return {
                    "cache_cleared": True,
                    "status": "Session cache cleared"
                }
            
            elif action == "cache_stats":
                cache_stats = get_cache_stats()
                return {
                    "cache_stats": cache_stats
                }
            
            else:
                return {
                    "error": f"Unknown action '{action}'",
                    "available_actions": ["status", "capture", "recover", "health", "save", "list_strategies", "clear_cache", "cache_stats"],
                    "help": get_parameter_help("session_manager")
                }
                
        except Exception as e:
            enhanced_error = enhance_error("unexpected", tool_name="session_manager", original_error=str(e))
            return enhanced_error.to_dict()

def _get_mode_settings(mode: str) -> Dict[str, str]:
    """Get the settings applied for a network debugging mode."""
    settings = {
        "stable": {
            "base_timeout": "15 seconds",
            "max_retries": "3",
            "backoff_multiplier": "1.5",
            "network_compensation": "minimal"
        },
        "unstable": {
            "base_timeout": "30 seconds",
            "max_retries": "5",
            "backoff_multiplier": "2.0",
            "network_compensation": "aggressive"
        },
        "ultra_stable": {
            "base_timeout": "60 seconds",
            "max_retries": "7",
            "backoff_multiplier": "2.5",
            "network_compensation": "maximum"
        }
    }
    return settings.get(mode, {})

def _rate_performance(response_time: float) -> str:
    """Rate the performance based on response time."""
    if response_time < 1.0:
        return "excellent"
    elif response_time < 3.0:
        return "good"
    elif response_time < 10.0:
        return "fair"
    else:
        return "poor"

def _assess_session_health(health_data: Dict[str, Any]) -> str:
    """Assess overall session health."""
    health_score = health_data.get("health_score", 0)
    
    if health_score >= 90:
        return "excellent"
    elif health_score >= 75:
        return "good"
    elif health_score >= 50:
        return "fair"
    else:
        return "poor"

def _get_health_tips(health_data: Dict[str, Any]) -> List[str]:
    """Get health improvement tips based on session health data."""
    tips = []
    health_score = health_data.get("health_score", 0)
    
    if health_score < 70:
        tips.append("🔄 Consider capturing session state regularly")
        tips.append("📊 Monitor connection stability with connection_manager")
    
    if health_score < 50:
        tips.append("⚠️ Session may benefit from recovery using 'conservative' strategy")
        tips.append("🔧 Check network connectivity and VM performance")
    
    if not tips:
        tips.append("✅ Session health is good - no immediate action needed")
    
    return tips 