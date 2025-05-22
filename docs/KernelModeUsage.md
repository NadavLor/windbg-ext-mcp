# WinDbg-MCP Kernel-Mode Debugging Guide

This document provides guidance for using WinDbg-MCP in kernel-mode debugging scenarios, including known limitations and workarounds.

## Kernel vs User Mode Debugging

WinDbg-MCP supports both user-mode and kernel-mode debugging. However, there are important differences between these modes that affect available commands and functionality:

- **Kernel-mode debugging**: Debugging the Windows kernel and device drivers
- **User-mode debugging**: Debugging applications and user-mode processes

## Key Limitations and Workarounds

### 1. Process & Command Line Enumeration

**Limitation**: User-mode command lines cannot be retrieved from kernel-mode debugging.

**Workaround**:
- Use `!process 0 0` to list kernel processes without command lines
- For detailed process information, use `!process <address> f`

**Example**:
```
// Instead of this (won't work in kernel-mode)
!process -cmdline

// Use this instead
!process 0 0
// Then get details about a specific process
!process <address> f
```

### 2. Heap & Memory Analysis

**Limitation**: User-mode heap commands fail in kernel-mode.

**Workaround**:
- Use kernel pool commands (`!poolused`, `!poolfind`) instead of heap commands
- For memory analysis, use `!address` and `!vprot` instead of user-mode specific commands

**Example**:
```
// Instead of this (won't work in kernel-mode)
!heap -stat

// Use these instead
!poolused
!poolfind <tag>
```

### 3. Module Information

**Limitation**: Symbol reloads require full image names and base addresses in kernel-mode.

**Workaround**:
- Use the enhanced `.reload` command handler which automatically includes module names and base addresses
- Use the `troubleshoot_symbols` tool for comprehensive symbol troubleshooting

**Example**:
```
// This will automatically be enhanced with proper module information
.reload

// For detailed symbol troubleshooting
// Use the troubleshoot_symbols tool
```

### 4. Thread & CPU Usage

**Limitation**: Limited process/thread context switching capabilities for non-System processes.

**Workaround**:
- Use `!process <address> f` to examine thread information without switching context
- Use the `get_all_thread_stacks` tool to get stack traces from multiple threads

**Example**:
```
// Instead of this (may not work for all processes)
~* k

// Use this custom tool
// get_all_thread_stacks tool with count parameter
```

### 5. Call Stack Inspection

**Limitation**: Multi-thread stack trace commands like `~* k` are not supported in MCP.

**Workaround**:
- Use the `get_all_thread_stacks` tool to collect stack traces from multiple threads
- Manually switch to each thread using `.thread <address>` and then use `k` command

**Example**:
```
// Use the get_all_thread_stacks tool which handles thread switching internally
```

### 6. Exception & Bugcheck Analysis

**Limitation**: Manual break-ins appear similar to real bugchecks in analysis.

**Workaround**:
- Use the `analyze_exception` tool which distinguishes between manual break-ins and real bugchecks
- For real bugcheck analysis, use crash dumps or use `.crash` to trigger a test bugcheck

**Example**:
```
// Instead of just running
!analyze -v

// Use the enhanced tool
// analyze_exception tool
```

### 7. Symbol Verification & Troubleshooting

**Limitation**: Complex symbol loading issues can be difficult to diagnose.

**Workaround**:
- Use the `troubleshoot_symbols` tool for comprehensive symbol troubleshooting
- For persistent issues, use `.sympath+ srv*c:\symbols*https://msdl.microsoft.com/download/symbols`

**Example**:
```
// Use the troubleshoot_symbols tool for guided diagnostics
```

### 8. Expressions, Pseudo-Registers, and Aliases

**Limitation**: Alias commands are not supported in MCP.

**Workaround**:
- Use direct expressions instead of aliases
- Use variables in LLM context to track important addresses

### 9. Automation, Dot-Commands, and Scripting

**Limitation**: Many dot-commands for automation are not supported in MCP.

**Workaround**:
- Use the `run_command_sequence` tool to run multiple commands in sequence
- Use LLM logic to implement conditional execution and looping

**Example**:
```
// Use the run_command_sequence tool with an array of commands
// It will execute them in sequence and return all results
```

## Specialized Tools for Kernel Debugging

WinDbg-MCP provides these specialized tools to help with kernel-mode debugging:

1. **get_all_thread_stacks**: Gets stack traces for multiple threads (replacement for `~* k`)
2. **troubleshoot_symbols**: Performs comprehensive symbol troubleshooting
3. **run_command_sequence**: Runs multiple commands in sequence (basic scripting)
4. **analyze_exception**: Enhanced exception/bugcheck analysis with context

## Best Practices

1. **Context Management**:
   - Always check if commands are appropriate for kernel-mode
   - Tools automatically save and restore context when switching processes/threads

2. **Symbol Loading**:
   - Use the `troubleshoot_symbols` tool if experiencing symbol issues
   - Ensure you have proper symbol paths configured

3. **System Impact**:
   - Avoid commands that could crash or destabilize the target system
   - Be cautious with commands that modify memory in kernel-mode

4. **Performance**:
   - Large commands like `!process 0 0` can be slow in kernel-mode
   - Use targeted commands when possible for better performance

## Further Resources

- [WinDbg from A to Z](https://docs.microsoft.com/en-us/windows-hardware/drivers/debugger/windbg-a-z)
- [Kernel-Mode Debugging in WinDbg](https://docs.microsoft.com/en-us/windows-hardware/drivers/debugger/kernel-mode-debugging-in-windbg)
- [Debugging Tools for Windows](https://docs.microsoft.com/en-us/windows-hardware/drivers/debugger/) 