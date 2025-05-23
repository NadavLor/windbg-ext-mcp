# WinDbg-ext-MCP

**Vibe debugging your Windows kernel!**

WinDbg-ext-MCP connects your LLM client (like Cursor, Claude, or VS Code) with WinDbg, enabling AI kernel debugging through natural language prompts. Designed for network-based kernel debugging scenarios with Windows VMs.

---

## 🎯 Overview

This project enables you to debug Windows kernels using WinDbg while leveraging the power of LLMs (like Claude, GPT, etc.) through natural language interactions. When you hit a breakpoint in WinDbg while debugging a Windows VM over the network, you can write prompts in Cursor (or any MCP-compatible client) to get detailed kernel information and analysis.

---

## 🏗️ Architecture

The project uses a hybrid architecture optimized for network kernel debugging:

```
┌─────────────┐    stdio     ┌──────────────────┐    named pipe   ┌─────────────┐    network    ┌─────────────┐
│   Cursor    │◄────────────►│  Python MCP      │◄───────────────►│   WinDbg    │◄─────────────►│ Target VM   │
│   (Client)  │              │    Server        │                 │ Extension   │               │  (Kernel)   │
└─────────────┘              └──────────────────┘                 └─────────────┘               └─────────────┘
```

### Components
1. **MCP Client** (Cursor/IDE): Natural language interface
2. **Python MCP Server** (`mcp_server/`): Core logic, optimization, and tool orchestration
3. **WinDbg Extension** (`extension/`): C++ DLL for WinDbg integration
4. **WinDbg**: Debugger connected to target VM
5. **Target VM**: Windows kernel debugging target

---

## ✨ Features

### 🔧 Core Debugging Tools
- **Session Management**: Connection health monitoring, session recovery
- **Command Execution**: Validation, resilience, and performance optimization
- **Process Analysis**: List, switch, and analyze kernel processes
- **Thread Analysis**: Thread enumeration, stack traces, and context switching
- **Memory Analysis**: Memory inspection, structure analysis, and search capabilities
- **Kernel Analysis**: Kernel objects, IDT, handles, and system structures

### 🚀 Performance & Reliability
- **Network Optimization**: Designed for VM based kernel debugging over network
- **Connection Resilience**: Automatic retry logic with exponential backoff
- **Async Operations**: Parallel command execution for better performance
- **Result Caching**: Caching with TTL for faster repeated operations
- **Data Compression**: Automatic compression for large outputs
- **Session Recovery**: State preservation and recovery for interrupted sessions

---

## 🚀 Quick Start

### Prerequisites
- Windows 10/11 (host machine)
- [WinDbg (Windows Debugger)](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/) (Windows SDK)
- Python 3.10+ with [Poetry](https://python-poetry.org/)
- Target Windows VM configured for kernel debugging
- MCP-compatible LLM client (Cursor, Claude Desktop, VS Code + Cline/Roo)
- (Optional) Visual Studio with C++ build tools

### Installation

1. **Get the WinDbg Extension DLL:**

   You have two options:

   - **Option 1: Download Pre-built DLL**
     - Go to the [Releases page](https://github.com/NadavLor/windbg-ext-mcp/releases) and download the latest `windbgmcpExt.dll` for your platform.
     - Place the DLL in a known directory (you'll load it from this path in WinDbg).

   - **Option 2: Clone and Build from Source**
     ```sh
     git clone https://github.com/NadavLor/windbg-ext-mcp.git
     cd windbg-ext-mcp/extension
     msbuild /p:Configuration=Release /p:Platform=x64
     ```

2. **Install and start the MCP server:**
   ```sh
   poetry install
   poetry run python mcp_server/server.py
   ```

3. **Load the extension in WinDbg:**
   ```sh
   .load C:\path\to\windbg-ext-mcp\extension\x64\Release\windbgmcpExt.dll
   ```

4. **Configure your LLM client:**
   ```sh
   python install_client_config.py
   ```

### For first time debuggers

1. **Configure target VM for kernel debugging**
   ```cmd
   # On target VM (as Administrator)
   bcdedit /debug on
   bcdedit /dbgsettings net hostip:YOUR_HOST_IP port:50000 key:YOUR_KEY
   shutdown /r /t 0
   ```

2. **Connect WinDbg to target VM**
   ```cmd
   # On host machine
   windbg -k net:port=50000,key=YOUR_KEY
   ```

3. **Load the WinDbg extension**
   ```
   # In WinDbg command window
   .load C:\path\to\windbgmcpExt.dll
   ```

---

## 📖 Usage Examples

### Basic Debugging Session

1. **Start a debugging session**
   ```
   # In Cursor chat
   debug_session(action="status")
   ```

2. **List all processes in the kernel**
   ```
   # In Cursor chat
   analyze_process(action="list")
   ```

3. **Analyze a specific process**
   ```
   # Copy process address from the list above
   analyze_process(action="info", address="0xffff8e0e481d7080")
   ```

4. **Get memory information**
   ```
   analyze_memory(action="read", address="0x1000", size="0x100")
   ```

5. **Parallel command execution**
   ```
   async_manager(action="parallel", commands=["version", "lm", "!process -1 0"])
   ```

6. **Performance optimization**
   ```
   performance_manager(action="set_level", level="aggressive")
   ```

7. **Session recovery**
   ```
   session_manager(action="capture")  # Save current state
   session_manager(action="recover", strategy="automatic")  # Recover if needed
   ```

### Natural Language Debugging

You can also use natural language prompts in Cursor:

- *"Show me all running processes in the kernel"*
- *"What's the current thread's stack trace?"*
- *"Analyze the memory at address 0x1000"*
- *"Help me understand this crash dump"*

---

## ⚙️ Configuration

### Environment Variables
- `DEBUG=true`: Enable debug logging
- `VERBOSE=true`: Enable verbose logging
- `OPTIMIZATION_LEVEL=aggressive`: Set performance optimization level

### Network Debugging Modes
- `stable`: Standard timeouts (reliable networks)
- `unstable`: Extended timeouts (unreliable networks)  
- `ultra_stable`: Maximum timeouts (poor connections)

### Timeout Categories
- `quick`: 5s (version, registers)
- `normal`: 15s (most commands)
- `slow`: 30s (stack traces, thread info)
- `bulk`: 60s (process lists, module lists)
- `analysis`: 120s (crash analysis, complex operations)

## 🛠️ Available Tools

### Session Management
- `debug_session`: Get session status and metadata
- `connection_manager`: Manage connection resilience and health
- `session_manager`: Session recovery and state management

### Command Execution  
- `run_command`: Execute WinDbg commands with optimization
- `run_sequence`: Execute multiple commands in sequence

### Analysis Tools
- `analyze_process`: Process analysis and context switching
- `analyze_thread`: Thread analysis and stack traces
- `analyze_memory`: Memory inspection and structure analysis
- `analyze_kernel`: Kernel object and system analysis

### Performance Tools
- `performance_manager`: Performance optimization control
- `async_manager`: Asynchronous command execution

### Support Tools
- `troubleshoot`: Debugging assistance and diagnostics
- `get_help`: Tool documentation and examples

### Debug Mode
Enable debug logging for troubleshooting:
```bash
# Set environment variable
set DEBUG=true

# Or modify config.py
DEBUG_ENABLED = True
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Microsoft WinDbg team for the debugging platform
- Anthropic for the Model Context Protocol
- FastMCP for the Python MCP framework

**Happy kernel debugging! 🐛🔍**