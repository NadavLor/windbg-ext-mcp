"""
Callback analysis tools for WinDbg MCP extension.
"""

import logging
import time
from typing import Dict, Any, Optional
from fastmcp import FastMCP, Context

from core.communication import send_command
from core.performance import execute_optimized_command

logger = logging.getLogger(__name__)


def parse_callback_line(line: str) -> Optional[Dict[str, str]]:
    """Parse a single callback line from dps output."""
    if not line.strip():
        return None
    
    # Look for pattern like: address  value
    parts = line.split()
    if len(parts) >= 2:
        slot_address = parts[0].strip()
        callback_address = parts[1].strip()
        
        # Validate it looks like hex addresses
        if slot_address.startswith('0x') or slot_address.startswith('ffff'):
            if callback_address.startswith('0x') or callback_address.startswith('ffff'):
                # Skip null callbacks (all zeros)
                if callback_address.replace('0', '').replace('x', '').strip():
                    return {
                        "slot_address": slot_address,
                        "callback_address": callback_address
                    }
    
    return None


def register_callback_tools(mcp: FastMCP):
    """Register callback analysis tools."""
    
    @mcp.tool()
    async def mcp_list_callbacks(ctx: Context, callback_type: str = "all", include_addresses: bool = True, resolve_modules: bool = True, timeout_ms: int = 60000) -> Dict[str, Any]:
        """
        Unified callback enumeration command that consolidates all core callback lists.
        
        This command internally gathers all core callback lists (process, thread, image, 
        registry, object manager) and outputs a consolidated report. It automatically 
        resolves addresses to module names, highlighting any third-party (EDR) involvement.
        
        Args:
            ctx: The MCP context
            callback_type: Type of callbacks to enumerate - "all", "process", "thread", "image", "registry", "object" (default: "all")
            include_addresses: Whether to include raw addresses in output (default: True)
            resolve_modules: Whether to resolve addresses to module names (default: True)
            timeout_ms: Timeout for each callback enumeration in milliseconds (default: 60000)
            
        Returns:
            Consolidated callback enumeration results with third-party driver detection
        """
        logger.info(f"Starting unified callback enumeration: type={callback_type}, resolve_modules={resolve_modules}")
        
        # Validate parameters
        valid_types = ["all", "process", "thread", "image", "registry", "object"]
        if callback_type not in valid_types:
            return {
                "error": f"Invalid callback_type '{callback_type}'. Must be one of: {', '.join(valid_types)}",
                "valid_types": valid_types,
                "help": "Use 'all' to enumerate all callback types, or specify a specific type"
            }
        
        # Initialize results structure
        results = {
            "command": "mcp_list_callbacks",
            "filter_applied": callback_type,
            "callback_enumeration": {},
            "summary": {
                "total_callbacks": 0,
                "third_party_drivers": [],
                "unique_drivers": 0,
                "execution_time": 0
            },
            "metadata": {
                "command_info": "Unified callback enumeration across all callback types",
                "supported_types": valid_types,
                "edr_detection_note": "Third-party drivers may indicate EDR/AV presence",
                "timestamp": time.time()
            }
        }
        
        start_time = time.time()
        callbacks = results["callback_enumeration"]
        total_callbacks = 0
        third_party_drivers = set()
        
        try:
            # 1. Enumerate Process Creation Callbacks
            if callback_type in ["all", "process"]:
                try:
                    logger.debug("Enumerating process creation callbacks")
                    success, output, metadata = execute_optimized_command("dps nt!PspCreateProcessNotifyRoutine", "bulk")
                    
                    if success and output.strip():
                        parsed_callbacks = []
                        callback_count = 0
                        
                        for line in output.strip().split('\n'):
                            parsed = parse_callback_line(line)
                            if parsed is None:
                                continue  # Skip invalid or empty lines
                            
                            callback_entry = {
                                "slot_address": parsed["slot_address"],
                                "callback_address": parsed["callback_address"],
                                "index": callback_count
                            }
                            
                            # Try to resolve the callback address to module+function
                            if resolve_modules:
                                target_addr = parsed["callback_address"]
                                try:
                                    ln_success, ln_output, _ = execute_optimized_command(f"ln {target_addr}", "quick")
                                    if ln_success and ln_output.strip():
                                        # Parse ln output for module and function
                                        if '!' in ln_output:
                                            module_func = ln_output.split('!')[0].strip()
                                            if module_func:
                                                callback_entry["module"] = module_func
                                                callback_entry["resolved"] = True
                                                
                                                # Check if third-party driver
                                                core_modules = ["nt", "ntoskrnl", "hal", "ndis", "tcpip", "ci", "fltmgr"]
                                                if module_func.lower() not in core_modules:
                                                    callback_entry["third_party"] = True
                                                    third_party_drivers.add(module_func)
                                                else:
                                                    callback_entry["third_party"] = False
                                except Exception as e:
                                    logger.debug(f"Failed to resolve address {target_addr}: {e}")
                                    callback_entry["resolved"] = False
                            
                            parsed_callbacks.append(callback_entry)
                            callback_count += 1
                        
                        callbacks["process_creation"] = {
                            "type": "Process Creation Callbacks",
                            "source_symbol": "nt!PspCreateProcessNotifyRoutine",
                            "count": callback_count,
                            "parsed_callbacks": parsed_callbacks,
                            "raw_output": output if include_addresses else "[Hidden - use include_addresses=true]"
                        }
                        total_callbacks += callback_count
                        
                    else:
                        callbacks["process_creation"] = {
                            "type": "Process Creation Callbacks",
                            "error": "Failed to enumerate or no callbacks found"
                        }
                        
                except Exception as e:
                    callbacks["process_creation"] = {
                        "type": "Process Creation Callbacks",
                        "error": f"Exception during enumeration: {str(e)}"
                    }
            
            # 2. Enumerate Thread Creation Callbacks  
            if callback_type in ["all", "thread"]:
                try:
                    logger.debug("Enumerating thread creation callbacks")
                    success, output, metadata = execute_optimized_command("dps nt!PspCreateThreadNotifyRoutine", "bulk")
                    
                    if success and output.strip():
                        parsed_callbacks = []
                        callback_count = 0
                        
                        for line in output.strip().split('\n'):
                            parsed = parse_callback_line(line)
                            if parsed is None:
                                continue  # Skip invalid or empty lines
                            
                            callback_entry = {
                                "slot_address": parsed["slot_address"],
                                "callback_address": parsed["callback_address"],
                                "index": callback_count
                            }
                            
                            if resolve_modules:
                                target_addr = parsed["callback_address"]
                                try:
                                    ln_success, ln_output, _ = execute_optimized_command(f"ln {target_addr}", "quick")
                                    if ln_success and '!' in ln_output:
                                        module_func = ln_output.split('!')[0].strip()
                                        if module_func:
                                            callback_entry["module"] = module_func
                                            callback_entry["resolved"] = True
                                            
                                            core_modules = ["nt", "ntoskrnl", "hal", "ndis", "tcpip"]
                                            if module_func.lower() not in core_modules:
                                                callback_entry["third_party"] = True
                                                third_party_drivers.add(module_func)
                                            else:
                                                callback_entry["third_party"] = False
                                except Exception:
                                    callback_entry["resolved"] = False
                            
                            parsed_callbacks.append(callback_entry)
                            callback_count += 1
                        
                        callbacks["thread_creation"] = {
                            "type": "Thread Creation Callbacks",
                            "source_symbol": "nt!PspCreateThreadNotifyRoutine", 
                            "count": callback_count,
                            "parsed_callbacks": parsed_callbacks,
                            "raw_output": output if include_addresses else "[Hidden]"
                        }
                        total_callbacks += callback_count
                        
                    else:
                        callbacks["thread_creation"] = {
                            "type": "Thread Creation Callbacks",
                            "error": "Failed to enumerate or no callbacks found"
                        }
                        
                except Exception as e:
                    callbacks["thread_creation"] = {
                        "type": "Thread Creation Callbacks", 
                        "error": f"Exception during enumeration: {str(e)}"
                    }
            
            # 3. Enumerate Image Load Callbacks
            if callback_type in ["all", "image"]:
                try:
                    logger.debug("Enumerating image load callbacks")
                    success, output, metadata = execute_optimized_command("dps nt!PspLoadImageNotifyRoutine", "bulk")
                    
                    if success and output.strip():
                        parsed_callbacks = []
                        callback_count = 0
                        
                        for line in output.strip().split('\n'):
                            parsed = parse_callback_line(line)
                            if parsed is None:
                                continue  # Skip invalid or empty lines
                            
                            callback_entry = {
                                "slot_address": parsed["slot_address"],
                                "callback_address": parsed["callback_address"],
                                "index": callback_count
                            }
                            
                            if resolve_modules:
                                target_addr = parsed["callback_address"]
                                try:
                                    ln_success, ln_output, _ = execute_optimized_command(f"ln {target_addr}", "quick")
                                    if ln_success and '!' in ln_output:
                                        module_func = ln_output.split('!')[0].strip()
                                        if module_func:
                                            callback_entry["module"] = module_func
                                            callback_entry["resolved"] = True
                                            
                                            core_modules = ["nt", "ntoskrnl", "hal", "ndis", "tcpip", "ci", "fltmgr"]
                                            if module_func.lower() not in core_modules:
                                                callback_entry["third_party"] = True
                                                third_party_drivers.add(module_func)
                                            else:
                                                callback_entry["third_party"] = False
                                except Exception:
                                    callback_entry["resolved"] = False
                            
                            parsed_callbacks.append(callback_entry)
                            callback_count += 1
                        
                        callbacks["image_load"] = {
                            "type": "Image Load Callbacks",
                            "source_symbol": "nt!PspLoadImageNotifyRoutine",
                            "count": callback_count,
                            "parsed_callbacks": parsed_callbacks,
                            "raw_output": output if include_addresses else "[Hidden]"
                        }
                        total_callbacks += callback_count
                        
                    else:
                        callbacks["image_load"] = {
                            "type": "Image Load Callbacks",
                            "error": "Failed to enumerate or no callbacks found"
                        }
                        
                except Exception as e:
                    callbacks["image_load"] = {
                        "type": "Image Load Callbacks",
                        "error": f"Exception during enumeration: {str(e)}"
                    }
            
            # 4. Enumerate Registry Callbacks
            if callback_type in ["all", "registry"]:
                try:
                    logger.debug("Enumerating registry callbacks")
                    # Try multiple approaches for registry callbacks
                    registry_callbacks = {
                        "type": "Registry Callbacks",
                        "source_symbols": ["nt!CmCallbackListHead", "nt!CallbackListHead"],
                        "parsed_callbacks": [],
                        "count": 0,
                        "note": "Registry notification callbacks for monitoring registry operations"
                    }
                    
                    # Method 1: Try CmCallbackListHead
                    try:
                        success, output, _ = execute_optimized_command("dps nt!CmCallbackListHead", "bulk")
                        if success and output.strip():
                            parsed_callbacks = []
                            callback_count = 0
                            
                            for line in output.strip().split('\n'):
                                parsed = parse_callback_line(line)
                                if parsed is None:
                                    continue
                                
                                callback_entry = {
                                    "slot_address": parsed["slot_address"],
                                    "callback_address": parsed["callback_address"],
                                    "index": callback_count,
                                    "method": "CmCallbackListHead"
                                }
                                
                                if resolve_modules:
                                    target_addr = parsed["callback_address"]
                                    try:
                                        ln_success, ln_output, _ = execute_optimized_command(f"ln {target_addr}", "quick")
                                        if ln_success and '!' in ln_output:
                                            module_func = ln_output.split('!')[0].strip()
                                            if module_func:
                                                callback_entry["module"] = module_func
                                                callback_entry["resolved"] = True
                                                
                                                core_modules = ["nt", "ntoskrnl", "hal"]
                                                if module_func.lower() not in core_modules:
                                                    callback_entry["third_party"] = True
                                                    third_party_drivers.add(module_func)
                                                else:
                                                    callback_entry["third_party"] = False
                                    except Exception:
                                        callback_entry["resolved"] = False
                                
                                parsed_callbacks.append(callback_entry)
                                callback_count += 1
                            
                            registry_callbacks["parsed_callbacks"] = parsed_callbacks
                            registry_callbacks["count"] = callback_count
                            registry_callbacks["raw_output"] = output if include_addresses else "[Hidden]"
                            total_callbacks += callback_count
                            
                    except Exception as e:
                        logger.debug(f"CmCallbackListHead method failed: {e}")
                        
                        # Method 2: Try alternative registry notification command
                        try:
                            success, output, _ = execute_optimized_command("!regnotify", "bulk")
                            if success and output.strip():
                                registry_callbacks["alternative_output"] = output if include_addresses else "[Hidden]"
                                registry_callbacks["note"] += " - Used !regnotify command as fallback"
                                # Basic parsing for !regnotify output
                                if "callback" in output.lower():
                                    total_callbacks += 1  # At least one registry callback detected
                        except Exception as e2:
                            logger.debug(f"!regnotify fallback also failed: {e2}")
                            registry_callbacks["error"] = f"Both CmCallbackListHead and !regnotify failed: {str(e)}, {str(e2)}"
                    
                    callbacks["registry"] = registry_callbacks
                        
                except Exception as e:
                    callbacks["registry"] = {
                        "type": "Registry Callbacks",
                        "error": f"Exception during enumeration: {str(e)}"
                    }
            
            # 5. Enumerate Object Manager Callbacks (simplified approach)
            if callback_type in ["all", "object"]:
                try:
                    logger.debug("Enumerating object manager callbacks")
                    
                    # Get process object type callback list
                    success, output, metadata = execute_optimized_command("dx @$ProcObj = *(nt!_OBJECT_TYPE **)&nt!PsProcessType; @$ProcObj->CallbackList", "bulk")
                    
                    object_callbacks = {
                        "type": "Object Manager Callbacks",
                        "process_callbacks": {},
                        "thread_callbacks": {},
                        "note": "Object manager callbacks for handle operations"
                    }
                    
                    if success and output.strip():
                        object_callbacks["process_callbacks"] = {
                            "raw_output": output if include_addresses else "[Hidden]",
                            "note": "Process object type callback list"
                        }
                        
                        # Check if there are active callbacks
                        if "Flink" in output and "Blink" in output:
                            if "0x" in output and not output.count("0x0") == output.count("0x"):
                                total_callbacks += 1  # At least one object callback detected
                    
                    # Try thread object type as well
                    try:
                        success2, output2, _ = execute_optimized_command("dx @$ThreadObj = *(nt!_OBJECT_TYPE **)&nt!PsThreadType; @$ThreadObj->CallbackList", "bulk")
                        if success2:
                            object_callbacks["thread_callbacks"] = {
                                "raw_output": output2 if include_addresses else "[Hidden]",
                                "note": "Thread object type callback list"
                            }
                    except Exception:
                        pass
                    
                    callbacks["object_manager"] = object_callbacks
                        
                except Exception as e:
                    callbacks["object_manager"] = {
                        "type": "Object Manager Callbacks",
                        "error": f"Exception during enumeration: {str(e)}"
                    }
            
            # Calculate execution time and finalize summary
            execution_time = time.time() - start_time
            
            results["summary"] = {
                "total_callbacks": total_callbacks,
                "third_party_drivers": sorted(list(third_party_drivers)),
                "unique_drivers": len(third_party_drivers),
                "execution_time": round(execution_time, 3),
                "filter_applied": callback_type,
                "callbacks_by_type": {
                    k: v.get("count", 0) for k, v in callbacks.items() 
                    if isinstance(v, dict) and "count" in v
                }
            }
            
            # Add security analysis
            security_notes = []
            if len(third_party_drivers) > 0:
                security_notes.append(f"🔍 Detected {len(third_party_drivers)} third-party drivers with callbacks")
                security_notes.append("⚠️ Third-party callbacks may indicate EDR/AV presence")
                security_notes.extend([f"   • {driver}" for driver in sorted(third_party_drivers)])
            
            if total_callbacks > 15:
                security_notes.append(f"📊 High callback count ({total_callbacks}) - system may be heavily monitored")
            elif total_callbacks < 5:
                security_notes.append(f"📊 Low callback count ({total_callbacks}) - minimal monitoring detected")
            
            results["security_analysis"] = security_notes
            
            # Add recommendations
            recommendations = []
            if third_party_drivers:
                recommendations.append("🎯 Consider analyzing third-party drivers for EDR bypass opportunities")
                recommendations.append("🔬 Use '!drvobj <driver>' to analyze individual driver capabilities")
            
            recommendations.append("🚀 Use callback_type filters for focused analysis")
            recommendations.append("📋 Cross-reference with '!process 0 0' for process monitoring validation")
            
            results["recommendations"] = recommendations
            
            logger.info(f"Callback enumeration completed: {total_callbacks} callbacks, {len(third_party_drivers)} third-party drivers")
            return results
            
        except Exception as e:
            logger.error(f"Unified callback enumeration failed: {e}")
            return {
                "error": f"Unified callback enumeration failed: {str(e)}",
                "partial_results": results,
                "suggestion": "Check debugger connection and ensure kernel symbols are loaded"
            } 