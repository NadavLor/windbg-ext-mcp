# Getting Started with WinDbg MCP Extension

This guide will walk you through setting up the WinDbg MCP Extension for kernel debugging and malware analysis.

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Environment Setup](#environment-setup)
3. [Installing the Extension](#installing-the-extension)
4. [Configuring Kernel Debugging](#configuring-kernel-debugging)
5. [Starting Your First Session](#starting-your-first-session)
6. [Basic Commands and Workflows](#basic-commands-and-workflows)
7. [Troubleshooting Common Issues](#troubleshooting-common-issues)

## System Requirements

### Host Machine (Debugger)
- Windows 10/11 Professional or Enterprise
- WinDbg Preview or WinDbg (version 10.0+)
- Python 3.8 or higher
- At least 8GB RAM (16GB recommended)
- Network adapter for kernel debugging

### Target VM (Debuggee)
- Windows 10/11 (any edition)
- Configured for network kernel debugging
- Virtual machine software (VMware, Hyper-V, or VirtualBox)

### Development Tools
- Visual Studio 2019+ (for building the extension)
- Git for Windows
- Poetry (Python dependency manager)

## Environment Setup

### 1. Install WinDbg

Download and install WinDbg from the Microsoft Store or the Windows SDK:

```powershell
# Using winget (recommended)
winget install Microsoft.WinDbg

# Or download from:
# https://docs.microsoft.com/en-us/windows-hardware/drivers/debugger/
```

### 2. Configure Python Environment

```bash
# Install Python 3.8+
# Download from https://www.python.org/downloads/

# Verify installation
python --version

# Install Poetry
pip install poetry

# Clone the repository
git clone https://github.com/yourusername/windbg-ext-mcp.git
cd windbg-ext-mcp

# Install dependencies
poetry install
```

### 3. Build the WinDbg Extension

```bash
# Navigate to extension directory
cd extension

# Build using Visual Studio (Release mode)
msbuild windbgmcpExt.sln /p:Configuration=Release /p:Platform=x64

# The built extension will be at:
# extension\x64\Release\windbgmcpExt.dll
```

## Configuring Kernel Debugging

### 1. Configure the Target VM

On your target Windows VM, run these commands as Administrator:

```cmd
# Enable kernel debugging
bcdedit /debug on

# Configure network debugging (adjust IP and port)
bcdedit /dbgsettings net hostip:192.168.1.100 port:50000 key:1.2.3.4

# Disable Windows Defender (for malware analysis)
Set-MpPreference -DisableRealtimeMonitoring $true

# Restart the VM
shutdown /r /t 0
```

### 2. Configure VM Network

Ensure your VM network adapter is set to:
- **VMware**: Bridged or NAT mode
- **Hyper-V**: External or Internal virtual switch
- **VirtualBox**: Bridged Adapter

### 3. Start WinDbg on Host

```cmd
# Start WinDbg with network kernel debugging
windbg -k net:port=50000,key=1.2.3.4

# Wait for target connection...
```

## Starting Your First Session

### 1. Load the Extension

Once connected to the target, load the MCP extension in WinDbg:

```
.load C:\path\to\windbg-ext-mcp\extension\x64\Release\windbgmcpExt.dll

!mcpstatus
```

### 2. Start the MCP Server

In a new terminal on your host:

```bash
cd windbg-ext-mcp
poetry run python -m mcp_server.server

# You should see:
# Starting WinDbg MCP Server (Modular Architecture Edition)
# ✓ Connected to WinDbg extension
```

### 3. Configure Cursor IDE

Run the configuration script:

```bash
python install_client_config.py
```

This adds the MCP server to your Cursor configuration.

### 4. Connect from Cursor

1. Open Cursor IDE
2. Open the MCP panel (View → MCP Servers)
3. Select "WinDbg MCP Server"
4. Start chatting with the kernel!

## Basic Commands and Workflows

### Security Research Workflows

#### 1. Process Analysis

```
"Show me all processes running as SYSTEM"
"Which process has the most kernel handles?"
"Find processes with unsigned drivers loaded"
```

#### 2. Driver Investigation

```
"List all non-Microsoft kernel drivers"
"Show me the driver object for XYZ.sys"
"What callbacks has this driver registered?"
```

#### 3. Memory Analysis

```
"Display the EPROCESS structure for process 1234"
"Show kernel pool allocations with tag 'Hack'"
"Find all executable memory regions in kernel space"
```

### Using MCP Tools Directly

The extension provides specialized tools you can call directly:

```python
# Analyze a specific process
analyze_process(action="info", address="0xffff8001234560")

# Get system performance metrics
performance_manager(action="report")

# Run commands with resilience
run_command(command="!process 0 0", resilient=True)
```

### Advanced Debugging Session

```python
# Capture session state for recovery
debug_session(action="capture_state")

# Enable aggressive performance optimization
performance_manager(action="set_level", level="aggressive")

# Run parallel analysis
async_manager(action="parallel", commands=[
    "!process 0 0",
    "!drivers",
    "lm"
])
```

## Troubleshooting Common Issues

### Connection Issues

If WinDbg can't connect to the target:

1. **Check network connectivity**
   ```
   ping <target-vm-ip>
   ```

2. **Verify bcdedit settings on target**
   ```
   bcdedit /dbgsettings
   ```

3. **Check Windows Firewall**
   - Add exception for port 50000
   - Or temporarily disable for testing

### Extension Loading Failures

If the extension won't load:

1. **Check architecture match**
   - Use x64 extension for x64 WinDbg
   - Use x86 extension for x86 WinDbg

2. **Verify dependencies**
   ```
   dumpbin /dependents windbgmcpExt.dll
   ```

3. **Check WinDbg version**
   ```
   version
   ```

### MCP Server Issues

If the Python server won't start:

1. **Check named pipe availability**
   ```python
   # Run diagnostic tool
   diagnose_hybrid_connection()
   ```

2. **Verify Python environment**
   ```bash
   poetry env info
   poetry install
   ```

3. **Check for port conflicts**
   - MCP uses stdio, not network ports
   - Ensure no other MCP servers running

### Performance Issues

For slow or unresponsive debugging:

1. **Enable network optimization**
   ```python
   connection_manager(action="set_mode", mode="unstable")
   ```

2. **Clear caches if needed**
   ```python
   performance_manager(action="clear_cache")
   ```

3. **Check VM resources**
   - Ensure VM has adequate RAM
   - Check CPU usage on both host and target

## Next Steps

- Read the [Security Researcher's Guide](security-guide.md) for advanced malware analysis techniques
- Explore the [Tool Reference](tools-reference.md) for all available commands
- Check [Architecture Deep Dive](architecture.md) to understand the internals
- Join our community Discord for support and discussions

---

Remember: This tool is powerful but requires responsible use. Always ensure you have proper authorization before debugging any system. 