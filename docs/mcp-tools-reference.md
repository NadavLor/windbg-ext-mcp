# MCP Tools Reference - Complete Documentation

This document provides comprehensive documentation for all available MCP (Model Context Protocol) tools in the WinDbg MCP Extension project.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Session Management Tools](#session-management-tools)
- [Command Execution Tools](#command-execution-tools) 
- [Analysis Tools](#analysis-tools)
- [Performance Tools](#performance-tools)
- [Support & Troubleshooting Tools](#support--troubleshooting-tools)
- [C++ Extension Handlers](#c-extension-handlers)
- [Quick Reference](#quick-reference)
- [Best Practices](#best-practices)

---

## Architecture Overview

The WinDbg MCP Extension uses a **hybrid architecture** with two layers of tools:

### **Python MCP Tools** (High-Level Interface)
- Accessed directly from Cursor IDE or other MCP clients
- Provide enhanced error handling, parameter validation, and user-friendly responses
- Support advanced features like async execution, performance optimization, and session recovery

### **C++ Extension Handlers** (Low-Level Interface)
- Direct integration with WinDbg debugging engine
- Faster execution for basic operations
- Called internally by Python tools or directly for performance-critical operations

---

## Session Management Tools

These tools manage debugging sessions, connections, and session recovery.

### **debug_session**

**Purpose:** Core session management and debugging status information.

**Parameters:**
- `action` (str): Action to perform
  - `"status"` - Get current session status (default)
  - `"connection"` - Test connection to WinDbg extension
  - `"health"` - Get comprehensive session health
  - `"version"` - Get WinDbg version information
  - `"capture_state"` - Capture current session state for recovery
  - `"performance"` - Get performance optimization status

**Examples:**
```python
# Check if debugging session is active
debug_session(action="status")

# Test connection to WinDbg extension
debug_session(action="connection")

# Get detailed health information
debug_session(action="health")

# Capture current state for recovery
debug_session(action="capture_state")
```

**Returns:**
- Session status with connection health
- Error suggestions and next steps
- Performance optimization information
- Recovery state information

---

### **connection_manager**

**Purpose:** Manage connection resilience and network debugging optimization.

**Parameters:**
- `action` (str): Action to perform
  - `"status"` - Get connection health status
  - `"health"` - Detailed health diagnostics
  - `"monitor"` - Start background connection monitoring
  - `"stop_monitor"` - Stop background monitoring
  - `"set_mode"` - Set network debugging mode
  - `"test"` - Test connection performance
  - `"resilience"` - Get resilience feature status
- `mode` (str): Network mode for `set_mode` action
  - `"stable"` - Standard timeouts (good networks)
  - `"unstable"` - Extended timeouts (unreliable networks)
  - `"ultra_stable"` - Maximum timeouts (very poor connections)
- `timeout_category` (str): Timeout category for testing
  - `"quick"`, `"normal"`, `"slow"`, `"bulk"`, `"analysis"`

**Examples:**
```python
# Check connection health
connection_manager(action="health")

# Optimize for unstable VM network debugging
connection_manager(action="set_mode", mode="unstable")

# Start background monitoring
connection_manager(action="monitor")

# Test connection performance
connection_manager(action="test", timeout_category="normal")
```

**Use Cases:**
- ✅ **VM Debugging:** Set to "unstable" mode for packet loss tolerance
- ✅ **Network Issues:** Get real-time health diagnostics
- ✅ **Performance:** Monitor connection quality over time

---

### **session_manager**

**Purpose:** Advanced session recovery and state persistence.

**Parameters:**
- `action` (str): Action to perform
  - `"status"` - Get session recovery status
  - `"capture"` - Capture current session state
  - `"recover"` - Recover from saved session state
  - `"health"` - Check session health
  - `"save"` - Save session to disk
  - `"list_strategies"` - List available recovery strategies
  - `"cache_stats"` - Get session cache statistics
- `strategy` (str): Recovery strategy for `recover` action
  - `"automatic"` - Smart recovery with context detection
  - `"manual"` - Manual recovery with user control
  - `"conservative"` - Safe recovery with minimal changes

**Examples:**
```python
# Check session recovery status
session_manager(action="status")

# Capture current session state
session_manager(action="capture")

# Recover using automatic strategy
session_manager(action="recover", strategy="automatic")

# Save current session to disk
session_manager(action="save")
```

**Advanced Features:**
- 🔄 **Automatic Recovery:** Smart detection of interrupted sessions
- 💾 **Persistent Storage:** Session state saved across crashes
- 🎯 **Context Preservation:** Maintains debugging context across restarts

---

## Command Execution Tools

These tools execute WinDbg commands with enhanced safety, validation, and performance optimization.

### **run_command**

**Purpose:** Execute single WinDbg commands with comprehensive error handling.

**Parameters:**
- `command` (str): WinDbg command to execute
- `validate` (bool): Enable command validation (default: True)
- `resilient` (bool): Use resilient execution with retries (default: True)  
- `optimize` (bool): Enable performance optimization (default: True)

**Examples:**
```python
# Execute with all optimizations (recommended)
run_command(command="!process 0 0")

# Execute without validation (for advanced users)
run_command(command="g", validate=False)

# Direct execution without optimization
run_command(command="version", optimize=False, resilient=False)

# Safe execution with validation
run_command(command="bp nt!NtCreateFile")
```

**Execution Control Commands (NOW ENABLED):**
```python
# ✅ These commands are now safe for LLM automation:
run_command(command="g")          # Continue execution
run_command(command="p")          # Step over
run_command(command="t")          # Step into  
run_command(command="gu")         # Go up (return from function)
run_command(command="wt")         # Watch and trace

# ✅ Breakpoint commands are enabled:
run_command(command="bp nt!NtCreateFile")  # Set breakpoint
run_command(command="bc 1")                # Clear breakpoint 1
run_command(command="bd 1")                # Disable breakpoint 1
run_command(command="be 1")                # Enable breakpoint 1
```

**Features:**
- 🛡️ **Safety Validation:** Prevents dangerous commands in automation
- 🚀 **Performance Optimization:** Automatic caching and compression
- 🔄 **Resilient Execution:** Automatic retries with exponential backoff
- 📊 **Detailed Responses:** Execution metrics and suggestions

---

### **run_sequence**

**Purpose:** Execute multiple commands in sequence with error handling.

**Parameters:**
- `commands` (List[str]): List of WinDbg commands to execute
- `stop_on_error` (bool): Stop execution if a command fails (default: False)

**Examples:**
```python
# Execute diagnostic sequence
run_sequence(commands=[
    "version",
    "!analyze -v", 
    "k",
    "lm"
])

# Critical sequence - stop on first error
run_sequence(commands=[
    ".reload",
    "bp nt!NtCreateFile",
    "g"
], stop_on_error=True)

# Analysis workflow
run_sequence(commands=[
    "!process 0 0",
    "!thread",
    "!handle 0 f"
])
```

**Advanced Features:**
- 📋 **Execution Summary:** Detailed results for each command
- ⏱️ **Performance Metrics:** Individual and total execution times
- 🔄 **Context Recovery:** Automatic context saving for rollback
- 💡 **Smart Suggestions:** Recommendations based on results

---

### **breakpoint_and_continue**

**Purpose:** Combined breakpoint setting and execution control optimized for LLM automation.

**Parameters:**
- `breakpoint` (str): Breakpoint specification (address, symbol, function)
- `continue_execution` (bool): Continue execution after setting breakpoint (default: True)
- `clear_existing` (bool): Clear existing breakpoints first (default: False)

**Examples:**
```python
# Set breakpoint and continue (most common)
breakpoint_and_continue(breakpoint="nt!NtCreateFile")

# Set breakpoint without continuing
breakpoint_and_continue(
    breakpoint="kernel32!CreateFileW", 
    continue_execution=False
)

# Clear all breakpoints and set new one
breakpoint_and_continue(
    breakpoint="ntdll!NtOpenFile",
    clear_existing=True
)

# Set breakpoint at specific address
breakpoint_and_continue(breakpoint="0x12345678")
```

**Automation Benefits:**
- 🎯 **One-Step Operation:** Combines multiple debugging steps
- 📊 **Step-by-Step Reporting:** Detailed execution of each step
- 🔄 **Context Management:** Automatic context saving and restoration
- 💡 **Guided Workflow:** Built-in suggestions for next steps

---

## Analysis Tools

These tools analyze debugging targets, processes, threads, memory, and kernel objects.

### **analyze_process**

**Purpose:** Comprehensive process analysis and context switching.

**Parameters:**
- `action` (str): Analysis action to perform
  - `"list"` - List all processes
  - `"switch"` - Switch to specific process context
  - `"info"` - Get detailed process information
  - `"peb"` - Analyze Process Environment Block (user-mode only)
  - `"restore"` - Restore previous process context
- `address` (str): Process address (required for switch, info, peb)
- `save_context` (bool): Save current context before switching (default: True)

**Examples:**
```python
# List all processes
analyze_process(action="list")

# Switch to specific process (saves current context)
analyze_process(action="switch", address="ffff8000`12345678")

# Get detailed process information  
analyze_process(action="info", address="ffff8000`12345678")

# Analyze PEB (user-mode debugging only)
analyze_process(action="peb", address="ffff8000`12345678")

# Restore previous context
analyze_process(action="restore")
```

**Smart Features:**
- 🎯 **Context Awareness:** Detects kernel vs user mode automatically
- 🔄 **Safe Switching:** Automatic context preservation
- 💡 **Guided Workflow:** Provides next steps after each operation
- ⚠️ **Mode Detection:** Warns when operations aren't available

---

### **analyze_thread**

**Purpose:** Thread analysis and stack trace examination.

**Parameters:**
- `action` (str): Analysis action to perform
  - `"list"` - List all threads
  - `"switch"` - Switch to specific thread context
  - `"info"` - Get detailed thread information
  - `"stack"` - Get stack trace for thread
  - `"all_stacks"` - Get stack traces for multiple threads
  - `"teb"` - Analyze Thread Environment Block
- `address` (str): Thread address (required for switch, info, stack, teb)
- `count` (int): Number of stack frames or threads to show (default: 20)

**Examples:**
```python
# List all threads
analyze_thread(action="list")

# Get stack trace for specific thread
analyze_thread(action="stack", address="ffff8000`87654321")

# Get stack traces for multiple threads (limited)
analyze_thread(action="all_stacks", count=5)

# Analyze Thread Environment Block
analyze_thread(action="teb", address="ffff8000`87654321")
```

**Performance Features:**
- ⚡ **Optimized Stack Traces:** Shorter traces for multiple threads
- 🎯 **Context Management:** Safe thread switching with restoration
- 📊 **Batch Processing:** Multiple thread analysis in one operation

---

### **analyze_memory**

**Purpose:** Memory analysis, structure display, and memory searches.

**Parameters:**
- `action` (str): Memory analysis action
  - `"display"` - Display memory contents
  - `"type"` - Display data structure
  - `"search"` - Search memory for patterns
  - `"pte"` - Analyze Page Table Entry
  - `"regions"` - Show memory regions
- `address` (str): Memory address (required for most actions)
- `type_name` (str): Structure type name (required for "type" action)
- `length` (int): Number of bytes/elements to display (default: 32)

**Examples:**
```python
# Display memory as DWORDs
analyze_memory(action="display", address="ffff8000`12345678")

# Display structure
analyze_memory(action="type", type_name="nt!_EPROCESS", address="ffff8000`12345678")

# Search for ASCII string
analyze_memory(action="search", address="malware.exe")

# Analyze page table entry
analyze_memory(action="pte", address="ffff8000`12345678")

# Show memory regions summary
analyze_memory(action="regions")
```

**Advanced Features:**
- 🔍 **Smart Searching:** Pattern detection in memory
- 📊 **Structure Visualization:** Formatted structure display
- 🗺️ **Memory Mapping:** Virtual memory layout analysis

---

### **analyze_kernel**

**Purpose:** Kernel object and system structure analysis.

**Parameters:**
- `action` (str): Kernel analysis action
  - `"object"` - Analyze kernel object
  - `"idt"` - Display Interrupt Descriptor Table
  - `"handles"` - Display system handles
  - `"interrupts"` - Analyze interrupt structure
  - `"modules"` - List loaded modules with details
- `address` (str): Object address (required for "object", "interrupts")

**Examples:**
```python
# Analyze kernel object
analyze_kernel(action="object", address="ffff8000`12345678")

# Display IDT
analyze_kernel(action="idt")

# Show all system handles
analyze_kernel(action="handles")

# Show handles for specific object
analyze_kernel(action="handles", address="ffff8000`12345678")

# List loaded modules with version info
analyze_kernel(action="modules")
```

**System Analysis Features:**
- 🔧 **Kernel Internals:** Deep system structure analysis
- 🛡️ **Security Research:** Object and handle enumeration
- 📋 **Module Analysis:** Driver and DLL information

---

### **mcp_list_callbacks** ⭐ **(NEW UNIFIED TOOL)**

**Purpose:** Comprehensive callback enumeration across all callback types with EDR detection.

**Parameters:**
- `callback_type` (str): Type of callbacks to enumerate (default: "all")
  - `"all"` - All callback types (comprehensive scan)
  - `"process"` - Process creation callbacks
  - `"thread"` - Thread creation callbacks  
  - `"image"` - Image load callbacks
  - `"registry"` - Registry callbacks
  - `"object"` - Object manager callbacks
- `include_addresses` (bool): Include raw addresses in output (default: True)
- `resolve_modules` (bool): Resolve addresses to module names (default: True)
- `timeout_ms` (int): Timeout for enumeration in milliseconds (default: 60000)

**Examples:**
```python
# Comprehensive callback enumeration (recommended)
mcp_list_callbacks()

# Fast process callback scan
mcp_list_callbacks(callback_type="process")

# Detailed analysis with module resolution
mcp_list_callbacks(
    callback_type="all",
    include_addresses=True,
    resolve_modules=True
)

# Quick registry callback check
mcp_list_callbacks(callback_type="registry", timeout_ms=30000)
```

**Security Research Features:**
- 🎯 **EDR Detection:** Automatically identifies third-party security drivers
- 📊 **Comprehensive Coverage:** All core callback types in one command
- ⚡ **Performance Optimized:** Filtering reduces execution time significantly
- 🔍 **Address Resolution:** Automatic module name resolution
- 📋 **Consolidated Reporting:** Single report with all callback information

**Sample Output Analysis:**
```
🔍 Callback Analysis Results:
• Process Creation: 10 callbacks (⚠️ Heavy monitoring detected)
• Thread Creation: 2 callbacks  
• Image Load: 2 callbacks
• Registry: 0 callbacks
• Object Manager: 0 callbacks

🎯 Performance: 2.17s (full scan) vs 0.124s (filtered)
💡 Tip: Use filtering for faster repeated scans
```

---

## Performance Tools

These tools manage performance optimization, caching, and asynchronous command execution.

### **performance_manager**

**Purpose:** Performance optimization and monitoring for debugging operations.

**Parameters:**
- `action` (str): Performance management action
  - `"report"` - Get comprehensive performance report
  - `"set_level"` - Set optimization level
  - `"clear_cache"` - Clear performance caches
  - `"stream"` - Stream large command output
  - `"benchmark"` - Run performance benchmark
- `level` (str): Optimization level for "set_level"
  - `"none"` - No optimization
  - `"basic"` - Basic caching and compression
  - `"aggressive"` - Enhanced optimization for VM debugging
  - `"maximum"` - Maximum optimization (may affect accuracy)
- `command` (str): Command for streaming or benchmarking

**Examples:**
```python
# Get performance report
performance_manager(action="report")

# Set aggressive optimization for VM debugging
performance_manager(action="set_level", level="aggressive")

# Clear caches if needed
performance_manager(action="clear_cache")

# Stream large command output
performance_manager(action="stream", command="!process 0 0")

# Benchmark specific command
performance_manager(action="benchmark", command="lm")
```

**Optimization Features:**
- 🚀 **Smart Caching:** TTL-based result caching
- 📦 **Compression:** Data compression for large outputs
- ⏱️ **Adaptive Timeouts:** Dynamic timeout adjustment
- 📊 **Performance Metrics:** Detailed execution analytics
- 🎯 **VM Optimization:** Special modes for virtualized debugging

---

### **async_manager**

**Purpose:** Asynchronous command execution for improved performance and concurrency.

**Parameters:**
- `action` (str): Async operation action
  - `"submit"` - Submit commands for async execution
  - `"status"` - Get task or system status
  - `"result"` - Retrieve task results
  - `"parallel"` - Execute commands in parallel
  - `"stats"` - Get async system statistics
  - `"cancel"` - Cancel specific task
  - `"diagnostic"` - Run async diagnostic sequence
- `commands` (List[str]): Commands for submission or parallel execution
- `task_id` (str): Task ID for status/result/cancel operations
- `priority` (str): Task priority (default: "normal")
  - `"low"`, `"normal"`, `"high"`, `"critical"`

**Examples:**
```python
# Execute commands in parallel (fastest for independent operations)
async_manager(action="parallel", commands=[
    "version",
    "lm", 
    "k",
    "!process -1 0"
])

# Submit commands with priority
async_manager(
    action="submit", 
    commands=["!analyze -v"],
    priority="high"
)

# Get system statistics
async_manager(action="stats")

# Run comprehensive diagnostic
async_manager(action="diagnostic")
```

**Concurrency Features:**
- ⚡ **Parallel Execution:** Multiple independent commands simultaneously
- 📋 **Task Management:** Full task lifecycle management
- 🎯 **Priority System:** Critical tasks get precedence
- 📊 **Real-time Status:** Live task monitoring and statistics
- 🔧 **Background Processing:** Non-blocking command execution

---

## Support & Troubleshooting Tools

These tools provide help, troubleshooting, and diagnostic capabilities.

### **troubleshoot**

**Purpose:** Troubleshoot common debugging issues with guided solutions.

**Parameters:**
- `action` (str): Troubleshooting area
  - `"symbols"` - Symbol loading and path issues
  - `"exception"` - Current exception analysis
  - `"analyze"` - General system analysis
  - `"connection"` - Connection and communication issues

**Examples:**
```python
# Troubleshoot symbol issues
troubleshoot(action="symbols")

# Analyze current exception
troubleshoot(action="exception")

# Test connection health
troubleshoot(action="connection")

# General system analysis
troubleshoot(action="analyze")
```

**Guided Troubleshooting:**
- 🔍 **Automatic Diagnosis:** Detects common issues automatically
- 💡 **Step-by-Step Guidance:** Detailed resolution steps
- 🛠️ **Automated Fixes:** Attempts automatic resolution where safe
- 📊 **Comprehensive Analysis:** Multi-point system health checks

---

### **get_help**

**Purpose:** Comprehensive help system with examples and best practices.

**Parameters:**
- `tool_name` (str): Name of tool to get help for (empty for tool list)
- `action` (str): Specific action to get help for (empty for all actions)

**Examples:**
```python
# List all available tools
get_help()

# Get help for specific tool
get_help(tool_name="analyze_process")

# Get help for specific action
get_help(tool_name="run_command", action="execute")

# Get help for breakpoint tool
get_help(tool_name="breakpoint_and_continue")
```

**Help Features:**
- 📚 **Comprehensive Documentation:** Detailed parameter descriptions
- 💡 **Usage Examples:** Real-world usage patterns
- 🎯 **Context-Aware Tips:** Mode-specific guidance
- 🚀 **Automation Features:** LLM optimization notes

---

### **diagnose_hybrid_connection**

**Purpose:** Comprehensive connection diagnostics for the hybrid architecture.

**Parameters:** None (dummy parameter required by framework)

**Example:**
```python
# Run comprehensive connection diagnostics
diagnose_hybrid_connection()
```

**Diagnostic Coverage:**
- 📡 **MCP Server Status:** Python server health
- 🔌 **Extension Connection:** Named pipe communication
- 🎯 **Target Connection:** WinDbg to debugging target
- 🌐 **Network Debugging:** VM-specific diagnostics

---

### **test_windbg_communication**

**Purpose:** Test communication with WinDbg extension with detailed results.

**Parameters:** None (dummy parameter required by framework)

**Example:**
```python
# Test WinDbg communication
test_windbg_communication()
```

**Test Coverage:**
- ✅ **Extension Connection:** Named pipe availability
- ✅ **Target Connection:** Debugging target responsiveness  
- ✅ **Command Execution:** Basic command functionality
- 📊 **Performance Testing:** Response time measurements

---

### **network_debugging_troubleshoot**

**Purpose:** Specialized troubleshooting for VM-based network debugging scenarios.

**Parameters:** None (dummy parameter required by framework)

**Example:**
```python
# Get network debugging troubleshooting guide
network_debugging_troubleshoot()
```

**Network-Specific Guidance:**
- 🌐 **VM Configuration:** Network adapter settings
- 🔄 **Connection Recovery:** Automatic retry strategies
- ⚠️ **Packet Loss Handling:** Network instability mitigation
- 🛠️ **Advanced Troubleshooting:** Complex connectivity issues

---

## C++ Extension Handlers

These are low-level handlers called internally by Python tools or available for direct use.

### **Basic Handlers**
- `check_connection` - Basic connection test
- `version` - Get WinDbg version
- `get_metadata` - Extension metadata  
- `lm` - List modules
- `dt` - Display type
- `dd` - Display memory

### **Enhanced Handlers**
- `execute_command` - Basic command execution
- `execute_command_enhanced` - Enhanced execution with metadata
- `execute_command_streaming` - Streaming for large outputs
- `for_each_module` - Module iteration
- `mcp_list_callbacks` - Unified callback enumeration (matches Python tool)
- `session_health` - Session health check
- `session_status` - Session status
- `connection_status` - Connection status
- `capture_session_state` - Session state capture

### **Diagnostic Handlers**
- `health_check` - System health check
- `performance_metrics` - Performance data collection

**Note:** Most users should use the Python MCP tools as they provide better error handling, validation, and user experience. The C++ handlers are primarily for internal use and performance-critical operations.

---

## Quick Reference

### **Most Common Workflows**

**🎯 Basic Debugging Session:**
```python
# 1. Check session status
debug_session(action="status")

# 2. List processes
analyze_process(action="list")

# 3. Switch to target process
analyze_process(action="switch", address="<process_addr>")

# 4. Set breakpoint and continue
breakpoint_and_continue(breakpoint="nt!NtCreateFile")
```

**🔍 Security Research:**
```python
# 1. Enumerate all callbacks (EDR detection)
mcp_list_callbacks()

# 2. Check for suspicious modules
analyze_kernel(action="modules")

# 3. Analyze handles for IOCs
analyze_kernel(action="handles")
```

**⚡ Performance Optimization:**
```python
# 1. Set aggressive optimization
performance_manager(action="set_level", level="aggressive")

# 2. Use parallel execution for independent commands
async_manager(action="parallel", commands=[
    "version", "lm", "k", "!thread"
])
```

**🌐 Network Debugging (VM):**
```python
# 1. Optimize for unstable connections
connection_manager(action="set_mode", mode="unstable")

# 2. Start monitoring
connection_manager(action="monitor")

# 3. Use resilient execution
run_command(command="!process 0 0", resilient=True)
```

### **Command Categories by Use Case**

| **Use Case** | **Primary Tools** | **Features** |
|---|---|---|
| **Basic Debugging** | `run_command`, `breakpoint_and_continue`, `analyze_process` | Execution control, context switching |
| **Malware Analysis** | `mcp_list_callbacks`, `analyze_kernel`, `analyze_memory` | EDR detection, callback enumeration |
| **Performance** | `async_manager`, `performance_manager`, `run_sequence` | Parallel execution, optimization |
| **Network/VM Debugging** | `connection_manager`, `session_manager`, `troubleshoot` | Resilience, monitoring, recovery |
| **Troubleshooting** | `diagnose_hybrid_connection`, `test_windbg_communication`, `get_help` | Diagnostics, guided solutions |

---

## Best Practices

### **🚀 For LLM Automation**

1. **Use Combined Operations:**
   ```python
   # ✅ Better: One operation
   breakpoint_and_continue(breakpoint="nt!NtCreateFile")
   
   # ❌ Avoid: Multiple separate operations
   run_command(command="bp nt!NtCreateFile")
   run_command(command="g")
   ```

2. **Enable All Safety Features:**
   ```python
   # ✅ Recommended: All safety features enabled (default)
   run_command(command="!analyze -v", validate=True, resilient=True)
   ```

3. **Use Parallel Execution:**
   ```python
   # ✅ Faster: Parallel execution for independent commands
   async_manager(action="parallel", commands=["version", "lm", "k"])
   ```

### **🌐 For Network/VM Debugging**

1. **Optimize Connection Settings:**
   ```python
   # Set unstable mode for VM debugging
   connection_manager(action="set_mode", mode="unstable")
   ```

2. **Use Session Recovery:**
   ```python
   # Capture state before risky operations
   session_manager(action="capture")
   ```

3. **Monitor Performance:**
   ```python
   # Set aggressive optimization
   performance_manager(action="set_level", level="aggressive")
   ```

### **🔍 For Security Research**

1. **Use Unified Callback Enumeration:**
   ```python
   # ✅ Comprehensive: One command for all callbacks
   mcp_list_callbacks()
   
   # ✅ Targeted: Focus on specific type
   mcp_list_callbacks(callback_type="process")
   ```

2. **Leverage EDR Detection:**
   ```python
   # The tool automatically highlights third-party drivers
   mcp_list_callbacks(resolve_modules=True)
   ```

### **⚡ For Performance**

1. **Use Appropriate Tools:**
   - Single commands: `run_command`
   - Multiple commands: `run_sequence` or `async_manager`
   - Large outputs: `performance_manager` with streaming

2. **Monitor and Optimize:**
   ```python
   # Check performance regularly
   performance_manager(action="report")
   
   # Clear caches if needed
   performance_manager(action="clear_cache")
   ```

### **🛠️ For Troubleshooting**

1. **Start with Diagnostics:**
   ```python
   # Always start with comprehensive diagnostics
   diagnose_hybrid_connection()
   ```

2. **Use Targeted Troubleshooting:**
   ```python
   # For specific issues
   troubleshoot(action="symbols")      # Symbol problems
   troubleshoot(action="connection")   # Connection issues
   ```

3. **Get Help When Needed:**
   ```python
   # Comprehensive help system
   get_help()                                    # List all tools
   get_help(tool_name="analyze_process")        # Tool-specific help
   ```

---

## Summary

The WinDbg MCP Extension provides **25+ tools** organized into logical categories:

- **5 Session Management Tools** - Connection, health, recovery
- **3 Command Execution Tools** - Safe command execution with automation features
- **5 Analysis Tools** - Process, thread, memory, kernel, and callback analysis
- **2 Performance Tools** - Optimization and async execution
- **8 Support Tools** - Help, troubleshooting, and diagnostics
- **12 C++ Extension Handlers** - Low-level performance operations

**Key Features:**
- ✅ **LLM-Optimized:** Safe automation with execution control
- ✅ **Network Debugging:** Resilient VM debugging support  
- ✅ **Security Research:** EDR detection and callback enumeration
- ✅ **Performance:** Async execution and optimization
- ✅ **Error Handling:** Enhanced error messages with guidance
- ✅ **Session Recovery:** Robust session management and recovery

**Architecture:** Hybrid Python/C++ design provides both ease of use and performance, with comprehensive error handling and automation-friendly interfaces optimized for LLM interactions. 